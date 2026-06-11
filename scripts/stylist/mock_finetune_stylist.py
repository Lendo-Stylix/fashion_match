"""Create a dry-run manifest for the next Stylist fine-tuning task.

This script does not train a model. It validates the local mock layout, checks that
Kaggle token *names* exist in .env.local, and writes a redacted manifest for three
candidate GGUF deployments driven by Llama Turbo Quant / llama.cpp.

Important: GGUF is treated as the inference artifact. Real LoRA/SFT should train
against the corresponding trainable base weights, then export/quantize for GGUF.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("configs/stylist_finetune_mock.yaml")


def _read_env_keys(env_path: Path) -> set[str]:
    """Return variable names defined in a dotenv file without exposing values."""
    if not env_path.exists():
        return set()

    keys: set[str] = set()
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _load_config(path: Path) -> dict[str, Any]:
    """Load the YAML mock config."""
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return loaded


def _ensure_dirs(paths: list[Path], *, create_dirs: bool) -> list[dict[str, Any]]:
    """Check or create directories and return manifest-safe status rows."""
    rows: list[dict[str, Any]] = []
    for path in paths:
        if create_dirs:
            path.mkdir(parents=True, exist_ok=True)
        rows.append({"path": str(path), "exists": path.is_dir()})
    return rows


def _count_dataset_files(path: Path, accepted_extensions: set[str]) -> int:
    """Count candidate source files in a dataset folder."""
    if not path.is_dir():
        return 0
    return sum(
        1
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in accepted_extensions
    )


def _build_dataset_manifest(
    config: dict[str, Any], *, create_dirs: bool
) -> tuple[dict[str, Any], list[Path]]:
    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("Missing `dataset` mapping in config")

    stylist_knowledge_dir = Path(str(dataset["stylist_knowledge_dir"]))
    users_query_response_dir = Path(str(dataset["users_query_response_dir"]))
    runs_dir = Path(str(config.get("outputs", {}).get("mock_manifest", ""))).parent
    dirs = [stylist_knowledge_dir, users_query_response_dir, runs_dir]

    accepted_extensions = {
        str(ext).lower() for ext in dataset.get("accepted_extensions", [])
    }
    dir_rows = _ensure_dirs(dirs, create_dirs=create_dirs)

    manifest = {
        "root": dataset.get("root"),
        "target_training_format": dataset.get("target_training_format"),
        "required_training_fields": dataset.get("required_training_fields", []),
        "directories": dir_rows,
        "file_counts": {
            "stylist_knowledge": _count_dataset_files(
                stylist_knowledge_dir, accepted_extensions
            ),
            "users_query_and_response": _count_dataset_files(
                users_query_response_dir, accepted_extensions
            ),
        },
    }
    return manifest, dirs


def _build_device_manifest(config: dict[str, Any], env_keys: set[str]) -> dict[str, Any]:
    device = config.get("device")
    if not isinstance(device, dict):
        raise ValueError("Missing `device` mapping in config")

    token_env_vars = [str(key) for key in device.get("token_env_vars", [])]
    return {
        "provider": device.get("provider"),
        "env_file": device.get("env_file"),
        "tokens": [
            {"env_var": key, "present_in_env_file": key in env_keys}
            for key in token_env_vars
        ],
    }


def _build_model_manifest(config: dict[str, Any], env_keys: set[str]) -> list[dict[str, Any]]:
    models = config.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Config must define a non-empty `models` list")

    rows: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Each model entry must be a mapping")
        token_env = str(model.get("kaggle_token_env", ""))
        rows.append(
            {
                "run_id": model.get("run_id"),
                "kaggle_token_env": token_env,
                "kaggle_token_present": token_env in env_keys,
                "gguf_repo": model.get("gguf_repo"),
                "gguf_selector": model.get("gguf_selector"),
                "trainable_base_model": model.get("trainable_base_model"),
                "modality": model.get("modality"),
                "role": model.get("role"),
                "request_overrides": model.get("request_overrides", {}),
                "llama_server_flags": model.get("llama_server_flags", []),
                "status": "mock_ready" if token_env in env_keys else "missing_kaggle_token",
            }
        )
    return rows


def build_manifest(config_path: Path, *, create_dirs: bool) -> dict[str, Any]:
    """Build a redacted dry-run manifest from the mock config."""
    config = _load_config(config_path)
    device = config.get("device", {})
    env_file = Path(str(device.get("env_file", ".env.local")))
    env_keys = set(os.environ) | _read_env_keys(env_file)
    dataset_manifest, _ = _build_dataset_manifest(config, create_dirs=create_dirs)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "config_path": str(config_path),
        "task": config.get("task"),
        "mode": config.get("mode"),
        "driver": config.get("driver", {}),
        "device": _build_device_manifest(config, env_keys),
        "dataset": dataset_manifest,
        "models": _build_model_manifest(config, env_keys),
        "mock_pipeline": config.get("mock_pipeline", {}),
        "outputs": config.get("outputs", {}),
        "notes": [
            "No Kaggle token values are included in this manifest.",
            "GGUF rows are inference targets; train LoRA on trainable_base_model weights.",
            "Use the same benchmark pack before and after SFT for a fair comparison.",
        ],
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output manifest path. Defaults to outputs.mock_manifest from config.",
    )
    parser.add_argument(
        "--create-dirs",
        action="store_true",
        help="Create dataset/run directories declared in the config.",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.config, create_dirs=args.create_dirs)
    out_path = args.out
    if out_path is None:
        output_config = manifest.get("outputs", {})
        out_path = Path(str(output_config.get("mock_manifest")))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote mock manifest: {out_path}")


if __name__ == "__main__":
    main()
