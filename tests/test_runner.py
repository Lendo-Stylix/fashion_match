import sys

import torch
from PIL import Image

from outfitmatch.config import ExperimentConfig


def _make_stub_encoder():
    """Return an encoder whose embeddings are globally unique across batches.

    torch.eye(N, 4) resets to the same rows for every batch, causing duplicate
    image/text vectors when batch_size < dataset_size.  Instead we keep a
    per-instance call counter and offset the identity rows accordingly so the
    concatenated result is a proper N×4 identity matrix.
    """

    class _Enc:
        embed_dim = 4
        _img_counter: int = 0
        _txt_counter: int = 0

        def encode_image(self, x):
            n = len(x)
            rows = torch.eye(8, 4)[self._img_counter: self._img_counter + n]
            self._img_counter += n
            return rows

        def encode_text(self, x):
            n = len(x)
            rows = torch.eye(8, 4)[self._txt_counter: self._txt_counter + n]
            self._txt_counter += n
            return rows

    return _Enc()


def _make_stub_ds_class():
    class _DS:
        def __init__(self, *a, **k):
            pass

        def __len__(self):
            return 4

        def __getitem__(self, i):
            return {"image": Image.new("RGB", (8, 8)), "text": f"t{i}"}

    return _DS


def test_execute_zero_shot_retrieval(monkeypatch):
    cfg = ExperimentConfig.model_validate({
        "name": "smoke",
        "seed": 1,
        "task": "retrieval",
        "model": {"kind": "hf_clip", "checkpoint": "stub"},
        "dataset": {"hf_id": "stub", "max_rows": 4},
        "train": {"epochs": 0, "batch_size": 2},
    })

    stub_enc = _make_stub_encoder()
    _DS = _make_stub_ds_class()

    # Patch at the module level so lazy imports inside runner.py pick up stubs
    import outfitmatch.data.retrieval as data_mod
    import outfitmatch.encoders.factory as fac_mod

    monkeypatch.setattr(fac_mod, "build_encoder", lambda mc, device="cpu": stub_enc)
    monkeypatch.setattr(data_mod, "RetrievalDataset", _DS)

    # Ensure the lazy import inside execute() resolves to our patched modules
    monkeypatch.setitem(sys.modules, "outfitmatch.encoders.factory", fac_mod)
    monkeypatch.setitem(sys.modules, "outfitmatch.data.retrieval", data_mod)

    from outfitmatch.runner import execute

    metrics = execute(cfg, group="test", job_type="smoke")
    assert metrics["recall@1"] == 1.0


def test_execute_finetune_path_called(monkeypatch):
    cfg = ExperimentConfig.model_validate({
        "name": "ft",
        "seed": 1,
        "task": "retrieval",
        "model": {"kind": "hf_clip", "checkpoint": "stub", "finetune": True},
        "dataset": {"hf_id": "stub", "max_rows": 4},
        "train": {"epochs": 1, "batch_size": 2, "lr": 1e-4},
    })

    called = {}

    class _EncWithModel:
        embed_dim = 4

        class model:
            @staticmethod
            def parameters():
                return iter([torch.zeros(1, requires_grad=True)])

            @staticmethod
            def train():
                pass

            @staticmethod
            def eval():
                pass

        def encode_image(self, x):
            return torch.eye(len(x), 4)

        def encode_text(self, x):
            return torch.eye(len(x), 4)

    stub_enc = _EncWithModel()
    _DS = _make_stub_ds_class()

    import outfitmatch.data.retrieval as data_mod
    import outfitmatch.encoders.factory as fac_mod
    import outfitmatch.train.contrastive as contrastive_mod

    monkeypatch.setattr(fac_mod, "build_encoder", lambda mc, device="cpu": stub_enc)
    monkeypatch.setattr(data_mod, "RetrievalDataset", _DS)
    monkeypatch.setattr(
        contrastive_mod,
        "finetune_encoder",
        lambda *a, **k: called.setdefault("ft", True),
    )

    monkeypatch.setitem(sys.modules, "outfitmatch.encoders.factory", fac_mod)
    monkeypatch.setitem(sys.modules, "outfitmatch.data.retrieval", data_mod)
    monkeypatch.setitem(sys.modules, "outfitmatch.train.contrastive", contrastive_mod)

    from outfitmatch.runner import execute

    execute(cfg, group="t", job_type="ft")
    assert called.get("ft") is True
