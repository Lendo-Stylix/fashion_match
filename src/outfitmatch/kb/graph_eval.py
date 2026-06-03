"""Graph KB quality report: diversity plus coherence regression guards."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from outfitmatch.kb.graph import edge_allowed
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits

if TYPE_CHECKING:
    from outfitmatch.kb.graph import Edge
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord


@dataclass(frozen=True)
class GraphReport:
    n_nodes: int
    n_edges: int
    degree_min: int
    degree_median: int
    degree_max: int
    coherence_violations: int
    catalog_coverage: float
    distinct_items_used: int
    n_assembled: int
    item_reuse_p95: int


def _coherence_violations(items_by_id: dict[str, ItemRecord], edges: list[Edge]) -> int:
    violations = 0
    for edge in edges:
        item_a = items_by_id.get(edge.src_id)
        item_b = items_by_id.get(edge.dst_id)
        if item_a is None or item_b is None:
            continue
        if not edge_allowed(item_a, item_b):
            violations += 1
    return violations


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int(round(0.95 * (len(ordered) - 1)))
    return ordered[index]


def evaluate_graph(
    graph: OutfitGraph,
    items: list[ItemRecord],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    config: AssemblyConfig = AssemblyConfig(),
) -> GraphReport:
    """Compute diversity and integrity metrics for the compatibility graph."""
    items_by_id = {item.item_id: item for item in items}
    degree: Counter[str] = Counter({item.item_id: 0 for item in items})
    for edge in edges:
        degree[edge.src_id] += 1
        degree[edge.dst_id] += 1
    degrees = sorted(degree.values()) or [0]

    assembled = assemble_outfits(graph, seed_ids, config=config)
    used: Counter[str] = Counter()
    for outfit in assembled:
        for item_id in outfit.item_ids:
            used[item_id] += 1

    coverage = round(len(used) / len(items), 6) if items else 0.0
    return GraphReport(
        n_nodes=len(items),
        n_edges=len(edges),
        degree_min=degrees[0],
        degree_median=int(statistics.median(degrees)),
        degree_max=degrees[-1],
        coherence_violations=_coherence_violations(items_by_id, edges),
        catalog_coverage=coverage,
        distinct_items_used=len(used),
        n_assembled=len(assembled),
        item_reuse_p95=_p95(list(used.values())),
    )


def summarize_graph_report(report: GraphReport) -> str:
    """Return a stable human-readable summary."""
    return "\n".join(
        [
            f"nodes: {report.n_nodes}",
            f"edges: {report.n_edges}",
            (
                "degree_min/median/max: "
                f"{report.degree_min}/{report.degree_median}/{report.degree_max}"
            ),
            f"coherence_violations: {report.coherence_violations}",
            f"catalog_coverage: {report.catalog_coverage:.4f}",
            f"distinct_items_used: {report.distinct_items_used}",
            f"assembled_outfits: {report.n_assembled}",
            f"item_reuse_p95: {report.item_reuse_p95}",
        ]
    )


def graph_report_json(report: GraphReport) -> str:
    """JSON form for logs or future experiment exports."""
    return json.dumps(report.__dict__, ensure_ascii=False, sort_keys=True)
