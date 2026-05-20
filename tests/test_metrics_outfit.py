import torch

from outfitmatch.metrics.outfit import compatibility_auc, fitb_accuracy, preference_pairwise_accuracy


def test_fitb_accuracy_all_correct():
    assert fitb_accuracy([1, 0, 3], [1, 0, 3]) == 1.0


def test_fitb_accuracy_half():
    assert fitb_accuracy([0, 1], [0, 0]) == 0.5


def test_fitb_accuracy_empty():
    assert fitb_accuracy([], []) == 0.0


def test_compatibility_auc_separable():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    assert compatibility_auc(scores, labels) == 1.0


def test_compatibility_auc_random():
    scores = [0.5, 0.5, 0.5, 0.5]
    labels = [1, 0, 1, 0]
    assert 0.0 <= compatibility_auc(scores, labels) <= 1.0


def test_pairwise_accuracy_counts_correct_orderings():
    s_pos = torch.tensor([1.0, 0.2, 3.0])
    s_neg = torch.tensor([0.0, 0.5, 1.0])      # row 1 is wrong (0.2 < 0.5)
    assert preference_pairwise_accuracy(s_pos, s_neg) == round(2 / 3, 6)
