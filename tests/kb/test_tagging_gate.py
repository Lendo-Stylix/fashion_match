from __future__ import annotations

import pandas as pd
import pytest

from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.tagging import (
    TaggingBackend,
    clear_failed_429_tags,
    gate_backends,
    probe_backends,
    select_backend,
    tag_items,
)


def _item(item_id: str = "item_1") -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category="top",
        image_path="data/custom/catalog/images/item_1.jpg",
        item_embedding=[],
        store={
            "store_id": "canifa_vn",
            "store_name": "Canifa",
            "product_url": "https://canifa.vn/p/1",
            "price_vnd": 299000,
            "in_stock": True,
            "title_vi": "Áo thun cotton basic",
            "desc_vi": "Dáng suông, mát, dễ phối đồ.",
            "colors": ["trắng"],
        },
    )


def test_probe_backends_marks_rate_limited_and_selects_fallback():
    item = _item()
    backends = [
        TaggingBackend(provider="gemini", model="gemini-2.5-flash"),
        TaggingBackend(provider="gemma", model="gemma-3-27b-it"),
    ]

    def transport(record: ItemRecord, backend: TaggingBackend):
        if backend.provider == "gemini":
            raise RuntimeError(
                "429 You exceeded your current quota. "
                "* Quota exceeded for metric: requests, limit: 20, model: gemini-2.5-flash "
                "Please retry in 29.9s."
            )
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": f"fallback:{backend.provider}",
        }

    results = probe_backends(item, backends=backends, transport=transport)

    assert results[0].status == "rate_limited"
    assert results[0].limit_rpm == 20
    assert results[0].retry_after_s == 29.9
    assert select_backend(results) == backends[1]


def test_tag_items_falls_back_from_gemini_to_gemma(tmp_path):
    item = _item()
    backends = [
        TaggingBackend(provider="gemini", model="gemini-2.5-flash"),
        TaggingBackend(provider="gemma", model="gemma-3-27b-it"),
    ]
    calls: list[tuple[str, str]] = []

    def transport(record: ItemRecord, backend: TaggingBackend):
        calls.append((backend.provider, backend.model))
        if backend.provider == "gemini":
            raise RuntimeError(
                "429 You exceeded your current quota. "
                "* Quota exceeded for metric: requests, limit: 20, model: gemini-2.5-flash "
                "Please retry in 29.9s."
            )
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "Gemma fallback ok.",
        }

    tagged = tag_items(
        [item],
        cache_dir=str(tmp_path / "cache"),
        backends=backends,
        backend_transport=transport,
    )

    assert calls == [
        ("gemini", "gemini-2.5-flash"),
        ("gemma", "gemma-3-27b-it"),
    ]
    assert tagged[0].body_shapes_fit == ["pear"]
    assert tagged[0].season == ["summer"]
    assert tagged[0].stylist_notes_vi == "Gemma fallback ok."


def test_gate_backends_prefers_history_over_live_probe(tmp_path):
    item = _item()
    backends = [
        TaggingBackend(provider="gemini", model="gemini-2.5-flash"),
        TaggingBackend(provider="gemma", model="gemma-3-27b-it"),
    ]
    progress_path = tmp_path / "progress.jsonl"
    progress_path.write_text(
        "\n".join(
            [
                '{"item_id":"item_22","model":"gemini-2.5-flash",'
                '"ok":false,"errors":[{"error":"429 quota exceeded '
                'limit: 20 Please retry in 29.9s."}]}',
                '{"item_id":"item_23","model":"gemma-3-27b-it","ok":true,"errors":[]}',
            ]
        ),
        encoding="utf-8",
    )

    def transport(record: ItemRecord, backend: TaggingBackend):
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": f"ok:{backend.provider}",
        }

    results = gate_backends(
        item, backends=backends, progress_path=progress_path, transport=transport
    )

    assert results[0].status == "rate_limited"
    assert results[0].limit_rpm == 20
    assert select_backend(results) == backends[1]


def test_gate_backends_allows_backend_after_later_success(tmp_path):
    item = _item()
    backends = [TaggingBackend(provider="gemma", model="gemma-3-27b-it")]
    progress_path = tmp_path / "progress.jsonl"
    progress_path.write_text(
        "\n".join(
            [
                '{"item_id":"item_22","model":"gemma-3-27b-it",'
                '"ok":false,"errors":[{"error":"429 quota exceeded limit: 20"}]}',
                '{"item_id":"item_23","model":"gemma-3-27b-it","ok":true,"errors":[]}',
            ]
        ),
        encoding="utf-8",
    )

    def transport(record: ItemRecord, backend: TaggingBackend):
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "ok:gemma",
        }

    results = gate_backends(
        item, backends=backends, progress_path=progress_path, transport=transport
    )

    assert results[0].status == "ok"


