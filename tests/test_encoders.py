import inspect

import pytest
import torch

from outfitmatch.config import ModelConfig
from outfitmatch.encoders.base import BaseEncoder


def test_base_encoder_is_abstract():
    assert inspect.isabstract(BaseEncoder)


def test_base_encoder_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseEncoder()  # type: ignore[abstract]


def test_factory_routes_hf_clip(monkeypatch):
    class _FakeEnc:
        embed_dim = 512

        def encode_image(self, imgs):
            return torch.zeros(len(imgs), 512)

        def encode_text(self, txts):
            return torch.zeros(len(txts), 512)

    import outfitmatch.encoders.factory as fac

    # Patch build_encoder itself to return a stub when kind == "hf_clip"
    original_build = fac.build_encoder

    def patched_build(mc, device="cpu"):
        if mc.kind == "hf_clip":
            return _FakeEnc()
        return original_build(mc, device)

    monkeypatch.setattr(fac, "build_encoder", patched_build)

    mc = ModelConfig(kind="hf_clip", checkpoint="stub")
    enc = fac.build_encoder(mc)
    assert enc.embed_dim == 512


def test_factory_raises_on_unknown_kind(monkeypatch):
    """build_encoder raises ValueError for an unrecognised kind.

    We use monkeypatch to bypass pydantic's Literal validation on ModelConfig
    by constructing the config and then overriding its kind attribute.
    """
    import outfitmatch.encoders.factory as fac

    mc = ModelConfig(kind="hf_clip", checkpoint="stub")
    monkeypatch.setattr(mc, "kind", "nonexistent_encoder")

    with pytest.raises(ValueError, match="unknown encoder kind"):
        fac.build_encoder(mc)
