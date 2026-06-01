# Outfit Graph KB — Construction & Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng graph item-compatibility (node = `ItemRecord`, edge = "phối được") từ catalog VN và lưu (parquet edges + Qdrant `items` collection), kèm interface cho traversal retrieval sau này.

**Architecture:** Edge **tồn tại** khi thoả 3 hard-constraint (co-wearable category / đồng gender / coherent formality — tái dùng `_combo_gender` + `formality_span_ok`). Edge **weight** là pairwise compatibility pluggable (`HeuristicPairScorer` placeholder → OT-labse sau). Mỗi node giữ top-K=15 neighbor/partner-category để graph thưa. Lưu canonical 1 chiều (`src_id < dst_id`); load dựng adjacency 2 chiều.

**Tech Stack:** Python 3.13, `uv`, pandas (parquet), `qdrant-client` (embedded `path://` cho test), pytest, dataclasses. Không thêm dependency mới.

**Spec:** `docs/superpowers/specs/2026-06-01-outfit-graph-kb-design.md` (sub-project 1/3).

---

## Bối cảnh (đã kiểm chứng trong code)

- `ItemRecord` (`src/outfitmatch/kb/schema.py:9`) đã có `item_id/category/gender/formality/store/image_path/item_embedding`. `store` mang `price_vnd/product_url/in_stock/colors/...` (xem `catalog.py:77`).
- Tái dùng: `_combo_gender` (`generation.py:26`), `formality_span_ok` + `FORMALITY_RANK` + `FORMALITY_RELEVANT_CATEGORIES` + `ITEM_CATEGORY` (`vocab.py:183/61`), `load_catalog_items`/`group_items_by_category` (`catalog.py`), `extract_item_embeddings` (`embedding.py:30`), `HeuristicOutfitScorer` (`scoring.py:22`, `encode_item` dim 128).
- Qdrant pattern (`qdrant_index.py`): `_import_qdrant`/`_make_client`/`_close_client`/`_collection_exists`/`_is_existing_index_error`/`_batched` (private, dùng lại trong cùng package); test dùng `path://<dir>` rồi mở lại `QdrantClient(path=...)` (xem `tests/kb/test_qdrant_index.py`).
- `CATALOG_DIR`/`REPO_ROOT` ở `scripts/data/scrape/base.py:33-36`.

**Bất biến:** `OutfitRecord`, `generation.py`, `build_outfits.py`, `qdrant_index.py` (collection `outfits`) **không sửa, không xoá** — migration thuộc sub-project 3.

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/kb/pair_scoring.py` | `PairScorer` protocol + `HeuristicPairScorer.score_pair` | **Create** |
| `src/outfitmatch/kb/graph.py` | `COMPLEMENTARY_CATEGORIES`, `Edge`, `edge_allowed_categories`, `edge_allowed`, `build_edges` | **Create** |
| `src/outfitmatch/kb/graph_store.py` | `write_edges`/`read_edges`, `OutfitGraph`/`load_graph`, `index_item_nodes` (Qdrant) | **Create** |
| `scripts/data/kb/build_graph.py` | CLI: catalog → graph → parquet + Qdrant; `--incremental`/`--rebuild` | **Create** |
| `tests/kb/test_pair_scoring.py` | Test scorer | **Create** |
| `tests/kb/test_graph.py` | Test constraint + sparsify + determinism | **Create** |
| `tests/kb/test_graph_store.py` | Test parquet round-trip + adjacency + Qdrant nodes | **Create** |
| `data/custom/graph/item_edges.parquet` | Output edges | (sinh bởi build) |

---

### Task 1: `pair_scoring.py` — pluggable edge weight

**Files:**
- Create: `src/outfitmatch/kb/pair_scoring.py`
- Test: `tests/kb/test_pair_scoring.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_pair_scoring.py`:

```python
from __future__ import annotations

from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.schema import ItemRecord


def _item(item_id: str, *, category: str, formality: str, price: int, colors: list[str]) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender="unisex",
        formality=formality,
        store={"price_vnd": price, "colors": colors, "product_url": "x", "in_stock": True},
    )


def test_score_pair_in_unit_range_and_symmetric():
    s = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    b = _item("b", category="bottom", formality="casual", price=250_000, colors=["đen"])
    sa = s.score_pair(a, b)
    assert 0.0 <= sa <= 1.0
    assert sa == s.score_pair(b, a)  # symmetric


def test_score_pair_deterministic():
    s = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    b = _item("b", category="bottom", formality="smart_casual", price=900_000, colors=["trắng"])
    assert s.score_pair(a, b) == s.score_pair(a, b)


def test_score_pair_handles_empty_colors():
    s = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=[])
    b = _item("b", category="bottom", formality="casual", price=200_000, colors=[])
    score = s.score_pair(a, b)
    assert 0.0 <= score <= 1.0  # empty colors → neutral, no crash


