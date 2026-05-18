from __future__ import annotations

from outfitmatch.config import ModelConfig
from outfitmatch.encoders.base import BaseEncoder


def build_encoder(mc: ModelConfig, device: str = "cpu") -> BaseEncoder:
    """Instantiate the encoder specified by ModelConfig.

    Use this everywhere — never instantiate encoder classes directly outside tests.
    """
    if mc.kind == "hf_clip":
        from outfitmatch.encoders.hf_clip_encoder import HfClipEncoder

        return HfClipEncoder(mc.checkpoint, device=device)
    if mc.kind == "open_clip":
        from outfitmatch.encoders.openclip_encoder import OpenClipEncoder

        return OpenClipEncoder(mc.checkpoint, device=device)
    raise ValueError(f"unknown encoder kind: {mc.kind!r}")
