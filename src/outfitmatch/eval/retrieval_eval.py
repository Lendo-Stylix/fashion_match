from __future__ import annotations

import torch

from outfitmatch.metrics.retrieval import mean_average_precision, recall_at_k


def evaluate_retrieval(encoder, dataset, batch_size: int = 64) -> dict[str, float]:
    """Compute text→image retrieval metrics over an entire dataset.

    Assumes correct match for query i is candidate i (diagonal ground truth).
    Returns: recall@1, recall@5, recall@10, map
    """
    img_vecs, txt_vecs = [], []
    for start in range(0, len(dataset), batch_size):
        end = min(start + batch_size, len(dataset))
        rows = [dataset[i] for i in range(start, end)]
        img_vecs.append(encoder.encode_image([r["image"] for r in rows]))
        txt_vecs.append(encoder.encode_text([r["text"] for r in rows]))
    iv = torch.cat(img_vecs)
    tv = torch.cat(txt_vecs)
    sims = tv @ iv.T
    return {
        "recall@1": recall_at_k(sims, 1),
        "recall@5": recall_at_k(sims, min(5, sims.size(0))),
        "recall@10": recall_at_k(sims, min(10, sims.size(0))),
        "map": mean_average_precision(sims),
    }