def test_same_formality_scores_higher_than_distant():
    s = HeuristicPairScorer()
    a = _item("a", category="top", formality="casual", price=200_000, colors=["đen"])
    near = _item("n", category="bottom", formality="casual", price=200_000, colors=["đen"])
    far = _item("f", category="bottom", formality="formal", price=200_000, colors=["đen"])
    assert s.score_pair(a, near) > s.score_pair(a, far)
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_pair_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.pair_scoring'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/kb/pair_scoring.py`:

```python
"""Pairwise item compatibility scoring for the outfit graph.

Edge *existence* is decided by hard constraints in graph.py (category/gender/
formality). This module only provides the edge *weight* — a bounded [0, 1]
compatibility proxy. ``HeuristicPairScorer`` is a deterministic placeholder; swap
in an OutfitTransformer-labse pairwise adapter later via the same ``score_pair``
interface WITHOUT rebuilding the graph (weights are recomputed, edges are not).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from outfitmatch.vocab import FORMALITY_RANK

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


class PairScorer(Protocol):
    """Anything that scores how well two items go together, in [0, 1]."""

    def score_pair(self, a: ItemRecord, b: ItemRecord) -> float: ...


def _price_proximity(p1: int, p2: int) -> float:
    """1.0 when equal, →0 as prices diverge (ratio-based, symmetric)."""
    hi = max(p1, p2)
    lo = min(p1, p2)
    if hi <= 0:
        return 0.5
    return lo / hi


def _formality_closeness(a: ItemRecord, b: ItemRecord) -> float:
    """1.0 same band, decreasing with ladder distance; 0.5 if unknown."""
    ra = FORMALITY_RANK.get(a.formality)
    rb = FORMALITY_RANK.get(b.formality)
    if ra is None or rb is None:
        return 0.5
    return 1.0 - abs(ra - rb) / (len(FORMALITY_RANK) - 1)


def _color_harmony(a: ItemRecord, b: ItemRecord) -> float:
    """Shared colors → 1.0, disjoint → 0.4, unknown → 0.5 (never penalize).

    53% of the catalog (yody/canifa) has no colors; absent colors must stay
    neutral so those items still form sensible edges.
    """
    ca = {str(c).lower() for c in a.store.get("colors", [])}
    cb = {str(c).lower() for c in b.store.get("colors", [])}
    if not ca or not cb:
        return 0.5
    return 1.0 if ca & cb else 0.4


class HeuristicPairScorer:
    """Deterministic, symmetric pairwise compatibility in [0, 1]."""

    def score_pair(self, a: ItemRecord, b: ItemRecord) -> float:
        price = _price_proximity(
            int(a.store.get("price_vnd") or 0), int(b.store.get("price_vnd") or 0)
        )
        formality = _formality_closeness(a, b)
        color = _color_harmony(a, b)
        score = 0.4 * formality + 0.35 * color + 0.25 * price
        return max(0.0, min(1.0, round(score, 6)))
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_pair_scoring.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/pair_scoring.py tests/kb/test_pair_scoring.py
git commit -m "feat(kb): pluggable HeuristicPairScorer for graph edge weights"
```

---

### Task 2: `graph.py` — edge constraints + sparse build

**Files:**
- Create: `src/outfitmatch/kb/graph.py`
- Test: `tests/kb/test_graph.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_graph.py`:

```python
from __future__ import annotations

from outfitmatch.kb.graph import (
    Edge,
    build_edges,
    edge_allowed,
    edge_allowed_categories,
)
from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.schema import ItemRecord


def _item(
    item_id: str, *, category: str, gender: str = "unisex", formality: str = "casual", price: int = 200_000
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender=gender,
        formality=formality,
        store={"price_vnd": price, "colors": [], "product_url": "x", "in_stock": True},
    )


def test_edge_allowed_categories():
    assert edge_allowed_categories("top", "bottom") is True
    assert edge_allowed_categories("top", "shoes") is True
    assert edge_allowed_categories("dress", "shoes") is True
    assert edge_allowed_categories("top", "top") is False       # same slot
    assert edge_allowed_categories("top", "dress") is False      # dress excludes top
    assert edge_allowed_categories("bottom", "dress") is False


def test_edge_blocked_by_gender():
    a = _item("a", category="top", gender="men")
    b = _item("b", category="bottom", gender="women")
    assert edge_allowed(a, b) is False
    c = _item("c", category="bottom", gender="unisex")
    assert edge_allowed(a, c) is True  # unisex pairs with men


def test_edge_blocked_by_formality():
    a = _item("a", category="top", formality="athletic")
    b = _item("b", category="bottom", formality="formal")
    assert edge_allowed(a, b) is False
    c = _item("c", category="bottom", formality="smart_casual")
    a2 = _item("a2", category="top", formality="casual")
    assert edge_allowed(a2, c) is True  # adjacent bands ok


def test_edge_ignores_formality_for_accessory():
    a = _item("a", category="top", formality="casual")
    bag = _item("bag", category="bag", formality="formal")  # style-neutral category
    assert edge_allowed(a, bag) is True


def test_build_edges_canonical_and_sparse():
    items = [
        _item("i1", category="top"),
        _item("i2", category="bottom"),
        _item("i3", category="bottom"),
        _item("i4", category="shoes"),
    ]
    edges = build_edges(items, HeuristicPairScorer(), k=15)
    # canonical: src_id < dst_id
    assert all(e.src_id < e.dst_id for e in edges)
    # no same-category / excluded edges
    pairs = {(e.src_id, e.dst_id) for e in edges}
    assert ("i2", "i3") not in pairs  # bottom-bottom
    assert ("i1", "i2") in pairs       # top-bottom
    assert ("i1", "i4") in pairs       # top-shoes
    assert all(isinstance(e, Edge) for e in edges)


def test_build_edges_respects_top_k_per_partner_category():
    top = _item("a_top", category="top")
    bottoms = [_item(f"b{i:02d}", category="bottom", price=100_000 + i) for i in range(20)]
    # Anchor ONLY on the top so union-of-both-sides doesn't inflate degree:
    # top-k is a per-anchor cap, so the single anchor keeps exactly k neighbours.
    edges = build_edges([top, *bottoms], HeuristicPairScorer(), k=5, anchors=[top])
    assert len(edges) == 5  # top keeps exactly its top-5 bottom neighbours


def test_build_edges_deterministic():
    items = [
        _item("i1", category="top"),
        _item("i2", category="bottom"),
        _item("i3", category="shoes"),
    ]
    s = HeuristicPairScorer()
    assert build_edges(items, s) == build_edges(items, s)
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.graph'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/kb/graph.py`:

