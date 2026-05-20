from __future__ import annotations

from collections.abc import Sequence

import torch
from sklearn.metrics import roc_auc_score


def fitb_accuracy(preds: Sequence[int], labels: Sequence[int]) -> float:
    if not preds:
        return 0.0
    correct = sum(int(p == y) for p, y in zip(preds, labels, strict=True))
    return round(correct / len(preds), 6)


def compatibility_auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    return round(float(roc_auc_score(list(labels), list(scores))), 6)


def preference_pairwise_accuracy(
    score_pos: torch.Tensor, score_neg: torch.Tensor
) -> float:
    """Fraction of pairs where the positive outfit scores higher than the negative.

    Args:
        score_pos: (N,) tensor of composer scores for preferred outfits.
        score_neg: (N,) tensor of composer scores for rejected outfits.

    Returns:
        Accuracy in [0, 1].
    """
    if score_pos.numel() == 0:
        return 0.0
    correct = (score_pos > score_neg).float().sum().item()
    return round(correct / score_pos.numel(), 6)


def instruction_flip_consistency(scores_a: torch.Tensor, scores_b: torch.Tensor) -> float:
    """For contrastive-flip pairs (same outfits, flipped instruction),
    fraction where the model's preferred outfit also flips."""
    flipped = scores_a.argmax(dim=-1) != scores_b.argmax(dim=-1)
    return round(flipped.float().mean().item(), 6)
