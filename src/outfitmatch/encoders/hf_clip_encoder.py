from __future__ import annotations

import torch
from PIL.Image import Image
from transformers import CLIPModel, CLIPProcessor

from outfitmatch.encoders.base import BaseEncoder


class HfClipEncoder(BaseEncoder):
    """openai/clip-* and patrickjohncyh/fashion-clip via HuggingFace transformers."""

    def __init__(self, checkpoint: str, device: str = "cpu") -> None:
        self.device = device
        self.model = CLIPModel.from_pretrained(checkpoint).to(device).eval()
        self.proc = CLIPProcessor.from_pretrained(checkpoint)
        self.embed_dim: int = self.model.config.projection_dim

    @torch.no_grad()
    def encode_image(self, images: list[Image]) -> torch.Tensor:
        inp = self.proc(images=images, return_tensors="pt").to(self.device)
        v = self.model.get_image_features(**inp)
        return v / v.norm(dim=1, keepdim=True)

    @torch.no_grad()
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        inp = self.proc(text=texts, return_tensors="pt",
                         padding=True, truncation=True).to(self.device)
        v = self.model.get_text_features(**inp)
        return v / v.norm(dim=1, keepdim=True)