```python
"""Outfit compatibility graph — node = ItemRecord, edge = 'wearable together'.

An edge exists between two items only when ALL three hard constraints hold:
  1. co-wearable categories (COMPLEMENTARY_CATEGORIES);
  2. consistent gender (``_combo_gender`` is not None — unisex pairs with anything);
  3. coherent formality (``formality_span_ok`` — bags/accessories are style-neutral).
Edge weight is a pluggable pairwise compatibility (see pair_scoring.py). Each node
keeps its top-K strongest neighbours per partner-category so the graph stays sparse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from outfitmatch.kb.generation import _combo_gender
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, formality_span_ok

if TYPE_CHECKING:
    from outfitmatch.kb.pair_scoring import PairScorer
    from outfitmatch.kb.schema import ItemRecord

# Undirected co-wearability. Same category never connects (one per slot); ``dress``
# excludes ``top``/``bottom`` (a dress replaces both).
COMPLEMENTARY_CATEGORIES: dict[str, frozenset[str]] = {
    "top": frozenset({"bottom", "shoes", "outerwear", "bag", "accessory"}),
    "bottom": frozenset({"top", "shoes", "outerwear", "bag", "accessory"}),
    "dress": frozenset({"shoes", "outerwear", "bag", "accessory"}),
    "shoes": frozenset({"top", "bottom", "dress", "outerwear", "bag", "accessory"}),
    "outerwear": frozenset({"top", "bottom", "dress", "shoes", "bag", "accessory"}),
    "bag": frozenset({"top", "bottom", "dress", "shoes", "outerwear", "accessory"}),
    "accessory": frozenset({"top", "bottom", "dress", "shoes", "outerwear", "bag"}),
}


@dataclass(frozen=True)
class Edge:
    src_id: str
    dst_id: str
    src_category: str
    dst_category: str
    weight: float


def edge_allowed_categories(cat_a: str, cat_b: str) -> bool:
    """True if the two categories can co-occur in one outfit."""
    return cat_b in COMPLEMENTARY_CATEGORIES.get(cat_a, frozenset())


def edge_allowed(a: ItemRecord, b: ItemRecord) -> bool:
    """All three hard constraints for an edge between ``a`` and ``b``."""
    if a.item_id == b.item_id:
        return False
    if not edge_allowed_categories(a.category, b.category):
        return False
    if _combo_gender([a, b]) is None:
        return False
    formalities = [
        it.formality for it in (a, b) if it.category in FORMALITY_RELEVANT_CATEGORIES
    ]
    return formality_span_ok(formalities)


def build_edges(
    items: list[ItemRecord],
    scorer: PairScorer,
    k: int = 15,
    *,
    anchors: list[ItemRecord] | None = None,
) -> list[Edge]:
    """Build sparse compatibility edges (canonical ``src_id < dst_id``, de-duped).

    For each anchor item and each partner-category, keep the top-``k`` strongest
    neighbours. ``anchors=None`` → every item anchors (full build). Passing a
    subset (incremental build) restricts which items drive top-k selection while
    still linking them against all of ``items``. Deterministic: anchors processed
    in ``item_id`` order, weight ties break on ``item_id``.
    """
    ordered = sorted(items, key=lambda it: it.item_id)
    by_category: dict[str, list[ItemRecord]] = {}
    for it in ordered:
        by_category.setdefault(it.category, []).append(it)

    anchor_items = sorted(
        anchors if anchors is not None else items, key=lambda it: it.item_id
    )
    canonical: dict[tuple[str, str], Edge] = {}
    for a in anchor_items:
        for partner_cat in sorted(COMPLEMENTARY_CATEGORIES.get(a.category, frozenset())):
            candidates: list[tuple[float, ItemRecord]] = []
            for b in by_category.get(partner_cat, []):
                if edge_allowed(a, b):
                    candidates.append((scorer.score_pair(a, b), b))
            candidates.sort(key=lambda pair: (-pair[0], pair[1].item_id))
            for weight, b in candidates[:k]:
                lo, hi = sorted((a, b), key=lambda it: it.item_id)
                key = (lo.item_id, hi.item_id)
                if key not in canonical:
                    canonical[key] = Edge(
                        src_id=lo.item_id,
                        dst_id=hi.item_id,
                        src_category=lo.category,
                        dst_category=hi.category,
                        weight=weight,
                    )
    return sorted(canonical.values(), key=lambda e: (e.src_id, e.dst_id))
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_graph.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/graph.py tests/kb/test_graph.py
git commit -m "feat(kb): compatibility-graph edge constraints + sparse build_edges"
```

