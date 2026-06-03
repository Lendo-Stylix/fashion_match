"""Pairwise item compatibility scoring for the outfit graph.

Edge *existence* is decided by hard constraints in ``graph.py``
(category/gender/formality). This module only provides the edge *weight* — a
bounded ``[0, 1]`` compatibility proxy. ``HeuristicPairScorer`` is a
deterministic placeholder; swap in an OutfitTransformer-labse pairwise adapter
later via the same ``score_pair`` interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from outfitmatch.vocab import FORMALITY_RANK

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


class PairScorer(Protocol):
    """Anything that scores how well two items go together, in ``[0, 1]``."""

    def score_pair(self, a: ItemRecord, b: ItemRecord) -> float: ...


def _price_proximity(p1: int, p2: int) -> float:
    """Return ``1.0`` when equal, trending to ``0`` as prices diverge."""
    hi = max(int(p1), int(p2))
    lo = min(int(p1), int(p2))
    if hi <= 0:
        return 0.5
    return lo / hi


def _formality_closeness(a: ItemRecord, b: ItemRecord) -> float:
    """Return ``1.0`` for equal formality; ``0.5`` when either value is unknown."""
    rank_a = FORMALITY_RANK.get(a.formality)
    rank_b = FORMALITY_RANK.get(b.formality)
    if rank_a is None or rank_b is None:
        return 0.5
    scale = max(1, len(FORMALITY_RANK) - 1)
    return 1.0 - abs(rank_a - rank_b) / scale


def _color_harmony(a: ItemRecord, b: ItemRecord) -> float:
    """Shared colors score high; missing colors stay neutral, never a hard penalty."""
    colors_a = {
        str(color).strip().lower() for color in a.store.get("colors", []) if str(color).strip()
    }
    colors_b = {
        str(color).strip().lower() for color in b.store.get("colors", []) if str(color).strip()
    }
    if not colors_a or not colors_b:
        return 0.5
    return 1.0 if colors_a & colors_b else 0.4


class HeuristicPairScorer:
    """Deterministic, symmetric pairwise compatibility proxy in ``[0, 1]``."""

    def score_pair(self, a: ItemRecord, b: ItemRecord) -> float:
        price = _price_proximity(
            int(a.store.get("price_vnd") or 0),
            int(b.store.get("price_vnd") or 0),
        )
        formality = _formality_closeness(a, b)
        color = _color_harmony(a, b)
        score = 0.4 * formality + 0.35 * color + 0.25 * price
        return max(0.0, min(1.0, round(score, 6)))
