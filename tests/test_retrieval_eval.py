import torch
from PIL import Image

from outfitmatch.eval.retrieval_eval import evaluate_retrieval


class _StubEncoder:
    embed_dim = 4

    def encode_image(self, images):
        return torch.eye(len(images), 4)

    def encode_text(self, texts):
        return torch.eye(len(texts), 4)


class _StubDS:
    def __len__(self):
        return 4

    def __getitem__(self, i):
        return {"image": Image.new("RGB", (8, 8)), "text": f"t{i}"}


def test_evaluate_retrieval_returns_metrics():
    # batch_size == dataset size so encode_image/encode_text receive all 4 items
    # at once, producing eye(4,4) — a proper identity matrix with no duplicate rows.
    out = evaluate_retrieval(_StubEncoder(), _StubDS(), batch_size=4)
    assert out["recall@1"] == 1.0
    assert "recall@5" in out and "recall@10" in out and "map" in out
