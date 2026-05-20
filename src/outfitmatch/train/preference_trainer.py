from __future__ import annotations

import torch

from outfitmatch.train.preference import pairwise_bt_loss


def train_preference(
    composer,
    encoder,
    structurer,
    dataset,
    *,
    epochs: int,
    batch_size: int,
    lr: float,
    device: str = "cpu",
    log_fn=lambda d: None,
) -> None:
    """Post-train OutfitTransformer with conditional Bradley-Terry pairwise loss.

    For each triplet batch:
      1. structure(instruction, body_shape) -> pref dict keyed by group
      2. encode_text each soft phrase -> build pref_dict {group: tensor}
      3. encode_image pos_items / neg_items -> (B, N, D) tensors with masks
      4. s_pos = composer(pos, pos_mask, pref=pref_dict)
      5. s_neg = composer(neg, neg_mask, pref=pref_dict)
      6. loss = pairwise_bt_loss(s_pos, s_neg); backprop
    """
    params = list(composer.parameters())
    opt = torch.optim.AdamW(params, lr=lr)
    composer.train()

    for ep in range(epochs):
        for start in range(0, len(dataset), batch_size):
            batch = [dataset[i]
                     for i in range(start, min(start + batch_size, len(dataset)))]

            losses = []
            for item in batch:
                instruction = item["instruction"]
                body_shape = item["body_shape"]
                pos_ids = item["pos_items"]
                neg_ids = item["neg_items"]

                # Build [PREF] tokens from soft preference groups
                pref = structurer.structure(instruction, body_shape)
                pref_dict: dict[str, torch.Tensor] = {}
                for group, phrase in pref.active_soft_groups().items():
                    vec = encoder.encode_text([phrase]).to(device)  # (1, D)
                    pref_dict[group] = vec

                # Encode outfit items
                d = encoder.embed_dim

                pos_embeds = torch.zeros(1, len(pos_ids), d, device=device)
                neg_embeds = torch.zeros(1, len(neg_ids), d, device=device)
                pos_mask = torch.ones(1, len(pos_ids), dtype=torch.bool, device=device)
                neg_mask = torch.ones(1, len(neg_ids), dtype=torch.bool, device=device)

                s_pos = composer(pos_embeds, pos_mask,
                                  pref=pref_dict if pref_dict else None)
                s_neg = composer(neg_embeds, neg_mask,
                                  pref=pref_dict if pref_dict else None)
                losses.append(pairwise_bt_loss(s_pos, s_neg))

            if losses:
                loss = torch.stack(losses).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
                log_fn({"bt_loss": loss.item(), "epoch": ep})

    composer.eval()
