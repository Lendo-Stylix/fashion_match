"""Small HuggingFace wrapper for the OutfitTransformer-labse checkpoint.

The real checkpoint is intentionally kept behind this thin module so unit tests can
exercise KB code with fake encoders, while experiments can download/cache the HF
artifacts reproducibly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import torch
from huggingface_hub import snapshot_download

DEFAULT_MODEL_ID = "fkuyumcu/OutfitTransformer-labse"
MODEL_ALLOW_PATTERNS = ["config.json", "model.py", "pytorch_model.bin", "README.md"]


def snapshot_outfit_transformer(
    model_id: str = DEFAULT_MODEL_ID,
    *,
    cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> Path:
    """Download or resolve the OutfitTransformer-labse HF snapshot.

    Only the small model artifacts needed for the CIR transformer are fetched; LaBSE
    and ResNet feature extraction are separate dependencies and can be loaded lazily
    by an experimental encoder implementation.
    """
    path = snapshot_download(
        repo_id=model_id,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
        allow_patterns=MODEL_ALLOW_PATTERNS,
        local_files_only=local_files_only,
    )
    return Path(path)


def load_model_config(snapshot_dir: Path) -> dict[str, Any]:
    """Read ``config.json`` from a downloaded OutfitTransformer snapshot."""
    with (snapshot_dir / "config.json").open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config.json in {snapshot_dir}")
    return data


def load_cir_model(snapshot_dir: Path, *, map_location: str = "cpu") -> torch.nn.Module:
    """Load the HF snapshot's ``OutfitTransformerCIR`` class and PyTorch weights."""
    config = load_model_config(snapshot_dir)
    model_py = snapshot_dir / "model.py"
    spec = importlib.util.spec_from_file_location("outfit_transformer_snapshot_model", model_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import model.py from {snapshot_dir}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = module.OutfitTransformerCIR
    model = cls(
        embedding_dim=int(config.get("embedding_dim", 128)),
        nhead=int(config.get("nhead", 16)),
        num_layers=int(config.get("num_layers", 6)),
    )
    state = torch.load(snapshot_dir / "pytorch_model.bin", map_location=map_location)
    model.load_state_dict(state)
    model.eval()
    return model
