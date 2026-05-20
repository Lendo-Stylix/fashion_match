from __future__ import annotations

import torch
import torch.nn.functional as F


def pairwise_bt_loss(score_pos: torch.Tensor,
                      score_neg: torch.Tensor) -> torch.Tensor:
    """Conditional Bradley-Terry: -log sigmoid(s+ - s-).

    Both inputs are (B,) composer scores computed with the SAME [PREF]
    tokens; minimising this ranks the preferred outfit above the rejected
    one *under that instruction*.
    """
    return -F.logsigmoid(score_pos - score_neg).mean()
