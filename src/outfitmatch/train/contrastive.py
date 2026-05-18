from __future__ import annotations

from collections.abc import Callable

import torch
import torch.nn.functional as F


def siglip_loss(img: torch.Tensor, txt: torch.Tensor,
                t: float = 10.0, b: float = -10.0) -> torch.Tensor:
    """Sigmoid contrastive loss (SigLIP, Zhai et al. 2023 arXiv:2303.15343).

    img, txt: (N, D) — will be L2-normalised internally.
    t: learned temperature proxy (log scale, passed as scalar here).
    b: learned bias proxy.
    """
    img = F.normalize(img, dim=1)
    txt = F.normalize(txt, dim=1)
    logits = (img @ txt.T) * t + b
    n = img.size(0)
    labels = 2 * torch.eye(n, device=img.device) - 1  # +1 diag, -1 off-diag
    return -F.logsigmoid(labels * logits).mean()


def finetune_encoder(
    encoder,
    dataset,
    *,
    epochs: int,
    batch_size: int,
    lr: float,
    device: str = "cpu",
    log_fn: Callable[[dict], None] = lambda d: None,
) -> None:
    """Fine-tune an encoder in-place with SigLIP contrastive loss.

    Modifies encoder.model weights. Encoder is put back in eval() after training.
    """
    params = [p for p in encoder.model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr)
    encoder.model.train()
    step = 0
    for ep in range(epochs):
        for start in range(0, len(dataset), batch_size):
            end = min(start + batch_size, len(dataset))
            rows = [dataset[i] for i in range(start, end)]
            iv = encoder.encode_image([r["image"] for r in rows])
            tv = encoder.encode_text([r["text"] for r in rows])
            loss = siglip_loss(iv, tv)
            opt.zero_grad()
            loss.backward()
            opt.step()
            log_fn({"train/loss": loss.item(), "epoch": ep, "step": step})
            step += 1
    encoder.model.eval()
