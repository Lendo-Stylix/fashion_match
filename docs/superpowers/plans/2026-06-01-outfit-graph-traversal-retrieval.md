# Outfit Graph Traversal Retrieval (Tầng 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiện thực Tầng 3 qua graph: Qdrant filter seed node → traverse graph ráp outfit động (top+bottom bắt buộc, shoes/outerwear/bag/accessory optional, shoeless hợp lệ) → trả `OutfitRecord` để Tầng 4 rerank + pipeline dùng nguyên.

**Architecture:** `kb/traversal.py` (pure-graph assembly, clique đảm bảo coherence) → `kb/assemble_record.py` (dựng `OutfitRecord` tag-dẫn-xuất: occasion từ formality, style từ store) → `retrieval.py` (Qdrant seed-filter injectable + post-filter) → `pipeline.recommend_outfit` wire Tầng 3+4.

**Tech Stack:** Python 3.13, `uv`, `qdrant-client`, pytest, dataclasses. Không thêm dependency.

**Spec:** `docs/superpowers/specs/2026-06-01-outfit-graph-traversal-retrieval-design.md`. **Depends on:** sub-project 1 (`OutfitGraph`, Qdrant `items`).

> ⚠️ **Quyết định đã chốt trong plan (xem spec §3):** occasion suy từ `formality` (map), style suy từ `store.style_tags`, **body_shape DEFER** (no-op MVP — body-ablation cần item-tagging follow-up).

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/vocab.py` | `FORMALITY_OCCASIONS`, `occasions_for_formality`, `formalities_for_occasion` | Modify |
| `src/outfitmatch/kb/traversal.py` | `AssemblyConfig`, `AssembledOutfit`, `assemble_from_seed`, `assemble_outfits` | **Create** |
| `src/outfitmatch/kb/assemble_record.py` | `to_outfit_record` | **Create** |
| `src/outfitmatch/retrieval.py` | `qdrant_filter_seed_ids`, `search_outfits` | **Create** |
| `src/outfitmatch/pipeline.py` | `recommend_outfit` wire | Modify |
| `tests/test_vocab.py`, `tests/kb/test_traversal.py`, `tests/kb/test_assemble_record.py`, `tests/test_retrieval.py`, `tests/test_pipeline_v31.py` | Test | Create/Modify |

---

### Task 1: vocab — formality↔occasion map

**Files:**
- Modify: `src/outfitmatch/vocab.py` (cuối file, sau `formality_span_ok`)
- Test: `tests/test_vocab.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_vocab.py`:

```python
def test_occasions_for_formality_subset_of_occasion():
    from outfitmatch.vocab import OCCASION_SET, occasions_for_formality

    for f in ("athletic", "casual", "smart_casual", "formal"):
        occ = occasions_for_formality(f)
        assert occ, f"no occasions for {f}"
        assert occ <= OCCASION_SET


def test_formalities_for_occasion_inverse():
    from outfitmatch.vocab import formalities_for_occasion, occasions_for_formality

    assert "office" in occasions_for_formality("formal")
    assert "formal" in formalities_for_occasion("office")
    assert "athletic" not in formalities_for_occasion("wedding")
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/test_vocab.py::test_formalities_for_occasion_inverse -v`
Expected: FAIL — `ImportError: cannot import name 'occasions_for_formality'`

- [ ] **Step 3: Thêm map + helper**

Cuối `src/outfitmatch/vocab.py`:

```python
# Coarse formality → admissible occasions. Graph nodes carry no per-item occasion
# tag, so retrieval derives occasion fit from an item's formality band. Keep every
# value inside OCCASION.
FORMALITY_OCCASIONS: dict[str, frozenset[str]] = {
    "athletic": frozenset({"home_casual", "travel", "school"}),
    "casual": frozenset({"school", "cafe_hangout", "home_casual", "travel", "date"}),
    "smart_casual": frozenset(
        {"office", "interview", "school", "date", "cafe_hangout", "party"}
    ),
    "formal": frozenset({"office", "interview", "wedding", "party", "date"}),
}


def occasions_for_formality(formality: str) -> frozenset[str]:
    """Occasions a given formality band is appropriate for (⊆ OCCASION)."""
    return FORMALITY_OCCASIONS.get(formality, frozenset())


