from __future__ import annotations

import torch


def recall_at_k(sims: torch.Tensor, k: int) -> float:
    """sims[i][j] = similarity(query_i, candidate_j). Correct match is j == i."""
    n = sims.size(0)
    topk = sims.topk(k, dim=1).indices
    gold = torch.arange(n).unsqueeze(1)
    hits = (topk == gold).any(dim=1).float().sum().item()
    return round(hits / n, 6)


def mean_average_precision(sims: torch.Tensor) -> float:
    n = sims.size(0)
    ranks = sims.argsort(dim=1, descending=True)
    gold = torch.arange(n)
    ap = []
    for i in range(n):
        pos = (ranks[i] == gold[i]).nonzero(as_tuple=True)[0].item()
        ap.append(1.0 / (pos + 1))
    return round(sum(ap) / n, 6)