def test_gate_backends_reprobes_after_connection_refused_history(tmp_path):
    item = _item()
    backend = TaggingBackend(provider="openai", model="gemma4-turboquant")
    progress_path = tmp_path / "progress.jsonl"
    progress_path.write_text(
        '{"item_id":"item_47","model":"gemma4-turboquant","ok":false,'
        '"errors":[{"error":"<urlopen error [WinError 10061] No connection could be made '
        'because the target machine actively refused it>"}]}',
        encoding="utf-8",
    )
    calls: list[str] = []

    def transport(record: ItemRecord, probed_backend: TaggingBackend):
        calls.append(probed_backend.model)
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "server restarted ok",
        }

    results = gate_backends(
        item, backends=[backend], progress_path=progress_path, transport=transport
    )

    assert calls == ["gemma4-turboquant"]
    assert results[0].status == "ok"


def test_tag_items_aborts_after_consecutive_connection_failures(tmp_path):
    items = [_item(f"item_{idx}") for idx in range(4)]
    backend = TaggingBackend(provider="openai", model="gemma4-turboquant")
    progress_log = tmp_path / "progress.jsonl"
    calls: list[str] = []

    def transport(record: ItemRecord, probed_backend: TaggingBackend):
        calls.append(record.item_id)
        if len(calls) == 1:
            raise RuntimeError(
                "<urlopen error [WinError 10060] A connection attempt failed because "
                "the connected party did not properly respond after a period of time>"
            )
        raise RuntimeError(
            "<urlopen error [WinError 10061] No connection could be made because "
            "the target machine actively refused it>"
        )

    with pytest.raises(RuntimeError, match="Aborting tagging batch"):
        tag_items(
            items,
            cache_dir=str(tmp_path / "cache"),
            backends=[backend],
            backend_transport=transport,
            progress_log=progress_log,
            max_consecutive_backend_failures=2,
        )

    assert calls == ["item_0", "item_1"]
    records = [
        line for line in progress_log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(records) == 2


def test_clear_failed_429_tags_resets_only_failed_rows(tmp_path):
    catalog_path = tmp_path / "catalog.parquet"
    progress_path = tmp_path / "progress.jsonl"

    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "body_shapes_fit": '["pear"]',
                "season": '["summer"]',
                "stylist_notes_vi": "dirty",
            },
            {
                "item_id": "item_2",
                "body_shapes_fit": '["rectangle"]',
                "season": '["winter"]',
                "stylist_notes_vi": "keep",
            },
        ]
    ).to_parquet(catalog_path, index=False)

    progress_path.write_text(
        "\n".join(
            [
                '{"item_id":"item_1","ok":false,"errors":[{"error":"429 quota exceeded"}]}',
                '{"item_id":"item_2","ok":true,"errors":[]}',
            ]
        ),
        encoding="utf-8",
    )

    cleared = clear_failed_429_tags(catalog_path, progress_path)
    cleaned = pd.read_parquet(catalog_path)

    assert cleared == 1
    assert cleaned.loc[0, "body_shapes_fit"] == "[]"
    assert cleaned.loc[0, "season"] == "[]"
    assert cleaned.loc[0, "stylist_notes_vi"] == ""
    assert cleaned.loc[1, "body_shapes_fit"] == '["rectangle"]'


def test_clear_failed_429_tags_keeps_item_after_later_success(tmp_path):
    catalog_path = tmp_path / "catalog.parquet"
    progress_path = tmp_path / "progress.jsonl"

    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "body_shapes_fit": '["pear"]',
                "season": '["summer"]',
                "stylist_notes_vi": "keep rerun success",
            }
        ]
    ).to_parquet(catalog_path, index=False)

    progress_path.write_text(
        "\n".join(
            [
                '{"item_id":"item_1","ok":false,"errors":[{"error":"429 quota exceeded"}]}',
                '{"item_id":"item_1","ok":true,"errors":[]}',
            ]
        ),
        encoding="utf-8",
    )

    cleared = clear_failed_429_tags(catalog_path, progress_path)
    cleaned = pd.read_parquet(catalog_path)

    assert cleared == 0
    assert cleaned.loc[0, "body_shapes_fit"] == '["pear"]'
    assert cleaned.loc[0, "season"] == '["summer"]'
    assert cleaned.loc[0, "stylist_notes_vi"] == "keep rerun success"
