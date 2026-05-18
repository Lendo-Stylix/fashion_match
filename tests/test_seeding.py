from outfitmatch.seeding import set_seed


def test_set_seed_is_deterministic():
    import random

    set_seed(123)
    a = random.random()
    set_seed(123)
    assert random.random() == a


def test_set_seed_changes_torch_state():
    import torch

    set_seed(0)
    t1 = torch.rand(3)
    set_seed(0)
    t2 = torch.rand(3)
    assert torch.allclose(t1, t2)
