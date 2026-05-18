from __future__ import annotations

from collections.abc import Sequence

from sklearn.metrics import roc_auc_score


def fitb_accuracy(preds: Sequence[int], labels: Sequence[int]) -> float:
    if not preds:
        return 0.0
    correct = sum(int(p == y) for p, y in zip(preds, labels, strict=True))
    return round(correct / len(preds), 6)


def compatibility_auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    return round(float(roc_auc_score(list(labels), list(scores))), 6)
