import torch

from outfitmatch.train.contrastive import siglip_loss


def test_siglip_loss_lower_when_aligned():
    img = torch.eye(4)
    good = siglip_loss(img, img.clone(), t=1.0, b=0.0)
    bad = siglip_loss(img, img.flip(0), t=1.0, b=0.0)
    assert good < bad
