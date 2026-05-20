import math

import torch

from outfitmatch.train.preference import pairwise_bt_loss


def test_zero_margin_loss_is_log2():
    s = torch.zeros(4)
    assert abs(pairwise_bt_loss(s, s).item() - math.log(2)) < 1e-5


def test_loss_decreases_as_preferred_pulls_ahead():
    neg = torch.zeros(2)
    small_margin = pairwise_bt_loss(torch.full((2,), 0.5), neg)
    big_margin = pairwise_bt_loss(torch.full((2,), 3.0), neg)
    assert big_margin < small_margin


def test_loss_is_scalar_and_finite():
    loss = pairwise_bt_loss(torch.randn(8), torch.randn(8))
    assert loss.ndim == 0 and torch.isfinite(loss)
