from __future__ import annotations

import torch
import torch.nn as nn


class OutfitTransformer(nn.Module):
    """OutfitTransformer (Sarkar et al. 2022, arXiv:2204.04812).

    Special tokens: [CLS] always prepended; [BODY] and [OCC] appended
    when body/occ vectors are supplied; [PREF_<group>] appended for each
    active preference group.
    Input item_embeds must already be encoded by the catalog encoder.
    """

    def __init__(self, embed_dim: int = 512,
                 n_heads: int = 8, n_layers: int = 4,
                 pref_groups: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.cls = nn.Parameter(torch.randn(1, 1, embed_dim))
        self.body_proj = nn.Linear(embed_dim, embed_dim)
        self.occ_proj = nn.Linear(embed_dim, embed_dim)
        self.pref_proj = nn.ModuleDict(
            {g: nn.Linear(embed_dim, embed_dim) for g in pref_groups})
        layer = nn.TransformerEncoderLayer(
            d_model=embed_dim, nhead=n_heads, batch_first=True,
            dim_feedforward=embed_dim * 4,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Linear(embed_dim, 1)

    def forward(
        self,
        item_embeds: torch.Tensor,   # (B, N, D)
        mask: torch.Tensor,          # (B, N) bool — True = valid item
        body: torch.Tensor | None = None,  # (B, D)
        occ: torch.Tensor | None = None,   # (B, D)
        pref: dict[str, torch.Tensor] | None = None,  # group -> (B, D)
    ) -> torch.Tensor:               # (B,) compatibility score
        b = item_embeds.size(0)
        dev = item_embeds.device
        toks = [self.cls.expand(b, -1, -1), item_embeds]
        keep = [torch.ones(b, 1, dtype=torch.bool, device=dev), mask]
        if body is not None:
            toks.append(self.body_proj(body).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        if occ is not None:
            toks.append(self.occ_proj(occ).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        if pref:
            for group, vec in pref.items():
                toks.append(self.pref_proj[group](vec).unsqueeze(1))
                keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        x = torch.cat(toks, dim=1)
        pad = ~torch.cat(keep, dim=1)
        h = self.encoder(x, src_key_padding_mask=pad)
        return self.head(h[:, 0]).squeeze(-1)