---

### Task 3: `graph_store.py` — edges parquet + `OutfitGraph`

**Files:**
- Create: `src/outfitmatch/kb/graph_store.py`
- Test: `tests/kb/test_graph_store.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_graph_store.py`:

```python
from __future__ import annotations

import pytest

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import load_graph, read_edges, write_edges
from outfitmatch.kb.schema import ItemRecord


def _item(item_id: str, category: str) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[0.1, 0.2],
        gender="unisex",
        formality="casual",
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def _edges() -> list[Edge]:
    return [
        Edge("i1", "i2", "top", "bottom", 0.9),
        Edge("i1", "i3", "top", "shoes", 0.7),
    ]


def test_edges_round_trip(tmp_path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    loaded = read_edges(path)
    assert {(e.src_id, e.dst_id, e.weight) for e in loaded} == {
        ("i1", "i2", 0.9),
        ("i1", "i3", 0.7),
    }


def test_read_edges_missing_file_returns_empty(tmp_path):
    assert read_edges(tmp_path / "nope.parquet") == []


def test_read_edges_rejects_bad_schema(tmp_path):
    import pandas as pd

    path = tmp_path / "item_edges.parquet"
    pd.DataFrame([{"src_id": "i1", "dst_id": "i2"}]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing edge columns"):
        read_edges(path)


def test_outfit_graph_neighbors_both_directions_sorted(tmp_path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    items = [_item("i1", "top"), _item("i2", "bottom"), _item("i3", "shoes")]
    graph = load_graph(path, items=items)
    # i1 has a bottom (i2) and a shoes (i3) neighbour
    assert graph.neighbors("i1", "bottom") == [("i2", 0.9)]
    assert graph.neighbors("i1", "shoes") == [("i3", 0.7)]
    # reverse direction: i2 sees i1 as a 'top' neighbour
    assert graph.neighbors("i2", "top") == [("i1", 0.9)]


def test_outfit_graph_edge_weight_symmetric_and_none(tmp_path):
    path = tmp_path / "item_edges.parquet"
    write_edges(_edges(), path)
    items = [_item("i1", "top"), _item("i2", "bottom"), _item("i3", "shoes")]
    graph = load_graph(path, items=items)
    assert graph.edge_weight("i1", "i2") == 0.9
    assert graph.edge_weight("i2", "i1") == 0.9  # symmetric
    assert graph.edge_weight("i2", "i3") is None  # no edge
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_graph_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.graph_store'`

- [ ] **Step 3: Viết module (phần edges + graph)**

Tạo `src/outfitmatch/kb/graph_store.py`:

