from __future__ import annotations

import io
import json
import urllib.request

from PIL import Image

from outfitmatch.kb import tagging as tagging_mod
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.tagging import apply_item_tags, sanitize_tag_payload, tag_items


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


def test_sanitize_tag_payload_filters_unknown_enum_values():
    clean = sanitize_tag_payload(
        {
            "body_shapes_fit": ["pear", "alien"],
            "season": ["summer", "monsoon"],
            "stylist_notes_vi": "Mặc mát mùa nóng.",
        }
    )

    assert clean.body_shapes_fit == ["pear"]
    assert clean.season == ["summer"]
    assert clean.stylist_notes_vi == "Mặc mát mùa nóng."


def test_apply_item_tags_mutates_item_record():
    item = _item()
    tagged = sanitize_tag_payload(
        {
            "body_shapes_fit": ["pear", "rectangle"],
            "season": ["transitional"],
            "stylist_notes_vi": "Áo basic dễ phối.",
        }
    )

    apply_item_tags(item, tagged)

    assert item.body_shapes_fit == ["pear", "rectangle"]
    assert item.season == ["transitional"]
    assert item.stylist_notes_vi == "Áo basic dễ phối."


def test_probe_gemma_backend_uses_hf_login_token(monkeypatch, tmp_path):
    item = _item()
    seen: dict[str, str] = {}

    monkeypatch.setattr(tagging_mod, "_resolve_hf_token", lambda explicit: "hf-session-token")

    def fake_call_gemma(record: ItemRecord, *, gemma_model: str, api_key: str):
        seen["item_id"] = record.item_id
        seen["model"] = gemma_model
        seen["token"] = api_key
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "Gemma live ok.",
        }

    monkeypatch.setattr(tagging_mod, "_call_gemma", fake_call_gemma)

    tagged = tag_items(
        [item],
        backends=[tagging_mod.TaggingBackend(provider="gemma", model="google/gemma-3-27b-it")],
        cache_dir=str(tmp_path / "cache"),
        force=True,
    )

    assert seen == {
        "item_id": "item_1",
        "model": "google/gemma-3-27b-it",
        "token": "hf-session-token",
    }
    assert tagged[0].stylist_notes_vi == "Gemma live ok."


def test_probe_ollama_backend_uses_local_model(monkeypatch, tmp_path):
    item = _item()
    seen: dict[str, str] = {}

    def fake_call_ollama(record: ItemRecord, *, model: str):
        seen["item_id"] = record.item_id
        seen["model"] = model
        return {
            "body_shapes_fit": ["rectangle"],
            "season": ["transitional"],
            "stylist_notes_vi": "Ollama local ok.",
        }

    monkeypatch.setattr(tagging_mod, "_call_ollama", fake_call_ollama)

    tagged = tag_items(
        [item],
        backends=[tagging_mod.TaggingBackend(provider="ollama", model="qwen3-vl:8b")],
        cache_dir=str(tmp_path / "cache"),
        force=True,
    )

    assert seen == {"item_id": "item_1", "model": "qwen3-vl:8b"}
    assert tagged[0].body_shapes_fit == ["rectangle"]
    assert tagged[0].season == ["transitional"]
    assert tagged[0].stylist_notes_vi == "Ollama local ok."


def test_call_openai_compatible_converts_webp_to_jpeg_data_url(monkeypatch, tmp_path):
    image_path = tmp_path / "item.webp"
    Image.new("RGB", (4, 4), color="white").save(image_path, format="WEBP")
    item = _item()
    item.image_path = str(image_path)
    seen: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "body_shapes_fit": ["rectangle"],
                                    "season": ["summer"],
                                    "stylist_notes_vi": "OpenAI-compatible ok.",
                                }
                            )
                        }
                    }
                ]
            }
            self._buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))
            return self._buffer

        def __exit__(self, *args):
            return False

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        body = json.loads(request.data.decode("utf-8"))
        seen["body"] = body
        return _Response()

    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8087/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT", "123")
    monkeypatch.setattr(tagging_mod.urllib.request, "urlopen", fake_urlopen)

    payload = tagging_mod._call_openai_compatible(item, model="gemma4-turboquant")

    content = seen["body"]["messages"][0]["content"]
    assert seen["url"] == "http://127.0.0.1:8087/v1/chat/completions"
    assert seen["timeout"] == 123.0
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1]["type"] == "text"
    assert payload["season"] == ["summer"]


