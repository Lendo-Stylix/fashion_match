import torch

from outfitmatch.metrics.retrieval import mean_average_precision, recall_at_k


def test_recall_at_k_perfect_diagonal():
    sims = torch.eye(5)
    assert recall_at_k(sims, k=1) == 1.0


def test_recall_at_k_partial():
    # row 0 correct item is idx 0, but row 0 scores: col1=0.9 highest
    sims = torch.tensor([[0.1, 0.9, 0.2], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert recall_at_k(sims, k=1) == round(2 / 3, 6)
    assert recall_at_k(sims, k=2) == 1.0


def test_map_is_between_zero_and_one():
    sims = torch.rand(8, 8)
    m = mean_average_precision(sims)
    assert 0.0 <= m <= 1.0


def test_recall_at_k_all_wrong():
    # 3 queries, correct is always diagonal but scores arranged so k=1 always wrong
    sims = torch.tensor([
        [0.1, 0.9, 0.5],
        [0.9, 0.1, 0.5],
        [0.5, 0.9, 0.1],
    ])
    assert recall_at_k(sims, k=1) == 0.0
    assert recall_at_k(sims, k=2) == round(1 / 3, 6)