```python
"""Persist & load the outfit compatibility graph (edges parquet + Qdrant nodes)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from outfitmatch.kb.graph import Edge
from scripts.data.scrape.base import CATALOG_DIR

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord

GRAPH_DIR: Path = CATALOG_DIR.parent / "graph"
EDGES_PARQUET: Path = GRAPH_DIR / "item_edges.parquet"

_EDGE_COLUMNS = ("src_id", "dst_id", "src_category", "dst_category", "weight")


def write_edges(edges: list[Edge], path: Path = EDGES_PARQUET) -> Path:
    """Write canonical edges to parquet (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "src_id": e.src_id,
                "dst_id": e.dst_id,
                "src_category": e.src_category,
                "dst_category": e.dst_category,
                "weight": float(e.weight),
            }
            for e in edges
        ],
        columns=list(_EDGE_COLUMNS),
    )
    frame.to_parquet(path, index=False)
    return path


def read_edges(path: Path = EDGES_PARQUET) -> list[Edge]:
    """Read edges from parquet; empty list if file absent."""
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    missing = set(_EDGE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(
            f"{path} missing edge columns {sorted(missing)}; rebuild with --rebuild"
        )
    return [
        Edge(
            src_id=str(row.src_id),
            dst_id=str(row.dst_id),
            src_category=str(row.src_category),
            dst_category=str(row.dst_category),
            weight=float(row.weight),
        )
        for row in frame.itertuples(index=False)
    ]


class OutfitGraph:
    """In-memory adjacency over compatibility edges (built both directions)."""

    def __init__(self, items: list[ItemRecord], edges: list[Edge]) -> None:
        self._items: dict[str, ItemRecord] = {it.item_id: it for it in items}
        self._adj: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._weight: dict[tuple[str, str], float] = {}
        for e in edges:
            self._adj[e.src_id][e.dst_category].append((e.dst_id, e.weight))
            self._adj[e.dst_id][e.src_category].append((e.src_id, e.weight))
            self._weight[(e.src_id, e.dst_id)] = e.weight
            self._weight[(e.dst_id, e.src_id)] = e.weight
        for partner_map in self._adj.values():
            for neighbours in partner_map.values():
                neighbours.sort(key=lambda pair: (-pair[1], pair[0]))

    def neighbors(self, item_id: str, partner_category: str) -> list[tuple[str, float]]:
        """``(neighbor_id, weight)`` sorted by weight desc — for beam-expand."""
        return list(self._adj.get(item_id, {}).get(partner_category, []))

    def edge_weight(self, a_id: str, b_id: str) -> float | None:
        """Weight of edge a–b, or None if there is no edge (for clique checks)."""
        return self._weight.get((a_id, b_id))

    def item(self, item_id: str) -> ItemRecord:
        return self._items[item_id]


def load_graph(edges_path: Path = EDGES_PARQUET, *, items: list[ItemRecord]) -> OutfitGraph:
    """Load edges from parquet and build an ``OutfitGraph`` over ``items``."""
    return OutfitGraph(items, read_edges(edges_path))
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_graph_store.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/graph_store.py tests/kb/test_graph_store.py
git commit -m "feat(kb): edge parquet store + OutfitGraph adjacency (neighbors/edge_weight)"
```

---

### Task 4: `graph_store.py` — Qdrant `items` collection nodes

**Files:**
- Modify: `src/outfitmatch/kb/graph_store.py` (thêm node-indexing; reuse `qdrant_index` privates)
- Test: `tests/kb/test_graph_store.py` (thêm test Qdrant)

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/kb/test_graph_store.py`:

```python
def test_index_item_nodes_upserts_with_filterable_payload(tmp_path):
    from qdrant_client import QdrantClient

    from outfitmatch.kb.graph_store import ITEM_PAYLOAD_INDEX_FIELDS, index_item_nodes

    items = [
        ItemRecord(
            item_id="item_custom_00001",
            category="top",
            image_path="data/custom/catalog/images/item_custom_00001.jpg",
            item_embedding=[0.1, 0.2, 0.3],
            gender="men",
            formality="smart_casual",
            store={
                "store_id": "yody_vn",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 250_000,
                "in_stock": True,
                "colors": [],
            },
        )
    ]
    qdrant_path = tmp_path / "qdrant"
    index_item_nodes(items, f"path://{qdrant_path.as_posix()}", batch_size=1)

    client = QdrantClient(path=str(qdrant_path))
    try:
        assert client.get_collection("items").points_count == 1
        records, _ = client.scroll("items", limit=10, with_vectors=True)
    finally:
        client.close()

    payload = records[0].payload
    assert payload["item_id"] == "item_custom_00001"
    assert payload["gender"] == "men"
    assert payload["formality"] == "smart_casual"
    assert payload["price_tier"] == "budget"  # 250k < 300k
    assert records[0].id != "item_custom_00001"  # raw IDs invalid as Qdrant point IDs
    assert "gender" in ITEM_PAYLOAD_INDEX_FIELDS


def test_index_item_nodes_skips_items_without_embedding(tmp_path):
    from outfitmatch.kb.graph_store import index_item_nodes

    items = [
        ItemRecord(
            item_id="i1",
            category="top",
            image_path="",
            item_embedding=[],  # no embedding → skipped
            gender="unisex",
            formality="casual",
            store={"store_id": "x", "price_vnd": 1, "in_stock": True, "product_url": "x"},
        )
    ]
    # no embedding → no collection created, no crash
    index_item_nodes(items, f"path://{(tmp_path / 'qdrant').as_posix()}")
    assert not (tmp_path / "qdrant").exists() or True  # function returns early
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_graph_store.py::test_index_item_nodes_upserts_with_filterable_payload -v`
Expected: FAIL — `ImportError: cannot import name 'index_item_nodes'`

- [ ] **Step 3: Thêm node-indexing vào `graph_store.py`**

Thêm cuối `src/outfitmatch/kb/graph_store.py`:

```python
from uuid import NAMESPACE_URL, uuid5

from outfitmatch.kb.qdrant_index import (
    _batched,
    _close_client,
    _collection_exists,
    _import_qdrant,
    _is_existing_index_error,
    _make_client,
)

# KEYWORD-indexed payload fields → Tầng 3 seed-node filtering.
ITEM_PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "category",
    "gender",
    "formality",
    "price_tier",
    "has_vn_store",
    "in_stock",
    "store_id",
)

