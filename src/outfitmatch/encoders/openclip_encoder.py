from __future__ import annotations

import open_clip
import torch
from PIL.Image import Image

from outfitmatch.encoders.base import BaseEncoder


class OpenClipEncoder(BaseEncoder):
    """Marqo FashionSigLIP / FashionCLIP via open_clip hf-hub loading.

    Checkpoint format: "hf-hub:Marqo/marqo-fashionSigLIP"
    """

    def __init__(self, checkpoint: str, device: str = "cpu") -> None:
        self.device = device
        model, _, preprocess = open_clip.create_model_and_transforms(checkpoint)
        self.model = model.to(device).eval()
        self.preprocess = preprocess
        self.tokenizer = open_clip.get_tokenizer(checkpoint)
        with torch.no_grad():
            d = self.model.encode_text(self.tokenizer(["x"]).to(device)).shape[1]
        self.embed_dim: int = d

    @torch.no_grad()
    def encode_image(self, images: list[Image]) -> torch.Tensor:
        batch = torch.stack([self.preprocess(im) for im in images]).to(self.device)
        v = self.model.encode_image(batch)
        return v / v.norm(dim=1, keepdim=True)

    @torch.no_grad()
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        toks = self.tokenizer(texts).to(self.device)
        v = self.model.encode_text(toks)
        return v / v.norm(dim=1, keepdim=True)
