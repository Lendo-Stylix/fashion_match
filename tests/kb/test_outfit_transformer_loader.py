from __future__ import annotations

import json

import torch

from outfitmatch.kb.outfit_transformer import (
    DEFAULT_MODEL_ID,
    load_cir_model,
    load_model_config,
    snapshot_outfit_transformer,
)


def test_snapshot_download_delegation(monkeypatch, tmp_path):
    calls = {}

    def fake_snapshot_download(**kwargs):
        calls.update(kwargs)
        return str(tmp_path / "snapshot")

    monkeypatch.setattr(
        "outfitmatch.kb.outfit_transformer.snapshot_download", fake_snapshot_download
    )

    path = snapshot_outfit_transformer(cache_dir=tmp_path, local_files_only=True)

    assert path == tmp_path / "snapshot"
    assert calls["repo_id"] == DEFAULT_MODEL_ID
    assert calls["local_files_only"] is True
    assert calls["allow_patterns"] == ["config.json", "model.py", "pytorch_model.bin", "README.md"]


def test_load_model_config_reads_embedding_dim(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "config.json").write_text(json.dumps({"embedding_dim": 128}), encoding="utf-8")

    config = load_model_config(snapshot)

    assert config["embedding_dim"] == 128


def test_load_cir_model_imports_snapshot_model_and_weights(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "config.json").write_text(
        json.dumps({"embedding_dim": 4, "nhead": 2, "num_layers": 1}), encoding="utf-8"
    )
    (snapshot / "model.py").write_text(
        "import torch\n"
        "class OutfitTransformerCIR(torch.nn.Module):\n"
        "    def __init__(self, embedding_dim, nhead, num_layers):\n"
        "        super().__init__()\n"
        "        self.proj = torch.nn.Linear(embedding_dim, embedding_dim)\n"
        "    def forward(self, x):\n"
        "        return self.proj(x)\n",
        encoding="utf-8",
    )
    torch.save(
        {"proj.weight": torch.eye(4), "proj.bias": torch.zeros(4)},
        snapshot / "pytorch_model.bin",
    )

    model = load_cir_model(snapshot)

    assert model.training is False
    with torch.no_grad():
        out = model(torch.ones(1, 4))
    assert out.tolist() == [[1.0, 1.0, 1.0, 1.0]]
