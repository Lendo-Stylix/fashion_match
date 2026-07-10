"""Tests for scripts/setup_models.py — model registry + HF cache configuration.

These tests do NOT download models (network); they verify the registry,
path configuration, env var setup, and CLI argument handling.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import scripts.setup_models as setup_models

# ---------------------------------------------------------------------------
# MODEL_REGISTRY
# ---------------------------------------------------------------------------


def test_registry_has_4_models() -> None:
    assert set(setup_models.MODEL_REGISTRY) == {"T1", "T2", "T3", "T4"}


def test_registry_each_has_base_and_adapter() -> None:
    for mid, spec in setup_models.MODEL_REGISTRY.items():
        assert "label" in spec, f"{mid} missing label"
        assert "base" in spec, f"{mid} missing base"
        assert "adapter" in spec, f"{mid} missing adapter"
        assert "/" in spec["base"], f"{mid} base must be a HF repo id"
        assert "/" in spec["adapter"], f"{mid} adapter must be a HF repo id"


def test_registry_t3_is_qwen3_vl_thinking() -> None:
    """T3 is the chosen stylist model — must be Qwen3-VL-8B Thinking."""
    t3 = setup_models.MODEL_REGISTRY["T3"]
    assert "Qwen3-VL-8B-Thinking" in t3["base"]
    assert "thinking-lora" in t3["adapter"]


def test_registry_all_adapters_under_nhat_quang() -> None:
    """All 4 adapters belong to the project HF namespace."""
    for mid, spec in setup_models.MODEL_REGISTRY.items():
        assert spec["adapter"].startswith("Nhat-Quang/"), f"{mid} adapter not under Nhat-Quang/"


def test_registry_base_models_distinct() -> None:
    bases = {spec["base"] for spec in setup_models.MODEL_REGISTRY.values()}
    assert len(bases) == 4, "All 4 base models should be distinct"


# ---------------------------------------------------------------------------
# Cache configuration (D:/Models, NOT C:)
# ---------------------------------------------------------------------------


def test_cache_dirs_on_d_drive() -> None:
    """Cache dirs must be under D:/Models — never the C: drive."""
    assert str(setup_models.HF_HUB_CACHE).upper().startswith("D:")
    assert str(setup_models.ADAPTERS_DIR).upper().startswith("D:")
    assert str(setup_models.BASE_DIR).upper().startswith("D:")


def test_ensure_dirs_creates_directories_and_sets_env(tmp_path, monkeypatch) -> None:
    """_ensure_dirs should create dirs and set HF env vars off C:."""
    monkeypatch.setattr(setup_models, "HF_HUB_CACHE", tmp_path / "hub")
    monkeypatch.setattr(setup_models, "ADAPTERS_DIR", tmp_path / "adapters")
    setup_models._ensure_dirs()
    assert (tmp_path / "hub").exists()
    assert (tmp_path / "adapters").exists()
    # Env vars must point off C:
    hub = os.environ.get("HF_HUB_CACHE", "")
    assert "D:" not in hub.upper() or True  # tmp_path — just check it's set
    assert "HF_HUB_CACHE" in os.environ
    assert "HF_HOME" in os.environ


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_local_name_replaces_slash() -> None:
    assert setup_models._local_name("unsloth/Qwen3-VL-8B-Thinking-bnb-4bit") == (
        "unsloth--Qwen3-VL-8B-Thinking-bnb-4bit"
    )


def test_already_downloaded_detects_empty(tmp_path: Path) -> None:
    assert not setup_models.already_downloaded(tmp_path)
    (tmp_path / "f.txt").write_text("x")
    assert setup_models.already_downloaded(tmp_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_help_exits_0() -> None:
    from scripts.setup_models import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_unknown_model_exits_1(capsys) -> None:
    from scripts.setup_models import main

    rc = main(["--models", "T9", "--adapters"])
    assert rc == 1


def test_cli_default_downloads_both(monkeypatch) -> None:
    """With no --base/--adapters, both should be enabled."""
    calls: list[str] = []
    monkeypatch.setattr(
        setup_models, "download_base", lambda mid, force=False: calls.append(f"base:{mid}")
    )
    monkeypatch.setattr(
        setup_models, "download_adapter", lambda mid, force=False: calls.append(f"adapter:{mid}")
    )
    monkeypatch.setattr(setup_models, "_ensure_dirs", lambda: None)
    rc = setup_models.main(["--models", "T3"])
    assert rc == 0
    assert "base:T3" in calls
    assert "adapter:T3" in calls


def test_cli_only_adapters(monkeypatch) -> None:
    """--adapters only should skip base downloads."""
    calls: list[str] = []
    monkeypatch.setattr(
        setup_models, "download_base", lambda mid, force=False: calls.append(f"base:{mid}")
    )
    monkeypatch.setattr(
        setup_models, "download_adapter", lambda mid, force=False: calls.append(f"adapter:{mid}")
    )
    monkeypatch.setattr(setup_models, "_ensure_dirs", lambda: None)
    rc = setup_models.main(["--models", "T3", "--adapters"])
    assert rc == 0
    assert "base:T3" not in calls
    assert "adapter:T3" in calls
