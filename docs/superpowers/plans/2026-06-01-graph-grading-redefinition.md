# Graph KB Grading Redefinition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Định nghĩa lại grading cho KB-graph: `recall_at_k` + `fitb_recall_at_k` (graph-native), `GraphReport` (coverage/coherence/reuse — đo diversity), CLI `eval_graph` + ablation occasion/decoding, cập nhật docs. Giữ FITB/Compat-AUC (Polyvore/OT) nguyên.

**Architecture:** `metrics/retrieval.py` (recall) + `kb/graph_eval.py` (coverage report, coherence regression-guard) tái dùng `assemble_outfits` (sub-proj 2). CLI in report + 2 ablation map được (occasion on/off = seed-filter formality; decoding = `AssemblyConfig.beam`). Body-ablation **pending item-tagging follow-up**.

**Tech Stack:** Python 3.13, `uv`, pandas, pytest, dataclasses. Không thêm dependency.

**Spec:** `docs/superpowers/specs/2026-06-01-graph-grading-redefinition-design.md`. **Depends on:** sub-project 1 (graph) + 2 (`assemble_outfits`).

> ⚠️ **Đã chốt trong plan:** Recall@5 = FITB-on-graph self-consistency; diversity = `catalog_coverage`; **body-ablation BLOCKED** (cần item-tagging). Migration materialized = chỉ **deprecate-note**, KHÔNG xoá ở plan này.

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/metrics/retrieval.py` | `recall_at_k`, `fitb_recall_at_k`, `_rank_completions` | **Create** |
| `src/outfitmatch/kb/graph_eval.py` | `GraphReport`, `evaluate_graph`, `summarize_graph_report` | **Create** |
| `scripts/data/kb/eval_graph.py` | CLI report + ablation; exit≠0 nếu coherence_violations>0 | **Create** |
| `Kien_truc_v3.1.md`, `CLAUDE.md`, `docs/EXPERIMENT_GUIDE.md` | Bảng metric + ablation map + deprecate-note | Modify |
| `tests/metrics/test_retrieval.py`, `tests/kb/test_graph_eval.py` | Test | **Create** |

---

### Task 1: `metrics/retrieval.py` — recall + FITB-on-graph

**Files:**
- Create: `src/outfitmatch/metrics/retrieval.py`
- Test: `tests/metrics/test_retrieval.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/metrics/test_retrieval.py`:

```python
from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.kb.traversal import AssembledOutfit
from outfitmatch.metrics.retrieval import fitb_recall_at_k, recall_at_k