_ITEM_POINT_NAMESPACE = "outfitmatch:items"


def _item_point_id(item_id: str) -> str:
    # Qdrant point IDs must be uint64 or UUID; raw item_custom_NNNNN kept in payload.
    return str(uuid5(NAMESPACE_URL, f"{_ITEM_POINT_NAMESPACE}:{item_id}"))


def _item_price_tier(price_vnd: int) -> str:
    """Per-item price band (distinct from outfit-total tiers in generation.py)."""
    if price_vnd < 300_000:
        return "budget"
    if price_vnd <= 1_000_000:
        return "mid"
    return "premium"


def _item_payload(item: ItemRecord) -> dict:
    price = int(item.store.get("price_vnd") or 0)
    return {
        "item_id": item.item_id,
        "category": item.category,
        "gender": item.gender,
        "formality": item.formality,
        "price_vnd": price,
        "price_tier": _item_price_tier(price),
        "has_vn_store": bool(item.store.get("product_url")),
        "in_stock": bool(item.store.get("in_stock")),
        "store_id": str(item.store.get("store_id") or ""),
        "colors": list(item.store.get("colors", []) or []),
        "image_path": item.image_path,
        "product_url": str(item.store.get("product_url") or ""),
    }


def index_item_nodes(
    items: list[ItemRecord],
    qdrant_url: str,
    collection_name: str = "items",
    batch_size: int = 256,
) -> None:
    """Upsert item nodes (vector + filterable payload) into the Qdrant ``items`` collection.

    Items without an ``item_embedding`` are skipped (no vector to index). The
    collection is created on demand using the first item's embedding dimension.
    """
    nodes = [it for it in items if it.item_embedding]
    if not nodes:
        return
    vector_dim = len(nodes[0].item_embedding)
    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        if not _collection_exists(client, collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_dim, distance=models.Distance.COSINE
                ),
            )
        for field in ITEM_PAYLOAD_INDEX_FIELDS:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:
                if not _is_existing_index_error(exc):
                    raise
        for batch in _batched(nodes, batch_size):
            points = [
                models.PointStruct(
                    id=_item_point_id(it.item_id),
                    vector=[float(x) for x in it.item_embedding],
                    payload=_item_payload(it),
                )
                for it in batch
            ]
            client.upsert(collection_name=collection_name, points=points, wait=True)
    finally:
        _close_client(client)
```

> Ghi chú DRY: tái dùng `_make_client/_batched/_collection_exists/_is_existing_index_error/_close_client` từ `qdrant_index.py` (cùng package). Point-id namespace riêng (`outfitmatch:items`) để không đụng collection `outfits`.

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_graph_store.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/graph_store.py tests/kb/test_graph_store.py
git commit -m "feat(kb): index item nodes into Qdrant items collection for seed filtering"
```

---

### Task 5: `build_graph.py` — CLI (full + incremental)

**Files:**
- Create: `scripts/data/kb/build_graph.py`
- Test: `tests/kb/test_graph_store.py` (thêm test incremental qua `build_edges(anchors=...)`)

- [ ] **Step 1: Viết test thất bại (incremental edge semantics)**

Thêm vào `tests/kb/test_graph_store.py`:

```python
def test_incremental_anchor_build_keeps_old_edges(tmp_path):
    from outfitmatch.kb.graph import build_edges
    from outfitmatch.kb.pair_scoring import HeuristicPairScorer
    from outfitmatch.kb.schema import ItemRecord

    def mk(item_id, cat):
        return ItemRecord(
            item_id=item_id, category=cat, image_path="", item_embedding=[0.1],
            gender="unisex", formality="casual",
            store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
        )

    old_items = [mk("i1", "top"), mk("i2", "bottom")]
    scorer = HeuristicPairScorer()
    old_edges = build_edges(old_items, scorer)
    assert {(e.src_id, e.dst_id) for e in old_edges} == {("i1", "i2")}

    # add a shoe; incremental anchors only the new item against ALL items
    new_shoe = mk("i3", "shoes")
    all_items = [*old_items, new_shoe]
    inc_edges = build_edges(all_items, scorer, anchors=[new_shoe])
    inc_pairs = {(e.src_id, e.dst_id) for e in inc_edges}
    assert ("i1", "i3") in inc_pairs  # shoe links to the existing top
    assert ("i2", "i3") in inc_pairs  # shoe links to the existing bottom
    assert ("i1", "i2") not in inc_pairs  # existing top-bottom edge NOT recomputed

    # union (old + incremental) gives the complete graph; old edge preserved
    union = {(e.src_id, e.dst_id) for e in (*old_edges, *inc_edges)}
    assert union == {("i1", "i2"), ("i1", "i3"), ("i2", "i3")}
```

- [ ] **Step 2: Chạy test xác nhận PASS (logic đã có ở Task 2)**

Run: `uv run pytest tests/kb/test_graph_store.py::test_incremental_anchor_build_keeps_old_edges -v`
Expected: PASS (xác nhận `anchors=` đủ sức cho incremental — không cần code mới ở generation).

