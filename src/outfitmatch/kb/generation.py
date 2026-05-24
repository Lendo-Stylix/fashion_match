"""Outfit combination generation.

Two methods (see Kien_truc_v3.1.md §3.4 Bước 3):
  - fitb_beam:      Iterative FITB + Top-K sampling + Beam Search (beam=3). 70% of KB.
  - random_scored:  Random combos per category rule, pre-filtered by OT scoring. 30% of KB.

Category rule: (1 top + 1 bottom + 1 shoes) OR (1 dress + 1 shoes);
               outerwear / bag / accessory optional.

Implemented in Sprint 3-4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord, OutfitRecord


def generate_fitb_beam(
    items_by_category: dict[str, list[ItemRecord]],
    encoder: Any,
    n_outfits: int = 1000,
    beam_size: int = 3,
    top_k: int = 5,
) -> list[OutfitRecord]:
    """Generate outfit candidates via Iterative FITB + Beam Search.

    Each candidate gets a placeholder compatibility_score=0.0.
    Run scoring.rescore_outfits() after this step.
    """
    raise NotImplementedError("Implement in Sprint 3-4: FITB+Beam generation")


def generate_random_scored(
    items_by_category: dict[str, list[ItemRecord]],
    encoder: Any,
    n_candidates: int = 5000,
) -> list[OutfitRecord]:
    """Generate outfit candidates via random sampling (pre-filter by OT scoring).

    Uses OT score as the pre-filter — not CLIP cosine similarity (wrong metric).
    """
    raise NotImplementedError("Implement in Sprint 3-4: random sampling + OT pre-filter")
