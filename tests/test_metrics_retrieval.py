import torch

from outfitmatch.metrics.retrieval import mean_average_precision, recall_at_k


def test_recall_at_k_perfect_diagonal():
    sims = torch.eye(5)
    assert recall_at_k(sims, k=1) == 1.0


def test_recall_at_k_partial():
    # row 0: scores [0.1, 0.9, 0.2] → correct=0 is never in top-2 (top-2={1,2})
    # rows 1, 2 have correct item as top-1
    sims = torch.tensor([[0.1, 0.9, 0.2], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert recall_at_k(sims, k=1) == round(2 / 3, 6)
    assert recall_at_k(sims, k=2) == round(2 / 3, 6)  # row 0 still misses


def test_map_is_between_zero_and_one():
    sims = torch.rand(8, 8)
    m = mean_average_precision(sims)
    assert 0.0 <= m <= 1.0


def test_recall_at_k_all_wrong():
    # row 0: top-2={1,2}, correct=0 — miss. row 1: top-2={0,2}, correct=1 — miss.
    # row 2: top-2={1,0}, correct=2 — miss. All miss at both k=1 and k=2.
    sims = torch.tensor([
        [0.1, 0.9, 0.5],
        [0.9, 0.1, 0.5],
        [0.5, 0.9, 0.1],
    ])
    assert recall_at_k(sims, k=1) == 0.0
    assert recall_at_k(sims, k=2) == 0.0
