"""Assemble outfits by traversing the compatibility graph.

An outfit is a clique in the graph: every chosen pair shares an edge, so the
sub-project 1 gender/formality invariants hold automatically. Anchors are tops
and dresses; a top must gain a bottom, while shoes/outerwear/bag/accessory stay
optional. Shoeless outfits are valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord

OPTIONAL_CATEGORIES: tuple[str, ...] = ("shoes", "outerwear", "bag", "accessory")


@dataclass(frozen=True)
class AssemblyConfig:
    """Traversal knobs for deterministic sparse-graph assembly."""

    beam: int = 3
    max_optional: int = 3


@dataclass(frozen=True)
class AssembledOutfit:
    """A graph-assembled outfit before conversion to OutfitRecord."""

    items: list[ItemRecord]
    score: float

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.items)


def _mean_pairwise(graph: OutfitGraph, items: list[ItemRecord]) -> float:
    """Mean edge weight over all pairs, or ``0.0`` if any pair lacks an edge."""
    pairs = list(combinations(items, 2))
    if not pairs:
        return 0.0

    weights: list[float] = []
    for left, right in pairs:
        weight = graph.edge_weight(left.item_id, right.item_id)
        if weight is None:
            return 0.0
        weights.append(weight)
    return round(sum(weights) / len(weights), 6)


def _is_clique_extension(graph: OutfitGraph, items: list[ItemRecord], candidate_id: str) -> bool:
    """Whether ``candidate_id`` connects to every current item in ``items``."""
    return all(graph.edge_weight(item.item_id, candidate_id) is not None for item in items)


def _best_clique_neighbor(
    graph: OutfitGraph,
    items: list[ItemRecord],
    partner_category: str,
) -> ItemRecord | None:
    """Best neighbor from the anchor that still forms a clique with all items."""
    anchor_id = items[0].item_id
    present_ids = {item.item_id for item in items}
    for candidate_id, _weight in graph.neighbors(anchor_id, partner_category):
        if candidate_id in present_ids:
            continue
        if _is_clique_extension(graph, items, candidate_id):
            return graph.item(candidate_id)
    return None


def _with_optional_items(
    graph: OutfitGraph,
    items: list[ItemRecord],
    *,
    config: AssemblyConfig,
) -> list[ItemRecord]:
    """Greedily add at most one clique-safe item per optional category."""
    chosen = list(items)
    added = 0
    for category in OPTIONAL_CATEGORIES:
        if added >= config.max_optional:
            break
        candidate = _best_clique_neighbor(graph, chosen, category)
        if candidate is None:
            continue
        chosen.append(candidate)
        added += 1
    return chosen


def assemble_from_seed(
    graph: OutfitGraph,
    seed_id: str,
    *,
    config: AssemblyConfig = AssemblyConfig(),
) -> list[AssembledOutfit]:
    """Assemble up to ``beam`` outfits from one seed item."""
    try:
        seed = graph.item(seed_id)
    except KeyError:
        return []

    if seed.category == "top":
        outfits: list[AssembledOutfit] = []
        bottom_ids = [neighbor_id for neighbor_id, _ in graph.neighbors(seed_id, "bottom")]
        for bottom_id in bottom_ids[: max(1, config.beam)]:
            items = _with_optional_items(graph, [seed, graph.item(bottom_id)], config=config)
            outfits.append(AssembledOutfit(items=items, score=_mean_pairwise(graph, items)))
        return outfits

    if seed.category == "dress":
        items = _with_optional_items(graph, [seed], config=config)
        return [AssembledOutfit(items=items, score=_mean_pairwise(graph, items))]

    return []


def assemble_outfits(
    graph: OutfitGraph,
    seed_ids: list[str],
    *,
    config: AssemblyConfig = AssemblyConfig(),
) -> list[AssembledOutfit]:
    """Assemble, deduplicate, and rank outfits from multiple seeds."""
    by_key: dict[tuple[str, ...], AssembledOutfit] = {}
    for seed_id in seed_ids:
        for outfit in assemble_from_seed(graph, seed_id, config=config):
            key = tuple(sorted(outfit.item_ids))
            previous = by_key.get(key)
            if previous is None or outfit.score > previous.score:
                by_key[key] = outfit
    return sorted(by_key.values(), key=lambda outfit: (outfit.score, outfit.item_ids), reverse=True)
