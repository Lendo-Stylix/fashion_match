from __future__ import annotations

import pandas as pd
from scripts.data.kb import tag_items as cli

from outfitmatch.kb.tagging import BackendProbeResult, TaggingBackend


class _Item:
    def __init__(self, item_id: str):
        self.item_id = item_id
        self.body_shapes_fit: list[str] = []
        self.season: list[str] = []
        self.stylist_notes_vi = ""


def test_parse_args_defaults_to_long_run_google_models():
    args = cli._parse_args([])

    assert args.model == "gemma-4-26b-a4b-it"
    assert args.gemma_model == "gemma-4-31b-it"
    assert args.lite_model == "gemini-3.1-flash-lite"
    assert args.offset == 0
    assert args.limit == 0
    assert args.skip_tagged is False
    assert args.progress_log is None
    assert args.max_consecutive_backend_failures == 5


def test_candidate_backends_defaults_to_three_google_models():
    args = cli._parse_args([])

    assert cli._candidate_backends(args) == [
        TaggingBackend(provider="gemini", model="gemma-4-26b-a4b-it"),
        TaggingBackend(provider="gemini", model="gemma-4-31b-it"),
        TaggingBackend(provider="gemini", model="gemini-3.1-flash-lite"),
    ]


def test_candidate_backends_prepends_ollama_models_when_requested():
    args = cli._parse_args(
        [
            "--ollama-model",
            "qwen3-vl:8b",
            "--ollama-model",
            "gemma3:4b",
        ]
    )

    assert cli._candidate_backends(args)[:2] == [
        TaggingBackend(provider="ollama", model="qwen3-vl:8b"),
        TaggingBackend(provider="ollama", model="gemma3:4b"),
    ]


def test_candidate_backends_can_use_ollama_only():
    args = cli._parse_args(["--ollama-model", "qwen3-vl:2b", "--ollama-only"])

    assert cli._candidate_backends(args) == [
        TaggingBackend(provider="ollama", model="qwen3-vl:2b"),
    ]


def test_candidate_backends_supports_openai_compatible_llama_cpp_only():
    args = cli._parse_args(
        [
            "--openai-model",
            "gemma4-turboquant",
            "--openai-base-url",
            "http://127.0.0.1:8087/v1",
            "--openai-only",
        ]
    )

    assert args.openai_base_url == "http://127.0.0.1:8087/v1"
    assert cli._candidate_backends(args) == [
        TaggingBackend(provider="openai", model="gemma4-turboquant"),
    ]


def test_select_items_applies_offset_then_limit():
    items = [
        type(
            "Item",
            (),
            {"item_id": f"item_{i}", "body_shapes_fit": [], "season": [], "stylist_notes_vi": ""},
        )()
        for i in range(6)
    ]

    selected = cli._select_items(items, item_ids=set(), offset=2, limit=3, skip_tagged=False)

    assert [item.item_id for item in selected] == ["item_2", "item_3", "item_4"]


def test_select_items_skips_already_tagged_items_when_requested():
    items = [
        type(
            "Item",
            (),
            {
                "item_id": "item_1",
                "body_shapes_fit": ["pear"],
                "season": [],
                "stylist_notes_vi": "",
            },
        )(),
        type(
            "Item",
            (),
            {
                "item_id": "item_2",
                "body_shapes_fit": [],
                "season": [],
                "stylist_notes_vi": "Đã tag",
            },
        )(),
        type(
            "Item",
            (),
            {"item_id": "item_3", "body_shapes_fit": [], "season": [], "stylist_notes_vi": ""},
        )(),
    ]

    selected = cli._select_items(items, item_ids=set(), offset=0, limit=0, skip_tagged=True)

    assert [item.item_id for item in selected] == ["item_3"]


def test_is_tagged_requires_complete_main_garment_semantics_and_colors():
    complete = _Item("complete")
    complete.category = "top"
    complete.store = {"colors": ["đen"]}
    complete.body_shapes_fit = ["rectangle"]
    complete.season = ["summer"]
    complete.stylist_notes_vi = "ok"

    note_only = _Item("note_only")
    note_only.category = "top"
    note_only.store = {"colors": ["đen"]}
    note_only.stylist_notes_vi = "only note"

    colorless = _Item("colorless")
    colorless.category = "top"
    colorless.store = {"colors": []}
    colorless.body_shapes_fit = ["rectangle"]
    colorless.season = ["summer"]
    colorless.stylist_notes_vi = "ok"

    assert cli._is_tagged(complete) is True
    assert cli._is_tagged(note_only) is False
    assert cli._is_tagged(colorless) is False


def test_write_back_updates_only_items_with_semantic_signal(tmp_path):
    catalog = tmp_path / "catalog.parquet"
    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "body_shapes_fit": "[]",
                "season": "[]",
                "stylist_notes_vi": "",
            },
            {
                "item_id": "item_2",
                "body_shapes_fit": "[]",
                "season": "[]",
                "stylist_notes_vi": "",
            },
        ]
    ).to_parquet(catalog, index=False)

    item_ok = _Item("item_1")
    item_ok.season = ["summer"]
    item_ok.stylist_notes_vi = "ok"
    item_fail = _Item("item_2")

    updated = cli._write_back(catalog, [item_ok, item_fail])
    written = pd.read_parquet(catalog)

    assert updated == 1
    assert written.loc[0, "season"] == '["summer"]'
    assert written.loc[0, "stylist_notes_vi"] == "ok"
    assert written.loc[1, "season"] == "[]"
    assert written.loc[1, "stylist_notes_vi"] == ""


