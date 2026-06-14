from __future__ import annotations

import json

from scripts.data.kb import eval_tagging_models as eval_mod


def test_summarize_progress_scores_valid_json_quality(tmp_path):
    progress = tmp_path / "qwen.jsonl"
    progress.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "item_id": "item_1",
                        "provider": "ollama",
                        "model": "qwen2.5vl:3b",
                        "ok": True,
                        "body_shapes_fit": ["rectangle"],
                        "season": ["summer"],
                        "stylist_notes_vi": "Áo dáng suông hợp mùa hè.",
                        "latency_s": 12.5,
                        "errors": [],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "item_id": "item_2",
                        "provider": "ollama",
                        "model": "qwen2.5vl:3b",
                        "ok": False,
                        "body_shapes_fit": [],
                        "season": [],
                        "stylist_notes_vi": "",
                        "latency_s": 1.0,
                        "errors": [{"error": "empty content"}],
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    summary = eval_mod.summarize_progress(progress, model="qwen2.5vl:3b")

    assert summary.model == "qwen2.5vl:3b"
    assert summary.total == 2
    assert summary.ok == 1
    assert summary.with_body_shape == 1
    assert summary.with_season == 1
    assert summary.with_note == 1
    assert summary.avg_latency_s == 6.75
    assert summary.quality_score == 0.5


def test_choose_best_model_prefers_quality_then_latency():
    slow = eval_mod.ModelQualitySummary(
        model="slow",
        total=10,
        ok=10,
        with_body_shape=10,
        with_season=10,
        with_note=10,
        avg_latency_s=20.0,
    )
    fast = eval_mod.ModelQualitySummary(
        model="fast",
        total=10,
        ok=10,
        with_body_shape=10,
        with_season=10,
        with_note=10,
        avg_latency_s=5.0,
    )
    weak = eval_mod.ModelQualitySummary(
        model="weak",
        total=10,
        ok=8,
        with_body_shape=8,
        with_season=8,
        with_note=8,
        avg_latency_s=1.0,
    )

    assert eval_mod.choose_best_model([slow, fast, weak]) == fast


def test_evaluate_model_accepts_openai_provider(monkeypatch, tmp_path):
    item = type(
        "Item",
        (),
        {"item_id": "item_1", "body_shapes_fit": [], "season": [], "stylist_notes_vi": ""},
    )()
    seen: dict[str, object] = {}

    def fake_tag_items(items, **kwargs):
        backend = kwargs["backends"][0]
        seen["provider"] = backend.provider
        seen["model"] = backend.model
        seen["progress_log"] = kwargs["progress_log"]
        kwargs["progress_log"].write_text(
            json.dumps(
                {
                    "item_id": "item_1",
                    "provider": backend.provider,
                    "model": backend.model,
                    "ok": True,
                    "body_shapes_fit": ["rectangle"],
                    "season": ["summer"],
                    "stylist_notes_vi": "TurboQuant ok.",
                    "errors": [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return items

    monkeypatch.setattr(eval_mod, "tag_items", fake_tag_items)

    summary = eval_mod.evaluate_model(
        [item],
        provider="openai",
        model="gemma4-turboquant",
        output_dir=tmp_path / "out",
        cache_dir=tmp_path / "cache",
        force=True,
    )

    assert seen["provider"] == "openai"
    assert seen["model"] == "gemma4-turboquant"
    assert summary.ok == 1
    assert summary.quality_score == 1.0