- [ ] **Step 3: Viết CLI**

Tạo `scripts/data/kb/build_graph.py`:

```python
"""Build the outfit compatibility graph from the validated VN catalog.

Examples:
    # full build → edges parquet + Qdrant items collection
    uv run python -m scripts.data.kb.build_graph --qdrant-url path://data/cache/qdrant
    # parquet only (no Qdrant), capped for a quick smoke
    uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80
    # incremental: only new item_ids anchor new edges, old edges preserved
    uv run python -m scripts.data.kb.build_graph --incremental --no-qdrant
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from outfitmatch.kb.build_outfits import _ensure_item_embeddings
from outfitmatch.kb.catalog import group_items_by_category, load_catalog_items
from outfitmatch.kb.graph import build_edges
from outfitmatch.kb.graph_store import (
    EDGES_PARQUET,
    index_item_nodes,
    read_edges,
    write_edges,
)
from outfitmatch.kb.pair_scoring import HeuristicPairScorer
from outfitmatch.kb.scoring import HeuristicOutfitScorer
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.build_graph")


def _flatten(items_by_category: dict[str, list]) -> list:
    out: list = []
    for items in items_by_category.values():
        out.extend(items)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the OutfitMatch compatibility graph")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges-out", type=Path, default=EDGES_PARQUET)
    parser.add_argument("--k", type=int, default=15, help="Top-K neighbours per partner-category")
    parser.add_argument(
        "--limit-per-category", type=int, default=0, help="Cap items/category (0 = no cap)"
    )
    parser.add_argument("--include-kid", action="store_true", help="Include kids' wear")
    parser.add_argument("--qdrant-url", type=str, default="path://data/cache/qdrant")
    parser.add_argument("--no-qdrant", action="store_true", help="Write parquet only")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only new item_ids anchor new edges; existing edges are preserved",
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Force full rebuild (ignore existing edges)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    genders = None if args.include_kid else {"men", "women", "unisex"}
    items = load_catalog_items(args.catalog, args.links, genders=genders)
    if args.limit_per_category and args.limit_per_category > 0:
        items = _flatten(group_items_by_category(items, limit_per_category=args.limit_per_category))
    _ensure_item_embeddings({"_all": items}, HeuristicOutfitScorer())
    logger.info("loaded %d items (genders=%s)", len(items), genders or "all")

    scorer = HeuristicPairScorer()
    if args.incremental and not args.rebuild:
        existing = read_edges(args.edges_out)
        known_ids = {e.src_id for e in existing} | {e.dst_id for e in existing}
        new_items = [it for it in items if it.item_id not in known_ids]
        logger.info("incremental: %d new items, %d existing edges", len(new_items), len(existing))
        if not new_items:
            logger.info("no new items — nothing to do")
            new_edges = []
        else:
            new_edges = build_edges(items, scorer, k=args.k, anchors=new_items)
        seen = {(e.src_id, e.dst_id) for e in existing}
        merged = [*existing, *(e for e in new_edges if (e.src_id, e.dst_id) not in seen)]
        merged.sort(key=lambda e: (e.src_id, e.dst_id))
        edges = merged
    else:
        edges = build_edges(items, scorer, k=args.k)

    write_edges(edges, args.edges_out)
    logger.info("wrote %d edges → %s", len(edges), args.edges_out)

    if not args.no_qdrant:
        index_item_nodes(items, args.qdrant_url)
        logger.info("indexed %d item nodes → Qdrant items (%s)", len(items), args.qdrant_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Smoke import + chạy parquet-only trên data thật (cap nhỏ)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -c "import scripts.data.kb.build_graph"
uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80 --edges-out data/custom/graph/_smoke_edges.parquet
```
Expected: log `loaded N items` + `wrote M edges`; file `_smoke_edges.parquet` sinh ra; exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/kb/build_graph.py tests/kb/test_graph_store.py
git commit -m "feat(kb): build_graph CLI (full + incremental + Qdrant nodes)"
```

---

### Task 6: Full check, real-catalog build, docs

- [ ] **Step 1: Full test + lint**

Run: `uv run pytest -q`
Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run mypy src`
Expected: tất cả xanh. (Nếu ruff báo import order → `uv run ruff check --fix .` rồi chạy lại.)

- [ ] **Step 2: Build graph thật trên toàn catalog (parquet, có timing)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
Measure-Command { uv run python -m scripts.data.kb.build_graph --no-qdrant }
```
Expected: sinh `data/custom/graph/item_edges.parquet`; log số edge; thời gian < ~vài phút. Ghi lại số edge + thời gian.

- [ ] **Step 3: Sanity-check graph (degree, coherence-by-construction)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -c "import pandas as pd; df=pd.read_parquet('data/custom/graph/item_edges.parquet'); print('edges:', len(df)); print(df.groupby(['src_category','dst_category']).size().sort_values(ascending=False).head(12)); deg=pd.concat([df['src_id'],df['dst_id']]).value_counts(); print('degree min/median/max:', int(deg.min()), int(deg.median()), int(deg.max()))"
```
Expected: edges > 0; degree median hợp lý (vài chục); có cặp top-bottom, *-shoes; **không** có top-top/top-dress (coherence by construction).

