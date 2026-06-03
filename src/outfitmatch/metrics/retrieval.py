"""Retrieval metrics for the graph KB.

``recall_at_k`` is generic. ``fitb_recall_at_k`` is a graph-native
self-consistency Recall@K: mask one item from an assembled outfit, rank the
clique-valid candidates in that category by mean edge weight, and check whether
true item is recovered in the top-K.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.traversal import AssembledOutfit


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Return |top-k ∩ relevant| / |relevant|, or 0.0 when relevant is empty."""
    if not relevant:
        return 0.0
    topk = set(retrieved[:k])
    return round(len(topk & relevant) / len(relevant), 6)


def _rank_completions(
    graph: OutfitGraph,
    context_ids: list[str],
    masked_category: str,
) -> list[str]:
    """Rank clique-valid candidates in ``masked_category`` by mean edge weight."""
    if not context_ids:
        return []

    present = set(context_ids)
    candidate_ids: set[str] = set()
    for context_id in context_ids:
        for neighbor_id, _weight in graph.neighbors(context_id, masked_category):
            if neighbor_id not in present:
                candidate_ids.add(neighbor_id)

    scored: list[tuple[str, float]] = []
    for candidate_id in candidate_ids:
        weights = [graph.edge_weight(candidate_id, context_id) for context_id in context_ids]
        if any(weight is None for weight in weights):
            continue
        mean_weight = sum(weight for weight in weights if weight is not None) / len(weights)
        scored.append((candidate_id, mean_weight))

    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return [candidate_id for candidate_id, _ in scored]


def fitb_recall_at_k(
    graph: OutfitGraph,
    outfits: list[AssembledOutfit],
    *,
    k: int = 5,
    masked_category: str = "shoes",
) -> float:
    """Fraction of eligible outfits whose masked item is recovered in the top-k."""
    hits = 0
    eligible = 0
    for outfit in outfits:
        masked = [item for item in outfit.items if item.category == masked_category]
        context = [item for item in outfit.items if item.category != masked_category]
        if not masked or not context:
            continue

        eligible += 1
        true_id = masked[0].item_id
        ranked = _rank_completions(graph, [item.item_id for item in context], masked_category)
        if true_id in ranked[:k]:
            hits += 1

    return round(hits / eligible, 6) if eligible else 0.0
