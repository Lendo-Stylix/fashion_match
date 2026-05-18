from __future__ import annotations

from abc import ABC, abstractmethod

import torch
from PIL.Image import Image


class BaseEncoder(ABC):
    """Abstract encoder: maps images/text to L2-normalised embeddings."""

    embed_dim: int  # set in __init__

    @abstractmethod
    def encode_image(self, images: list[Image]) -> torch.Tensor:
        """Returns (N, embed_dim) L2-normalised tensor."""
        ...

    @abstractmethod
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        """Returns (N, embed_dim) L2-normalised tensor."""
        ...