def test_tag_items_supports_openai_compatible_backend(monkeypatch, tmp_path):
    item = _item()
    seen: dict[str, str] = {}

    def fake_call_openai(record: ItemRecord, *, model: str):
        seen["item_id"] = record.item_id
        seen["model"] = model
        return {
            "body_shapes_fit": ["rectangle"],
            "season": ["summer"],
            "stylist_notes_vi": "TurboQuant ok.",
        }

    monkeypatch.setattr(tagging_mod, "_call_openai_compatible", fake_call_openai)

    tagged = tag_items(
        [item],
        backends=[tagging_mod.TaggingBackend(provider="openai", model="gemma4-turboquant")],
        cache_dir=str(tmp_path / "cache"),
        force=True,
    )

    assert seen == {"item_id": "item_1", "model": "gemma4-turboquant"}
    assert tagged[0].stylist_notes_vi == "TurboQuant ok."


def test_tag_items_adds_conservative_note_when_backend_returns_empty_payload(tmp_path):
    item = _item()
    item.category = "accessory"

    def transport(record: ItemRecord, backend: tagging_mod.TaggingBackend):
        return {"body_shapes_fit": [], "season": [], "stylist_notes_vi": ""}

    tagged = tag_items(
        [item],
        backends=[tagging_mod.TaggingBackend(provider="openai", model="gemma4-turboquant")],
        backend_transport=transport,
        cache_dir=str(tmp_path / "cache"),
        force=True,
    )

    assert tagged[0].body_shapes_fit == []
    assert tagged[0].season == []
    assert tagged[0].stylist_notes_vi == "Phụ kiện tạo điểm nhấn và hoàn thiện tổng thể outfit."


def test_tag_items_writes_progress_log_for_success_and_failure(tmp_path):
    success_item = _item("item_success")
    failed_item = _item("item_failed")
    progress_log = tmp_path / "progress.jsonl"
    backends = [tagging_mod.TaggingBackend(provider="gemma", model="google/gemma-3-27b-it")]

    def transport(record: ItemRecord, backend: tagging_mod.TaggingBackend):
        if record.item_id == "item_failed":
            raise RuntimeError("429 quota exceeded")
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "Logged ok.",
        }

    tag_items(
        [success_item, failed_item],
        cache_dir=str(tmp_path / "cache"),
        backends=backends,
        backend_transport=transport,
        progress_log=progress_log,
        force=True,
    )

    records = [json.loads(line) for line in progress_log.read_text(encoding="utf-8").splitlines()]

    assert records[0] == {
        "item_id": "item_success",
        "provider": "gemma",
        "model": "google/gemma-3-27b-it",
        "ok": True,
        "body_shapes_fit": ["pear"],
        "season": ["summer"],
        "stylist_notes_vi": "Logged ok.",
        "errors": [],
    }
    assert records[1]["item_id"] == "item_failed"
    assert records[1]["provider"] == "gemma"
    assert records[1]["model"] == "google/gemma-3-27b-it"
    assert records[1]["ok"] is False
    assert records[1]["errors"][0]["error"] == "429 quota exceeded"


def test_tag_items_uses_cache_and_transport_once(tmp_path):
    item = _item()
    calls: list[str] = []

    def transport(record: ItemRecord):
        calls.append(record.item_id)
        return {
            "body_shapes_fit": ["pear"],
            "season": ["summer"],
            "stylist_notes_vi": "Cached tag.",
        }

    first = tag_items([item], cache_dir=str(tmp_path / "cache"), transport=transport)
    second = tag_items([item], cache_dir=str(tmp_path / "cache"), transport=transport)

    assert calls == ["item_1"]
    assert first[0].body_shapes_fit == ["pear"]
    assert second[0].season == ["summer"]