def formalities_for_occasion(occasion: str) -> set[str]:
    """Inverse: formality bands whose items suit ``occasion`` (for seed filtering)."""
    return {f for f, occ in FORMALITY_OCCASIONS.items() if occasion in occ}
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_vocab.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/vocab.py tests/test_vocab.py
git commit -m "feat(vocab): formality<->occasion map for graph retrieval"
```

---

### Task 2: `traversal.py` — assemble outfit từ graph

**Files:**
- Create: `src/outfitmatch/kb/traversal.py`
- Test: `tests/kb/test_traversal.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_traversal.py`:

```python
from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.traversal import assemble_from_seed, assemble_outfits


def _item(item_id: str, category: str) -> ItemRecord:
    return ItemRecord(
        item_id=item_id, category=category, image_path="", item_embedding=[0.1],
        gender="unisex", formality="casual",
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def _graph(items, edges) -> OutfitGraph:
    return OutfitGraph(items, edges)


def test_assemble_top_seed_adds_bottom_and_shoes():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    graph = _graph(items, edges)
    outfits = assemble_from_seed(graph, "t")
    assert outfits, "top seed should assemble at least one outfit"
    cats = {i.category for i in outfits[0].items}
    assert {"top", "bottom"} <= cats          # bottom mandatory
    assert "shoes" in cats                     # clique-connected shoes added
    assert outfits[0].score > 0.0


def test_assemble_is_shoeless_when_no_shoe_neighbor():
    items = [_item("t", "top"), _item("b", "bottom")]
    edges = [Edge("b", "t", "bottom", "top", 0.9)]  # no shoes at all
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    cats = {i.category for i in outfits[0].items}
    assert cats == {"top", "bottom"}            # valid shoeless outfit


def test_assemble_skips_top_with_no_bottom():
    items = [_item("t", "top"), _item("s", "shoes")]
    edges = [Edge("s", "t", "shoes", "top", 0.8)]  # top has shoes but NO bottom
    assert assemble_from_seed(_graph(items, edges), "t") == []


def test_assemble_clique_blocks_unconnected_optional():
    # shoes connects to top but NOT to bottom → must not be added (would break clique)
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [Edge("b", "t", "bottom", "top", 0.9), Edge("s", "t", "shoes", "top", 0.8)]
    outfits = assemble_from_seed(_graph(items, edges), "t")
    assert outfits
    assert {i.category for i in outfits[0].items} == {"top", "bottom"}  # shoes excluded


def test_assemble_outfits_dedup_and_sorted():
    items = [_item("t", "top"), _item("b1", "bottom"), _item("b2", "bottom")]
    edges = [
        Edge("b1", "t", "bottom", "top", 0.9),
        Edge("b2", "t", "bottom", "top", 0.6),
    ]
    graph = _graph(items, edges)
    outfits = assemble_outfits(graph, ["t", "t"])  # duplicate seed
    keys = [o.item_ids for o in outfits]
    assert len(keys) == len(set(keys))             # deduped
    assert outfits == sorted(outfits, key=lambda o: (o.score, o.item_ids), reverse=True)
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_traversal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.traversal'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/kb/traversal.py`:

```python
"""Assemble outfits by traversing the compatibility graph (v3.1 Tầng 3 core).

An outfit is a *clique* in the graph: every pair of chosen items shares an edge,
so gender + formality coherence (graph invariants) hold for the whole set. Anchors
are tops and dresses; a top must gain a bottom (mandatory), then optional
shoes/outerwear/bag/accessory are added when clique-safe. A top+bottom with no
shoe neighbour is a valid shoeless outfit — shoes attach later once the catalog
grows (see build_graph --incremental).
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
    beam: int = 3  # bottoms tried per top seed
    max_optional: int = 3  # cap optional items added per outfit


@dataclass(frozen=True)
class AssembledOutfit:
    items: list[ItemRecord]
    score: float

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(it.item_id for it in self.items)


def _mean_pairwise(graph: OutfitGraph, items: list[ItemRecord]) -> float:
    """Mean edge weight over all item pairs; 0.0 if any pair lacks an edge (not a clique)."""
    pairs = list(combinations(items, 2))
    if not pairs:
        return 0.0
    weights: list[float] = []
    for a, b in pairs:
        w = graph.edge_weight(a.item_id, b.item_id)
        if w is None:
            return 0.0
        weights.append(w)
    return round(sum(weights) / len(weights), 6)


def _best_clique_neighbor(
    graph: OutfitGraph, items: list[ItemRecord], partner_category: str
) -> ItemRecord | None:
    """Highest-weight neighbour (from items[0]) that connects to EVERY current item."""
    current_ids = [it.item_id for it in items]
    present = set(current_ids)
    for cand_id, _w in graph.neighbors(current_ids[0], partner_category):
        if cand_id in present:
            continue
        if all(graph.edge_weight(cand_id, cid) is not None for cid in current_ids):
            return graph.item(cand_id)
    return None


def assemble_from_seed(
    graph: OutfitGraph, seed_id: str, *, config: AssemblyConfig = AssemblyConfig()
) -> list[AssembledOutfit]:
    """Assemble up to ``config.beam`` outfits anchored on a top or dress seed."""
    seed = graph.item(seed_id)
    if seed.category == "dress":
        cores: list[list[ItemRecord]] = [[seed]]
    elif seed.category == "top":
        bottoms = [graph.item(bid) for bid, _ in graph.neighbors(seed_id, "bottom")]
        cores = [[seed, b] for b in bottoms[: config.beam]]
    else:
        return []  # only top/dress anchor an outfit

    results: list[AssembledOutfit] = []
    for core in cores:
        items = list(core)
        for category in OPTIONAL_CATEGORIES:
            added = sum(1 for it in items if it.category in OPTIONAL_CATEGORIES)
            if added >= config.max_optional:
                break
            cand = _best_clique_neighbor(graph, items, category)
            if cand is not None:
                items.append(cand)
        score = _mean_pairwise(graph, items)
        if score > 0.0:
            results.append(AssembledOutfit(items=items, score=score))
    return results


def assemble_outfits(
    graph: OutfitGraph, seed_ids: list[str], *, config: AssemblyConfig = AssemblyConfig()
) -> list[AssembledOutfit]:
    """Assemble + dedup outfits across seeds, sorted by score desc (deterministic)."""
    seen: set[tuple[str, ...]] = set()
    out: list[AssembledOutfit] = []
    for seed_id in seed_ids:
        for outfit in assemble_from_seed(graph, seed_id, config=config):
            if outfit.item_ids in seen:
                continue
            seen.add(outfit.item_ids)
            out.append(outfit)
    out.sort(key=lambda o: (o.score, o.item_ids), reverse=True)
    return out
```

> Lưu ý: dress-seed cần ít nhất 1 optional (shoes/bag/...) để có pair → có score; dress hoàn toàn cô lập bị bỏ (chấp nhận ở MVP — xem spec §5).

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_traversal.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/traversal.py tests/kb/test_traversal.py
git commit -m "feat(kb): graph traversal outfit assembly (clique + shoeless)"
```

---

### Task 3: `assemble_record.py` — dựng OutfitRecord tag-dẫn-xuất

**Files:**
- Create: `src/outfitmatch/kb/assemble_record.py`
- Test: `tests/kb/test_assemble_record.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_assemble_record.py`:

```python
from __future__ import annotations

from outfitmatch.kb.assemble_record import to_outfit_record
from outfitmatch.kb.schema import ItemRecord


def _item(item_id, category, *, gender="men", formality="smart_casual", price=300_000, store_id="aristino_vn", colors=None):
    return ItemRecord(
        item_id=item_id, category=category, image_path="", item_embedding=[0.1, 0.2],
        gender=gender, formality=formality,
        store={"store_id": store_id, "price_vnd": price, "colors": colors or [],
               "product_url": "https://x", "in_stock": True},
    )


def test_to_outfit_record_derives_tags():
    items = [_item("t", "top"), _item("b", "bottom", colors=["đen"])]
    rec = to_outfit_record(items, 0.82)
    assert rec.compatibility_score == 0.82
    assert rec.gender == "men"
    assert rec.gen_method == "graph_traversal"
    assert rec.price_total_vnd == 600_000
    assert "office" in rec.occasion          # smart_casual → office (formality map)
    assert rec.style                          # derived from store style_tags
    assert "đen" in rec.color_palette


def test_to_outfit_record_unisex_when_all_unisex():
    items = [_item("t", "top", gender="unisex"), _item("b", "bottom", gender="unisex")]
    rec = to_outfit_record(items, 0.5)
    assert rec.gender == "unisex"
    assert rec.body_shapes_fit == []          # deferred in MVP
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_assemble_record.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.assemble_record'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/kb/assemble_record.py`:

```python
"""Turn an assembled item set into an OutfitRecord with derived tags.

The graph KB has no per-outfit Gemini tags, so we derive them: occasion from the
outfit's highest formality band, style from each item's store style_tags, color
palette from item colors. The result is a normal OutfitRecord, so rerank.py and
the pipeline consume graph outfits unchanged. body_shapes_fit/season stay empty
(deferred — see traversal-retrieval spec §3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from outfitmatch.kb.generation import _aggregate_embedding, _combo_gender, _price_tier
from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.vocab import (
    FORMALITY_RANK,
    FORMALITY_RELEVANT_CATEGORIES,
    occasions_for_formality,
)
from scripts.data.scrape.config import STORES_BY_ID

if TYPE_CHECKING:
    from outfitmatch.kb.schema import ItemRecord


def _outfit_occasions(items: list[ItemRecord]) -> list[str]:
    bands = [it.formality for it in items if it.category in FORMALITY_RELEVANT_CATEGORIES]
    if not bands:
        return []
    top_band = max(bands, key=lambda f: FORMALITY_RANK.get(f, 0))
    return sorted(occasions_for_formality(top_band))


def _outfit_styles(items: list[ItemRecord]) -> list[str]:
    styles: set[str] = set()
    for it in items:
        store = STORES_BY_ID.get(str(it.store.get("store_id") or ""))
        if store is not None:
            styles.update(store.style_tags)
    return sorted(styles)


def to_outfit_record(items: list[ItemRecord], score: float, *, index: int = 1) -> OutfitRecord:
    """Build an OutfitRecord (derived tags) from an assembled item set."""
    price_total = sum(int(it.store.get("price_vnd") or 0) for it in items)
    colors = sorted({str(c) for it in items for c in it.store.get("colors", []) if str(c)})
    return OutfitRecord(
        outfit_id=f"OF_{index:05d}",
        schema_version="3.1",
        items=items,
        outfit_embedding=_aggregate_embedding(items),
        compatibility_score=round(float(score), 6),
        occasion=_outfit_occasions(items),
        style=_outfit_styles(items),
        body_shapes_fit=[],
        season=[],
        color_palette=colors,
        price_total_vnd=price_total,
        price_tier=_price_tier(price_total),
        has_vn_store=all(bool(it.store.get("product_url")) for it in items),
        stylist_explanation_vi="",
        gen_method="graph_traversal",
        gender=_combo_gender(items) or "unisex",
    )
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_assemble_record.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/assemble_record.py tests/kb/test_assemble_record.py
git commit -m "feat(kb): to_outfit_record with derived occasion/style tags"
```

---

### Task 4: `retrieval.py` — Tầng 3 (seed-filter + assemble + post-filter)

**Files:**
- Create: `src/outfitmatch/retrieval.py`
- Test: `tests/test_retrieval.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_retrieval.py`:

```python
from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.pipeline import RecommendRequest
from outfitmatch.retrieval import search_outfits


def _item(item_id, category, *, colors=None, price=300_000):
    return ItemRecord(
        item_id=item_id, category=category, image_path="", item_embedding=[0.1],
        gender="men", formality="smart_casual",
        store={"store_id": "aristino_vn", "price_vnd": price, "colors": colors or [],
               "product_url": "https://x", "in_stock": True},
    )


def _graph():
    items = [_item("t", "top"), _item("b", "bottom", colors=["đỏ"]), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    return OutfitGraph(items, edges), items


def test_search_outfits_with_injected_seeds_returns_records():
    graph, _ = _graph()
    req = RecommendRequest(occasion="office")
    records = search_outfits(req, graph=graph, seed_ids=["t"])
    assert records
    assert records[0].gen_method == "graph_traversal"
    assert {i.category for i in records[0].items} >= {"top", "bottom"}


def test_search_outfits_exclude_colors_drops_matching():
    graph, _ = _graph()
    req = RecommendRequest(occasion="office", exclude_colors=["đỏ"])
    # the only assemblable outfit contains the red bottom → excluded
    assert search_outfits(req, graph=graph, seed_ids=["t"]) == []


def test_search_outfits_price_max_filters():
    graph, _ = _graph()
    req = RecommendRequest(occasion="office", price_max=500_000)  # total 900k > cap
    assert search_outfits(req, graph=graph, seed_ids=["t"]) == []
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.retrieval'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/retrieval.py`:

```python
"""Tầng 3 retrieval — Qdrant seed-filter + graph traversal assembly.

Replaces the materialized ``outfits`` collection: we filter candidate *anchor*
items (tops/dresses) on the Qdrant ``items`` collection, then assemble outfits by
walking the compatibility graph. ``seed_ids`` is injectable so the assembly path
is testable without Qdrant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from outfitmatch.kb.assemble_record import to_outfit_record
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.vocab import formalities_for_occasion

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import OutfitRecord
    from outfitmatch.pipeline import RecommendRequest


def qdrant_filter_seed_ids(
    qdrant_url: str,
    *,
    occasion: str,
    gender: str | None = None,
    collection_name: str = "items",
    limit: int = 500,
) -> list[str]:
    """Anchor item_ids (top/dress) whose formality suits ``occasion``, in stock + has store."""
    from outfitmatch.kb.qdrant_index import _close_client, _import_qdrant, _make_client

    _, models = _import_qdrant()
    client = _make_client(qdrant_url)
    try:
        must = [
            models.FieldCondition(key="category", match=models.MatchAny(any=["top", "dress"])),
            models.FieldCondition(key="in_stock", match=models.MatchValue(value=True)),
            models.FieldCondition(key="has_vn_store", match=models.MatchValue(value=True)),
            models.FieldCondition(
                key="formality",
                match=models.MatchAny(any=sorted(formalities_for_occasion(occasion))),
            ),
        ]
        if gender:
            must.append(
                models.FieldCondition(key="gender", match=models.MatchAny(any=[gender, "unisex"]))
            )
        records, _ = client.scroll(
            collection_name,
            scroll_filter=models.Filter(must=must),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [str(r.payload.get("item_id")) for r in records if r.payload]
    finally:
        _close_client(client)


def _has_excluded_color(items, exclude: set[str]) -> bool:
    return any(
        str(c).lower() in exclude for it in items for c in it.store.get("colors", []) if str(c)
    )


def search_outfits(
    request: RecommendRequest,
    *,
    graph: OutfitGraph,
    seed_ids: list[str] | None = None,
    qdrant_url: str | None = None,
    top_n: int = 40,
    config: AssemblyConfig = AssemblyConfig(),
) -> list[OutfitRecord]:
    """Assemble + filter graph outfits for a request. Returns up to ``top_n`` OutfitRecords."""
    if seed_ids is None:
        if qdrant_url is None:
            raise ValueError("provide seed_ids or qdrant_url")
        seed_ids = qdrant_filter_seed_ids(
            qdrant_url, occasion=request.occasion, gender=_request_gender(request)
        )

    exclude = {c.lower() for c in request.exclude_colors}
    records: list[OutfitRecord] = []
    for outfit in assemble_outfits(graph, seed_ids, config=config):
        total = sum(int(it.store.get("price_vnd") or 0) for it in outfit.items)
        if request.price_max and total > request.price_max:
            continue
        if exclude and _has_excluded_color(outfit.items, exclude):
            continue
        record = to_outfit_record(outfit.items, outfit.score, index=len(records) + 1)
        if request.style and request.style not in record.style:
            continue
        records.append(record)
        if len(records) >= top_n:
            break
    return records


def _request_gender(request: RecommendRequest) -> str | None:
    """No gender field on RecommendRequest yet — return None (all genders). Hook for later."""
    return None
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/retrieval.py tests/test_retrieval.py
git commit -m "feat(retrieval): Tang 3 graph traversal + seed filter + post-filter"
```

---

### Task 5: Wire `pipeline.recommend_outfit`

**Files:**
- Modify: `src/outfitmatch/pipeline.py` (`recommend_outfit:55`)
- Test: `tests/test_pipeline_v31.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_pipeline_v31.py`:

```python
def test_recommend_outfit_assembles_from_injected_graph():
    from outfitmatch.kb.graph import Edge
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord
    from outfitmatch.pipeline import RecommendRequest, recommend_outfit

    def it(i, c):
        return ItemRecord(
            item_id=i, category=c, image_path="", item_embedding=[0.1],
            gender="men", formality="smart_casual",
            store={"store_id": "aristino_vn", "price_vnd": 300_000, "colors": [],
                   "product_url": "https://x", "in_stock": True},
        )

    graph = OutfitGraph([it("t", "top"), it("b", "bottom")], [Edge("b", "t", "bottom", "top", 0.9)])
    result = recommend_outfit(
        RecommendRequest(occasion="office"), graph=graph, seed_ids=["t"]
    )
    assert len(result.outfits) >= 1
    assert result.occasion == "office"
    assert result.outfits[0].gen_method == "graph_traversal"


def test_recommend_outfit_empty_seeds_is_safe():
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.pipeline import RecommendRequest, recommend_outfit

    result = recommend_outfit(
        RecommendRequest(occasion="office"), graph=OutfitGraph([], []), seed_ids=[]
    )
    assert result.outfits == []
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/test_pipeline_v31.py::test_recommend_outfit_empty_seeds_is_safe -v`
Expected: FAIL — `NotImplementedError` (hàm chưa wire).

- [ ] **Step 3: Wire `recommend_outfit`**

Thay thân `recommend_outfit` trong `src/outfitmatch/pipeline.py` (giữ docstring), thêm imports cần thiết ở đầu file (sau khối import hiện có):

```python
def recommend_outfit(
    request: RecommendRequest,
    *,
    graph: "OutfitGraph | None" = None,
    items: "list[ItemRecord] | None" = None,
    seed_ids: list[str] | None = None,
    qdrant_url: str = "path://data/cache/qdrant",
) -> RecommendResult:
    """Orchestrate Tầng 3 (graph retrieval) + Tầng 4 (preference rerank + sizing).

    ``graph``/``items`` are injectable for tests; in production they are loaded
    from data/custom/graph + the catalog. Qwen Tầng 2 explanation is left for
    Sprint 6-7. Returns top 3-5 OutfitRecords assembled from the graph.
    """
    import time

    from outfitmatch.kb.graph_store import load_graph
    from outfitmatch.quiz.schema import quiz_to_profile
    from outfitmatch.quiz.rerank import rerank_by_preference
    from outfitmatch.quiz.sizing import suggest_sizes_for_outfit
    from outfitmatch.retrieval import search_outfits

    start = time.perf_counter()
    if graph is None:
        from outfitmatch.kb.catalog import load_catalog_items
        from scripts.data.scrape.base import CATALOG_DIR

        items = items or load_catalog_items(
            CATALOG_DIR / "catalog_metadata.parquet",
            CATALOG_DIR / "item_store_links.parquet",
        )
        graph = load_graph(items=items)

    records = search_outfits(
        request, graph=graph, seed_ids=seed_ids, qdrant_url=None if seed_ids is not None else qdrant_url
    )

    if request.quiz_answers is not None:
        pref = quiz_to_profile(request.quiz_answers)
        records = rerank_by_preference(records, pref, top_k=5)
    else:
        records = records[:5]

    sizes = (
        suggest_sizes_for_outfit(records[0].items, request.height_cm, request.weight_kg)
        if records
        else {}
    )
    return RecommendResult(
        outfits=records,
        body_shape=request.body_shape or "",
        occasion=request.occasion,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        suggested_sizes=sizes,
    )
```

Cập nhật khối `if TYPE_CHECKING:` đầu file để thêm:

```python
if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.schema import ItemRecord, OutfitRecord
    from outfitmatch.quiz.schema import QuizAnswers
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_pipeline_v31.py -v`
Expected: PASS toàn bộ (kể cả `test_recommend_result_*` cũ).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/pipeline.py tests/test_pipeline_v31.py
git commit -m "feat(pipeline): wire recommend_outfit to graph retrieval + rerank + sizing"
```

---

### Task 6: Full check + smoke E2E + docs

- [ ] **Step 1: Full test + lint**

Run: `uv run pytest -q`
Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests && uv run mypy src`
Expected: tất cả xanh. (ruff import order → `uv run ruff check --fix .`.)

- [ ] **Step 2: Smoke E2E trên graph thật (cần `item_edges.parquet` từ sub-project 1)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -c "from outfitmatch.kb.catalog import load_catalog_items; from outfitmatch.kb.graph_store import load_graph; from outfitmatch.retrieval import search_outfits; from outfitmatch.pipeline import RecommendRequest; from scripts.data.scrape.base import CATALOG_DIR; items=load_catalog_items(CATALOG_DIR/'catalog_metadata.parquet', CATALOG_DIR/'item_store_links.parquet'); g=load_graph(items=items); seeds=[it.item_id for it in items if it.category in ('top','dress')][:200]; recs=search_outfits(RecommendRequest(occasion='office'), graph=g, seed_ids=seeds, top_n=10); print('outfits:', len(recs)); print('sample cats:', [[i.category for i in r.items] for r in recs[:3]])"
```
Expected: in ra ≥1 outfit; thành phần category hợp lệ (top+bottom[+shoes...] hoặc dress+...); một số outfit có thể shoeless.

- [ ] **Step 3: Docs**

`Kien_truc_v3.1.md` §3 (Tầng 3) — thay mô tả filter-sort cũ bằng:

```markdown
- **Tầng 3 (graph traversal).** Qdrant `items` collection filter seed (top/dress)
  theo gender/formality(→occasion)/in_stock → `kb/traversal.assemble_outfits` ráp
  outfit là *clique* trong graph (mọi cặp có cạnh → coherence bất biến). shoes/
  outerwear/bag/accessory optional; outfit shoeless hợp lệ. `to_outfit_record` dựng
  OutfitRecord tag-dẫn-xuất → Tầng 4 `rerank_by_preference` không đổi. body_shape
  conditioning defer (cần item-tagging follow-up).
```

`docs/feature.md` — thêm entry tương ứng (module + lệnh smoke E2E ở Step 2).

- [ ] **Step 4: Commit**

```bash
git add Kien_truc_v3.1.md docs/feature.md
git commit -m "docs(retrieval): Tang 3 graph traversal retrieval"
```

---

## Self-Review

**1. Spec coverage**
- Qdrant seed-filter (occasion→formality, gender, in_stock, top/dress) → Task 4 `qdrant_filter_seed_ids`. ✔
- Traversal clique + shoeless + beam → Task 2. ✔
- OutfitRecord tag-dẫn-xuất (occasion/style/color) → Task 3. ✔
- Post-filter exclude_colors/price_max/style → Task 4 `search_outfits`. ✔
- Pipeline wire Tầng 3+4 + sizing + empty-safe → Task 5. ✔
- body_shape defer (no-op) → Task 3 `body_shapes_fit=[]` + flag spec §3. ✔
- Giữ `OutfitGraph`/`qdrant_index` outfits collection → không sửa. ✔

**2. Placeholder scan** — mọi step có code thật + lệnh + expected. `_request_gender` trả None có chủ đích (hook), không phải placeholder.

**3. Type consistency** — `AssembledOutfit.items/score/item_ids` khớp giữa traversal/test; `to_outfit_record(items, score, index)` chữ ký nhất quán; `search_outfits(request, *, graph, seed_ids, qdrant_url, top_n, config)` khớp pipeline gọi; `OutfitGraph.neighbors/edge_weight/item` đúng interface sub-proj 1; `occasions_for_formality`/`formalities_for_occasion` khớp Task 1.

## Out of scope
- **Item semantic tagging** (Gemini occasion/style/body_shape per node) → mở khoá body-conditioning (cần cho sub-project 3 body-ablation) + style mịn. Follow-up riêng.
- OT-labse pairwise (sub-proj 1), Qwen Tầng 2, Gradio UI, season.

## Lưu ý khi thực thi
- `FORMALITY_OCCASIONS`, `AssemblyConfig(beam=3, max_optional=3)` là khởi điểm — calibrate khi xem outfit thật + coverage (sub-project 3).
- `recommend_outfit` lazy-load graph từ disk khi không inject; production nên cache graph ở tầng app (module-level) để tránh nạp lại mỗi request.