def _item(item_id, category):
    return ItemRecord(
        item_id=item_id, category=category, image_path="", item_embedding=[0.1],
        gender="unisex", formality="casual",
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def test_recall_at_k_basic():
    assert recall_at_k(["a", "b", "c"], {"b"}, 2) == 1.0
    assert recall_at_k(["a", "b", "c"], {"z"}, 2) == 0.0
    assert recall_at_k(["a", "b"], set(), 2) == 0.0  # empty relevant


def test_fitb_recall_recovers_held_out_shoe():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes"), _item("s2", "shoes")]
    graph = OutfitGraph(
        items,
        [
            Edge("b", "t", "bottom", "top", 0.9),
            Edge("s", "t", "shoes", "top", 0.95),
            Edge("b", "s", "bottom", "shoes", 0.9),
            Edge("s2", "t", "shoes", "top", 0.2),  # weaker rival shoe
            Edge("b", "s2", "bottom", "shoes", 0.2),
        ],
    )
    outfit = AssembledOutfit(items=[items[0], items[1], items[2]], score=0.9)  # contains shoe 's'
    # masking shoes, the true shoe 's' should rank top-1 over rival 's2'
    assert fitb_recall_at_k(graph, [outfit], k=1, masked_category="shoes") == 1.0


def test_fitb_recall_zero_when_no_eligible_outfit():
    items = [_item("t", "top"), _item("b", "bottom")]
    graph = OutfitGraph(items, [Edge("b", "t", "bottom", "top", 0.9)])
    outfit = AssembledOutfit(items=items, score=0.9)  # no shoes → not eligible
    assert fitb_recall_at_k(graph, [outfit], k=5, masked_category="shoes") == 0.0
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/metrics/test_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.metrics.retrieval'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/metrics/retrieval.py`:

```python
"""Retrieval metrics for the graph KB.

``recall_at_k`` is generic. ``fitb_recall_at_k`` is a graph-native self-consistency
Recall@K: mask one item from an assembled outfit, rank the clique-valid candidates
in that category by mean edge weight, and check whether the true item is recovered
in the top-K. This needs no externally-labelled relevance set.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfitmatch.kb.graph_store import OutfitGraph
    from outfitmatch.kb.traversal import AssembledOutfit


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """|top-k ∩ relevant| / |relevant|; 0.0 when ``relevant`` is empty."""
    if not relevant:
        return 0.0
    topk = set(retrieved[:k])
    return round(len(topk & relevant) / len(relevant), 6)


def _rank_completions(
    graph: OutfitGraph, context_ids: list[str], masked_category: str
) -> list[str]:
    """Candidate ids in ``masked_category`` connected to EVERY context item, by mean weight."""
    if not context_ids:
        return []
    present = set(context_ids)
    candidate_ids: set[str] = set()
    for cid in context_ids:
        for nid, _w in graph.neighbors(cid, masked_category):
            if nid not in present:
                candidate_ids.add(nid)
    scored: list[tuple[str, float]] = []
    for cand_id in candidate_ids:
        weights = [graph.edge_weight(cand_id, cid) for cid in context_ids]
        if any(w is None for w in weights):
            continue
        scored.append((cand_id, sum(w for w in weights if w is not None) / len(weights)))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return [cid for cid, _ in scored]


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
        masked = [it for it in outfit.items if it.category == masked_category]
        context = [it for it in outfit.items if it.category != masked_category]
        if not masked or not context:
            continue
        eligible += 1
        true_id = masked[0].item_id
        ranked = _rank_completions(graph, [it.item_id for it in context], masked_category)
        if true_id in ranked[:k]:
            hits += 1
    return round(hits / eligible, 6) if eligible else 0.0
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/metrics/test_retrieval.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/metrics/retrieval.py tests/metrics/test_retrieval.py
git commit -m "feat(metrics): recall_at_k + graph-native fitb_recall_at_k"
```

---

### Task 2: `kb/graph_eval.py` — coverage + coherence report

**Files:**
- Create: `src/outfitmatch/kb/graph_eval.py`
- Test: `tests/kb/test_graph_eval.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/kb/test_graph_eval.py`:

```python
from __future__ import annotations

from outfitmatch.kb.graph import Edge
from outfitmatch.kb.graph_store import OutfitGraph
from outfitmatch.kb.graph_eval import evaluate_graph
from outfitmatch.kb.schema import ItemRecord


def _item(item_id, category, *, gender="unisex", formality="casual"):
    return ItemRecord(
        item_id=item_id, category=category, image_path="", item_embedding=[0.1],
        gender=gender, formality=formality,
        store={"price_vnd": 200_000, "colors": [], "product_url": "x", "in_stock": True},
    )


def test_evaluate_graph_coverage_and_clean_coherence():
    items = [_item("t", "top"), _item("b", "bottom"), _item("s", "shoes")]
    edges = [
        Edge("b", "t", "bottom", "top", 0.9),
        Edge("s", "t", "shoes", "top", 0.8),
        Edge("b", "s", "bottom", "shoes", 0.7),
    ]
    graph = OutfitGraph(items, edges)
    report = evaluate_graph(graph, items, edges, seed_ids=["t"])
    assert report.n_nodes == 3
    assert report.coherence_violations == 0
    assert report.catalog_coverage == 1.0  # all 3 items used in the assembled outfit
    assert report.n_assembled >= 1


def test_evaluate_graph_flags_bad_edge():
    # a manually-injected men<->women edge must be counted as a coherence violation
    items = [_item("m", "top", gender="men"), _item("w", "bottom", gender="women")]
    bad_edges = [Edge("m", "w", "top", "bottom", 0.9)]
    graph = OutfitGraph(items, bad_edges)
    report = evaluate_graph(graph, items, bad_edges, seed_ids=["m"])
    assert report.coherence_violations == 1
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `uv run pytest tests/kb/test_graph_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.kb.graph_eval'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/kb/graph_eval.py`:

```python
"""Graph KB quality report: diversity (catalog coverage) + coherence regression guard.

Replaces OutfitBuildReport for the materialized KB. ``catalog_coverage`` directly
answers the original diversity failure (1000 materialized outfits used only 4% of
the catalog). ``coherence_violations`` re-checks every edge against the gender +
formality invariants and MUST be 0 — a non-zero count means graph construction
(sub-project 1) regressed.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from outfitmatch.kb.generation import _combo_gender
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, formality_span_ok

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
        a = items_by_id.get(edge.src_id)
        b = items_by_id.get(edge.dst_id)
        if a is None or b is None:
            continue
        if _combo_gender([a, b]) is None:
            violations += 1
            continue
        formalities = [
            it.formality for it in (a, b) if it.category in FORMALITY_RELEVANT_CATEGORIES
        ]
        if not formality_span_ok(formalities):
            violations += 1
    return violations


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round(0.95 * (len(ordered) - 1)))
    return ordered[idx]


def evaluate_graph(
    graph: OutfitGraph,
    items: list[ItemRecord],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    config: AssemblyConfig = AssemblyConfig(),
) -> GraphReport:
    """Compute diversity + integrity metrics for the compatibility graph."""
    items_by_id = {it.item_id: it for it in items}
    degree: Counter[str] = Counter()
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
    """Stable human-readable summary."""
    return "\n".join(
        [
            f"nodes: {report.n_nodes}",
            f"edges: {report.n_edges}",
            f"degree_min/median/max: {report.degree_min}/{report.degree_median}/{report.degree_max}",
            f"coherence_violations: {report.coherence_violations}",
            f"catalog_coverage: {report.catalog_coverage:.4f}",
            f"distinct_items_used: {report.distinct_items_used}",
            f"assembled_outfits: {report.n_assembled}",
            f"item_reuse_p95: {report.item_reuse_p95}",
        ]
    )
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_graph_eval.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/graph_eval.py tests/kb/test_graph_eval.py
git commit -m "feat(kb): graph coverage + coherence report (diversity grading)"
```

---

### Task 3: `eval_graph.py` CLI + ablation, chạy trên graph thật

**Files:**
- Create: `scripts/data/kb/eval_graph.py`

Không có unit test mới (CLI vận hành) — kiểm bằng smoke + exit code.

- [ ] **Step 1: Viết CLI**

Tạo `scripts/data/kb/eval_graph.py`:

```python
"""Evaluate the compatibility graph KB: coverage + coherence + FITB recall + ablations.

Example:
    uv run python -m scripts.data.kb.eval_graph --seeds 300
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.graph_eval import evaluate_graph, summarize_graph_report
from outfitmatch.kb.graph_store import EDGES_PARQUET, OutfitGraph, read_edges
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.metrics.retrieval import fitb_recall_at_k
from outfitmatch.vocab import formalities_for_occasion
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.eval_graph")


def _seed_ids(items, *, occasion: str | None, limit: int) -> list[str]:
    bands = formalities_for_occasion(occasion) if occasion else None
    out = []
    for it in items:
        if it.category not in ("top", "dress"):
            continue
        if bands is not None and it.formality not in bands:
            continue
        out.append(it.item_id)
        if limit and len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the OutfitMatch compatibility graph")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges", type=Path, default=EDGES_PARQUET)
    parser.add_argument("--seeds", type=int, default=300, help="Max anchor seeds to sweep")
    parser.add_argument("--occasion", type=str, default="office", help="Occasion for ablation")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")

    items = load_catalog_items(args.catalog, args.links, genders={"men", "women", "unisex"})
    edges = read_edges(args.edges)
    graph = OutfitGraph(items, edges)

    all_seeds = _seed_ids(items, occasion=None, limit=args.seeds)
    report = evaluate_graph(graph, items, edges, all_seeds)
    logger.info("graph report:\n%s", summarize_graph_report(report))

    assembled = assemble_outfits(graph, all_seeds)
    logger.info("fitb_recall@5 (mask shoes): %.4f", fitb_recall_at_k(graph, assembled, k=5))

    # Ablation (3) occasion on/off: coverage of occasion-filtered seeds vs all
    occ_seeds = _seed_ids(items, occasion=args.occasion, limit=args.seeds)
    occ_report = evaluate_graph(graph, items, edges, occ_seeds)
    logger.info(
        "ablation occasion=%s: seeds %d→%d, coverage %.4f vs all %.4f",
        args.occasion, len(all_seeds), len(occ_seeds),
        occ_report.catalog_coverage, report.catalog_coverage,
    )

    # Ablation (4) decoding greedy(beam=1) vs beam=3
    greedy = evaluate_graph(graph, items, edges, all_seeds, config=AssemblyConfig(beam=1))
    logger.info(
        "ablation decoding: assembled greedy=%d vs beam3=%d",
        greedy.n_assembled, report.n_assembled,
    )

    if report.coherence_violations > 0:
        logger.error("coherence_violations=%d — graph build regressed", report.coherence_violations)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke import**

Run: `uv run python -c "import scripts.data.kb.eval_graph"`
Expected: import không lỗi.

- [ ] **Step 3: Chạy trên graph thật (cần `item_edges.parquet` từ sub-project 1)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.eval_graph --seeds 300
```
Expected: in GraphReport (`coherence_violations: 0`, `catalog_coverage` ≫ 0.04 của materialized cũ), `fitb_recall@5`, 2 dòng ablation occasion + decoding; exit code 0. Ghi lại các số này.

- [ ] **Step 4: Commit**

```bash
git add scripts/data/kb/eval_graph.py
git commit -m "feat(kb): eval_graph CLI (coverage + fitb recall + occasion/decoding ablation)"
```

---

### Task 4: Docs — grading mới + ablation map + deprecate-note

**Files:**
- Modify: `Kien_truc_v3.1.md`, `CLAUDE.md`, `docs/EXPERIMENT_GUIDE.md`

- [ ] **Step 1: Cập nhật bảng metric (`CLAUDE.md` §Evaluation Targets)**

Thay dòng Recall@5 + thêm coverage; ghi rõ FITB/Compat giữ nguyên:

```markdown
| Recall@5 (graph FITB) | recalibrate sau lần đo đầu | `fitb_recall_at_k` mask 1 item, traversal recover top-5 |
| Catalog coverage (diversity) | ≥ 0.60 (sơ bộ) | `GraphReport.catalog_coverage` — % item dùng trong ≥1 outfit ráp |
| Coherence violations | = 0 (hard) | `GraphReport` — edge vi phạm gender/formality |
| FITB accuracy / Compat AUC | ≥55% / ≥0.85 | OT trên Polyvore — KHÔNG đổi |
```

- [ ] **Step 2: Cập nhật 4 ablation (`CLAUDE.md` + `Kien_truc_v3.1.md` §8)**

```markdown
4 ablation (graph KB):
(1) encoder OT zero-shot vs fine-tuned — Polyvore (không đổi);
(2) body conditioning on/off — **PENDING item semantic tagging** (node chưa có body-fit tag);
(3) occasion conditioning on/off — seed-filter có/không `formalities_for_occasion` (`eval_graph --occasion`);
(4) greedy vs beam — `AssemblyConfig(beam=1)` vs `beam=3` (`eval_graph`).
```

- [ ] **Step 3: `EXPERIMENT_GUIDE.md` — quy trình eval graph**

Thêm mục:

```markdown
## Graph KB eval (v3.1 graph)
- `uv run python -m scripts.data.kb.eval_graph --seeds 300`
- Đọc: catalog_coverage (diversity), coherence_violations (phải 0), fitb_recall@5,
  ablation occasion + decoding. body-ablation chờ item-tagging follow-up.
```

- [ ] **Step 4: Deprecate-note (KHÔNG xoá code)**

Thêm docstring-note ở đầu `scripts/data/kb/generate_outfits.py` và `src/outfitmatch/kb/build_outfits.py`:

```markdown
DEPRECATED (graph KB): KB chuyển sang graph traversal (kb/graph.py, kb/traversal.py,
retrieval.py). Module materialized này giữ tạm cho legacy/so sánh; sẽ gỡ ở một dọn
dẹp riêng sau khi pipeline graph chạy E2E ổn định. Xem
docs/superpowers/specs/2026-06-01-graph-grading-redefinition-design.md §7.
```

(Thêm như comment `# DEPRECATED ...` đầu file, không đổi logic.)

- [ ] **Step 5: Commit**

```bash
git add Kien_truc_v3.1.md CLAUDE.md docs/EXPERIMENT_GUIDE.md scripts/data/kb/generate_outfits.py src/outfitmatch/kb/build_outfits.py
git commit -m "docs(grading): redefine metrics for graph KB + ablation map + deprecate notes"
```

---

## Self-Review

**1. Spec coverage**
- `recall_at_k` + `fitb_recall_at_k` graph-native → Task 1. ✔
- `GraphReport` coverage/coherence/reuse/degree → Task 2. ✔
- CLI report + occasion + decoding ablation, exit≠0 nếu coherence>0 → Task 3. ✔
- FITB/Compat AUC giữ nguyên (`metrics/outfit.py` không sửa) → không task chạm. ✔
- Body-ablation pending (flag) → Task 4 Step 2 ghi rõ. ✔
- Migration = deprecate-note, không xoá → Task 4 Step 4. ✔
- Docs grading + ablation map → Task 4. ✔

**2. Placeholder scan** — mọi step có code/nội dung thật + lệnh + expected. Số target (coverage ≥0.60, Recall recalibrate) là calibration có chủ đích, ghi rõ "sơ bộ/recalibrate".

**3. Type consistency** — `GraphReport` field khớp giữa dataclass/`evaluate_graph`/`summarize`/test; `evaluate_graph(graph, items, edges, seed_ids, *, config)` khớp CLI gọi; `fitb_recall_at_k(graph, outfits, *, k, masked_category)` khớp test + CLI; `AssembledOutfit.items/item_ids` đúng sub-proj 2; `read_edges`/`EDGES_PARQUET`/`OutfitGraph` đúng sub-proj 1.

## Out of scope
- **Item semantic tagging** (Gemini occasion/style/body_shape per node) — mở khoá body-ablation; follow-up riêng.
- **Xoá thật** code materialized — dọn dẹp riêng sau khi E2E graph ổn định.
- LLM-as-judge (Gemini), latency benchmark GPU — Sprint 9.

## Lưu ý khi thực thi
- `catalog_coverage` phụ thuộc số `--seeds`; báo cáo kèm seed count để so sánh công bằng. Tăng seeds → coverage tăng tới bão hoà.
- `fitb_recall@5` là self-consistency (không phải nhãn ngoài) — diễn giải như "graph ranking điền chỗ trống tốt đến đâu", không so trực tiếp với Recall@5 của hệ vector cũ.
- 3 sub-project nên thực thi tuần tự (1→2→3); sub-project 3 cần `item_edges.parquet` (1) và `assemble_outfits` (2).
```
