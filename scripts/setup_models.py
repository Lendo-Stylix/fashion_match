"""Download 4 base models + 4 LoRA adapters to D:/Models (off the C: drive).

Configures HF caches so HuggingFace downloads never land in ~/.cache on C:.
Both base models (full snapshots) and adapters (small LoRA weights) are stored
in D:/Models/{hf_hub,adapters}/.

Example:
    uv run python scripts/setup_models.py --base --adapters
    uv run python scripts/setup_models.py --base --models T1 T3
    uv run python scripts/setup_models.py --adapters --models T3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path("D:/Models")
HF_HUB_CACHE = BASE_DIR / "hf_hub"
ADAPTERS_DIR = BASE_DIR / "adapters"

# Set HF cache env vars at IMPORT TIME so no download ever leaks to C:\~/.cache.
# These must be set before any huggingface_hub / transformers import.
os.environ.setdefault("HF_HUB_CACHE", str(HF_HUB_CACHE))
os.environ.setdefault("HF_HOME", str(BASE_DIR / "hf_home"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_HUB_CACHE))

# 4 base models + 4 adapters verified 2026-07-10
MODEL_REGISTRY = {
    "T1": {
        "label": "Qwen3-VL-8B Instruct",
        "base": "unsloth/Qwen3-VL-8B-Instruct-bnb-4bit",
        "adapter": "Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-instruct-lora",
    },
    "T2": {
        "label": "Qwen3.5-9B BNB4",
        "base": "techwithsergiu/Qwen3.5-text-9B-bnb-4bit",
        "adapter": "Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora",
    },
    "T3": {
        "label": "Qwen3-VL-8B Thinking",
        "base": "unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",
        "adapter": "Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora",
    },
    "T4": {
        "label": "Gemma 4 12B IT",
        "base": "unsloth/gemma-4-12b-it",
        "adapter": "Nhat-Quang/outfitmatch-stylist-final-gemma4-12b-it-lora",
    },
}


def _ensure_dirs() -> None:
    """Create cache directories on D: and set HF env vars (off C:)."""
    HF_HUB_CACHE.mkdir(parents=True, exist_ok=True)
    ADAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    # Tell HuggingFace to cache on D: (high precedence env var)
    os.environ["HF_HUB_CACHE"] = str(HF_HUB_CACHE)
    os.environ["HF_HOME"] = str(BASE_DIR / "hf_home")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_HUB_CACHE)


def _local_name(repo_id: str) -> str:
    return repo_id.replace("/", "--")


def already_downloaded(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def download_base(model_id: str, force: bool = False) -> Path:
    """Download a base model snapshot to D:/Models/hf_hub/."""
    from huggingface_hub import snapshot_download

    spec = MODEL_REGISTRY[model_id]
    local = HF_HUB_CACHE / _local_name(spec["base"])
    if not force and already_downloaded(local):
        print(f"[skip] {model_id} base already at {local}", file=sys.stderr)
        return local
    print(f"[get ] {model_id} base <- {spec['base']} -> {local}", file=sys.stderr)
    snapshot_download(
        repo_id=spec["base"],
        cache_dir=str(HF_HUB_CACHE),
        local_dir=str(local),
    )
    print(f"[ok  ] {model_id} base downloaded", file=sys.stderr)
    return local


def download_adapter(model_id: str, force: bool = False) -> Path:
    """Download a LoRA adapter (small) to D:/Models/adapters/."""
    from huggingface_hub import snapshot_download

    spec = MODEL_REGISTRY[model_id]
    local = ADAPTERS_DIR / _local_name(spec["adapter"])
    if not force and already_downloaded(local):
        print(f"[skip] {model_id} adapter already at {local}", file=sys.stderr)
        return local
    print(f"[get ] {model_id} adapter <- {spec['adapter']} -> {local}", file=sys.stderr)
    snapshot_download(
        repo_id=spec["adapter"],
        cache_dir=str(HF_HUB_CACHE),
        local_dir=str(local),
        # adapters are small but skip the original_untrained checkpoint if present
        ignore_patterns=["*.bin.index.json", "*.msgpack", "*.h5"],
    )
    print(f"[ok  ] {model_id} adapter downloaded", file=sys.stderr)
    return local


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download 4 base models + 4 LoRA adapters to D:/Models (off C:)."
    )
    parser.add_argument("--base", action="store_true", help="Download base model snapshots.")
    parser.add_argument("--adapters", action="store_true", help="Download LoRA adapters only.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODEL_REGISTRY),
        help="Which model IDs to download (default: T1 T2 T3 T4).",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if already present.")
    args = parser.parse_args(argv)

    if not args.base and not args.adapters:
        # default: both
        args.base = True
        args.adapters = True

    _ensure_dirs()
    print("=" * 60, file=sys.stderr)
    print(f"HF cache dir: {HF_HUB_CACHE}", file=sys.stderr)
    print(f"Adapters dir: {ADAPTERS_DIR}", file=sys.stderr)
    print(f"Models: {args.models}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    targets = [m for m in args.models if m in MODEL_REGISTRY]
    if not targets:
        print(f"Unknown model IDs: {args.models}. Valid: {list(MODEL_REGISTRY)}", file=sys.stderr)
        return 1
    rc = 0
    for mid in targets:
        try:
            if args.base:
                download_base(mid, force=args.force)
            if args.adapters:
                download_adapter(mid, force=args.force)
        except Exception as exc:  # noqa: BLE001 - report all failures
            print(f"[err ] {mid}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
