import torch

from outfitmatch.train.composer import OutfitTransformer


def test_forward_returns_compatibility_score():
    m = OutfitTransformer(embed_dim=16, n_heads=2, n_layers=2)
    item_embeds = torch.randn(2, 5, 16)
    mask = torch.ones(2, 5, dtype=torch.bool)
    score = m(item_embeds, mask)
    assert score.shape == (2,)
    assert torch.isfinite(score).all()


def test_body_occ_tokens_change_output():
    torch.manual_seed(0)
    m = OutfitTransformer(embed_dim=16, n_heads=2, n_layers=2)
    items = torch.randn(1, 3, 16)
    mask = torch.ones(1, 3, dtype=torch.bool)
    base = m(items, mask)
    cond = m(items, mask, body=torch.randn(1, 16), occ=torch.randn(1, 16))
    assert not torch.allclose(base, cond)