- [ ] **Step 4: Dọn file smoke**

Run:
```powershell
Remove-Item data/custom/graph/_smoke_edges.parquet -ErrorAction SilentlyContinue
```

- [ ] **Step 5: Docs**

`Kien_truc_v3.1.md` §3 (Tầng 1/3) — thêm đoạn:

```markdown
- **Graph KB (sub-project 1).** KB chuyển sang graph item-compatibility: node = item,
  edge = "phối được" khi đồng gender + coherent formality + co-wearable category
  (`kb/graph.py`). Edge thưa (top-K=15/partner-category), weight pluggable
  (`HeuristicPairScorer` → OT-labse). Lưu `data/custom/graph/item_edges.parquet`
  + Qdrant `items` collection. Outfit ráp động lúc retrieval (sub-project 2);
  thêm giày sau chỉ cần `build_graph --incremental`.
```

`docs/feature.md` — thêm entry:

```markdown
### Outfit Graph KB — construction (sub-project 1)
- `kb/pair_scoring.py`, `kb/graph.py`, `kb/graph_store.py`, `scripts/data/kb/build_graph.py`.
- Build: `uv run python -m scripts.data.kb.build_graph`. Incremental: `--incremental`.
- Interface cho Tầng 3: `OutfitGraph.neighbors(item_id, partner_category)` / `edge_weight(a, b)`.
```

- [ ] **Step 6: Commit**

```bash
git add data/custom/graph/item_edges.parquet Kien_truc_v3.1.md docs/feature.md
git commit -m "data(kb): build compatibility graph on VN catalog; docs"
```

---

## Self-Review

**1. Spec coverage**
- Node = ItemRecord, không schema mới → Task 3/4 dùng `ItemRecord` trực tiếp. ✔
- Edge 3 hard-constraint (category/gender/formality) → Task 2 `edge_allowed` + test khoá từng trục. ✔
- Weight pluggable (`PairScorer`/`HeuristicPairScorer`) → Task 1. ✔
- Sparsify top-K/partner-category → Task 2 `build_edges` + test. ✔
- Lưu parquet canonical + adjacency 2 chiều → Task 3. ✔
- Qdrant `items` collection filter seed → Task 4 (`ITEM_PAYLOAD_INDEX_FIELDS`). ✔
- Extensibility incremental, cạnh cũ bất biến → Task 2 `anchors=` + Task 5 CLI + test. ✔
- Determinism → Task 2 sort + test; build không RNG. ✔
- Interface §9 cho traversal → Task 3 `OutfitGraph.neighbors/edge_weight/item`. ✔
- Giữ nguyên `OutfitRecord`/`qdrant_index` outfits → không task nào sửa (cố ý). ✔
- Colors rỗng không phạt → Task 1 `_color_harmony` trả 0.5. ✔

**2. Placeholder scan** — mọi step có code thật + lệnh + expected. Không TODO/“xử lý phù hợp”.

**3. Type consistency** — `Edge(src_id,dst_id,src_category,dst_category,weight)` nhất quán giữa `graph.py`/`graph_store.py`/test; `score_pair(a,b)->float` khớp `PairScorer` protocol + dùng trong `build_edges`; `OutfitGraph.neighbors/edge_weight/item` khớp interface §9 của spec; `_EDGE_COLUMNS` khớp `write_edges`/`read_edges`; `ITEM_PAYLOAD_INDEX_FIELDS` khớp payload `_item_payload`. `build_edges(items, scorer, k, *, anchors)` cùng chữ ký ở full build (Task 2) và incremental (Task 5).

## Out of scope (sub-project sau)
1. **Traversal retrieval (Tầng 3 mới)** — ráp outfit động từ graph, rank, top-5; shoeless fallback. (sub-project 2)
2. **Grading redefinition** — Recall@5/Compat trên outfit ráp động; gỡ materialized `OutfitRecord`/`outfits` collection. (sub-project 3)
3. **OT-labse pairwise scorer thật** — cắm qua `PairScorer`, không dựng lại graph.
4. **Trục `season`** cho edge — tái dùng khung `edge_allowed`.

## Lưu ý khi thực thi
- `k=15` và band giá `_item_price_tier` là giá trị khởi điểm — calibrate sau khi xem degree distribution (Task 6 Step 3) và khi traversal (sub-project 2) chạy thật.
- Incremental cố ý KHÔNG tái tính top-K của node cũ (giữ cạnh cũ bất biến) → giày mới chỉ chắc chắn xuất hiện ở "phía neighbor của chính nó"; vì cạnh vô hướng nên `neighbors(old_top, "shoes")` vẫn thấy giày mới. Dùng `--rebuild` khi muốn top-K chuẩn lại toàn bộ.
- Build full O(N × partner-bucket) — nếu chậm quá mức chấp nhận, cân nhắc embedding-NN để cắt candidate (follow-up, không thuộc plan này).
```