def test_main_uses_history_gate_when_failed_log_is_given(monkeypatch, tmp_path):
    item = _Item("item_1")
    catalog = tmp_path / "catalog.parquet"
    links = tmp_path / "links.parquet"
    failed_log = tmp_path / "failed.jsonl"
    catalog.write_bytes(b"x")
    links.write_bytes(b"x")
    failed_log.write_text("", encoding="utf-8")

    chosen = TaggingBackend(provider="gemma", model="gemma-3-27b-it")
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "load_catalog_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(
        cli,
        "gate_backends",
        lambda selected_item, *, backends, progress_path, **kwargs: [
            BackendProbeResult(backend=backends[0], status="rate_limited", error="429"),
            BackendProbeResult(backend=chosen, status="ok"),
        ],
    )
    monkeypatch.setattr(cli, "select_backend", lambda results: chosen)

    def fake_tag_items(selected, **kwargs):
        seen["backends"] = kwargs["backends"]
        return selected

    monkeypatch.setattr(cli, "tag_items", fake_tag_items)
    monkeypatch.setattr(cli, "clear_failed_429_tags", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cli, "_write_back", lambda *args, **kwargs: 1)

    exit_code = cli.main(
        [
            "--catalog",
            str(catalog),
            "--links",
            str(links),
            "--failed-log",
            str(failed_log),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert seen["backends"] == [chosen]


def test_main_passes_progress_log_to_tag_items(monkeypatch, tmp_path):
    item = _Item("item_1")
    catalog = tmp_path / "catalog.parquet"
    links = tmp_path / "links.parquet"
    progress_log = tmp_path / "progress.jsonl"
    catalog.write_bytes(b"x")
    links.write_bytes(b"x")

    chosen = TaggingBackend(provider="gemma", model="gemma-3-27b-it")
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "load_catalog_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(
        cli,
        "probe_backends",
        lambda selected_item, *, backends, **kwargs: [
            BackendProbeResult(backend=chosen, status="ok")
        ],
    )
    monkeypatch.setattr(cli, "select_backend", lambda results: chosen)

    def fake_tag_items(selected, **kwargs):
        seen["progress_log"] = kwargs["progress_log"]
        seen["max_consecutive_backend_failures"] = kwargs["max_consecutive_backend_failures"]
        return selected

    monkeypatch.setattr(cli, "tag_items", fake_tag_items)
    monkeypatch.setattr(cli, "_write_back", lambda *args, **kwargs: 1)

    exit_code = cli.main(
        [
            "--catalog",
            str(catalog),
            "--links",
            str(links),
            "--progress-log",
            str(progress_log),
            "--max-consecutive-backend-failures",
            "2",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert seen["progress_log"] == progress_log
    assert seen["max_consecutive_backend_failures"] == 2


def test_main_passes_all_healthy_backends_to_tag_items(monkeypatch, tmp_path):
    item = _Item("item_1")
    catalog = tmp_path / "catalog.parquet"
    links = tmp_path / "links.parquet"
    catalog.write_bytes(b"x")
    links.write_bytes(b"x")

    backends = [
        TaggingBackend(provider="gemini", model="gemma-4-26b-a4b-it"),
        TaggingBackend(provider="gemini", model="gemma-4-31b-it"),
        TaggingBackend(provider="gemini", model="gemini-3.1-flash-lite"),
    ]
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "load_catalog_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(
        cli,
        "probe_backends",
        lambda selected_item, *, backends, **kwargs: [
            BackendProbeResult(backend=backends[0], status="ok"),
            BackendProbeResult(backend=backends[1], status="ok"),
            BackendProbeResult(backend=backends[2], status="ok"),
        ],
    )
    monkeypatch.setattr(cli, "select_backend", lambda results: results[0].backend)

    def fake_tag_items(selected, **kwargs):
        seen["selected"] = selected
        seen["backends"] = kwargs["backends"]
        return selected

    monkeypatch.setattr(cli, "tag_items", fake_tag_items)
    monkeypatch.setattr(cli, "_write_back", lambda *args, **kwargs: 1)

    exit_code = cli.main(
        [
            "--catalog",
            str(catalog),
            "--links",
            str(links),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert seen["selected"] == [item]
    assert seen["backends"] == backends


def test_main_probes_backends_then_uses_selected_backend(monkeypatch, tmp_path):
    item = _Item("item_1")
    catalog = tmp_path / "catalog.parquet"
    links = tmp_path / "links.parquet"
    catalog.write_bytes(b"x")
    links.write_bytes(b"x")

    chosen = TaggingBackend(provider="gemma", model="gemma-3-27b-it")
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "load_catalog_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(
        cli,
        "probe_backends",
        lambda selected_item, *, backends, **kwargs: [
            BackendProbeResult(
                backend=backends[0],
                status="rate_limited",
                error="429",
                limit_rpm=20,
                retry_after_s=30.0,
            ),
            BackendProbeResult(backend=chosen, status="ok"),
        ],
    )
    monkeypatch.setattr(cli, "select_backend", lambda results: chosen)

    def fake_tag_items(selected, **kwargs):
        seen["selected"] = selected
        seen["backends"] = kwargs["backends"]
        return selected

    monkeypatch.setattr(cli, "tag_items", fake_tag_items)
    monkeypatch.setattr(cli, "_write_back", lambda *args, **kwargs: 1)

    exit_code = cli.main(
        [
            "--catalog",
            str(catalog),
            "--links",
            str(links),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert seen["selected"] == [item]
    assert seen["backends"] == [chosen]
