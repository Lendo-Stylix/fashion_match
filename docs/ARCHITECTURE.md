# OutfitMatch — System Architecture (v3.1-lite)

> **Agents/devs: đọc file này trước khi sửa `src/`.** File này mô tả boundaries,
> data flow, schema và trạng thái triển khai thực tế. Canonical product plan vẫn là
> [`Kien_truc_v3.1.md`](../Kien_truc_v3.1.md).

---

## 0. Implementation Snapshot

Kiến trúc thật trong repo hiện tại là **graph-first v3.1-lite**:

- **Đã chạy được:** scraper VN catalog, quality gate, item semantic tagging, graph build,
  Qdrant `items` indexing helper, graph traversal retrieval, quiz rerank, size suggestion,
  retrieval/rerank pipeline smoke path.
- **Đang là planned/stub:** Qwen3-VL model loading/fine-tuning dataset trong
  `src/outfitmatch/stylist/model.py` và `src/outfitmatch/stylist/data.py`; Gradio UI trong
  `src/outfitmatch/ui/gradio_app.py` vẫn là placeholder integration target.
- **Legacy:** materialized outfit generation + Qdrant `outfits` collection còn tồn tại để so
  sánh/benchmark, không phải primary serving path.

Current local artifacts verified in repo:

| Artifact | Current role | Snapshot |
|---|---|---|
| `data/custom/catalog/catalog_metadata.parquet` | Canonical item catalog | 5,618 rows |
| `data/custom/catalog/item_store_links.parquet` | Store/price/stock/size links | 5,618 rows |
| `data/custom/graph/item_edges.parquet` | Primary graph KB | 316,559 canonical edges |
| `data/custom/outfits/generated_outfits.parquet` | Legacy comparison path | 1,000 materialized outfits |
| `data/reports/tagging_quality/summary.json` | Item-tag audit | 0 invalid rows, 0 pending empty |
| `data/reports/outfit_tagging_quality/summary.json` | Derived outfit-tag audit | 824/824 valid core outfits |

---

## 1. System Overview — 4 Tầng v3.1-lite

```text
┌──────────────────────────────────────────────────────────────┐
│ TẦNG 1: GRAPH KB BUILDER (offline)                           │
│ VN catalog → semantic tags + item embeddings                 │
│ pair scoring + graph gates → sparse item_edges.parquet       │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│ TẦNG 2: CONVERSATIONAL STYLIST                               │
│ Tool schema + hallucination/size validation implemented       │
│ Qwen3-VL-8B + LoRA model/data are still planned stubs         │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│ TẦNG 3: RETRIEVAL ENGINE                                     │
│ Qdrant `items` seed filter or graph scan fallback             │
│ seed top/dress → clique traversal → derived OutfitRecord      │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│ TẦNG 4: PERSONALIZATION                                      │
│ QuizAnswers → PreferenceProfile → rule-based rerank          │
│ height/weight + real available sizes → size suggestion        │
└──────────────────────────────────────────────────────────────┘
```

Key architectural decision: **Qdrant is not the outfit KB.** Qdrant `items` is only a fast
seed-node filter. The canonical matching structure is `item_edges.parquet` loaded as an
`OutfitGraph`, and outfits are assembled dynamically as graph cliques.

---

## 2. Module Responsibilities

| Module | Responsibility | Status / Must NOT do |
|---|---|---|
| `src/outfitmatch/vocab.py` | Single source of truth for enum values + Vietnamese labels | ✅ Do not redefine enums elsewhere |
| `src/outfitmatch/kb/schema.py` | `ItemRecord`, `OutfitRecord` dataclasses | ✅ Schema only; no I/O/business logic |
| `src/outfitmatch/kb/catalog.py` | Load scraper parquet rows into `ItemRecord`s | ✅ No scoring/graph build |
| `src/outfitmatch/kb/tagging.py` | LLM semantic item tagging (`body_shapes_fit`, `season`, `colors`, notes) | ✅ Validates enums before writeback |
| `src/outfitmatch/kb/embedding.py` | Item embedding extraction adapter | ✅ Testable adapter interface |
| `src/outfitmatch/kb/outfit_transformer.py` | HF wrapper for `fkuyumcu/OutfitTransformer-labse` | ✅ Prototype/checkpoint wrapper |
| `src/outfitmatch/kb/pair_scoring.py` | Bounded pairwise compatibility scorer | ✅ Scoring only; edge gates stay in `graph.py` |
| `src/outfitmatch/kb/graph.py` | Category/gender/formality-gated sparse graph build | ✅ Decides allowed edges/top-K |
| `src/outfitmatch/kb/graph_store.py` | Persist/load `item_edges.parquet`; index Qdrant `items` | ✅ Storage/indexing only |
| `src/outfitmatch/kb/traversal.py` | Clique-safe outfit assembly from seed IDs | ✅ No file/Qdrant I/O |
| `src/outfitmatch/kb/assemble_record.py` | Convert assembled items to derived `OutfitRecord` | ✅ Derives outfit tags deterministically |
| `src/outfitmatch/kb/graph_eval.py` | `GraphReport`: coverage/coherence/reuse/FITB recall | ✅ Evaluation only |
| `src/outfitmatch/kb/generation.py` | Legacy materialized outfit generation | 🟡 Not primary path |
| `src/outfitmatch/kb/scoring.py` | Legacy materialized outfit scoring | 🟡 Not primary path |
| `src/outfitmatch/kb/qdrant_index.py` | Legacy Qdrant `outfits` indexing | 🟡 Comparison/migration only |
| `src/outfitmatch/retrieval.py` | Tầng 3 search: seed filter → traversal → post-filter | ✅ No training/model loading |
| `src/outfitmatch/stylist/tools.py` | `SEARCH_OUTFITS_TOOL` schema from `vocab.py` | ✅ Implemented |
| `src/outfitmatch/stylist/validation.py` | Validate outfit IDs and explicit size mentions | ✅ Implemented guardrail |
| `src/outfitmatch/stylist/model.py` | Qwen3-VL-8B + LoRA loading/inference | 🚧 `NotImplementedError` stub |
| `src/outfitmatch/stylist/data.py` | Conversation dataset loader for LoRA SFT | 🚧 `NotImplementedError` stub |
| `src/outfitmatch/quiz/schema.py` | Quiz answers/profile conversion | ✅ Implemented |
| `src/outfitmatch/quiz/rerank.py` | Preference rerank scoring | ✅ Implemented |
| `src/outfitmatch/quiz/sizing.py` | Rule-based alpha size suggestions | ✅ Implemented |
| `src/outfitmatch/metrics/outfit.py` | FITB accuracy + compatibility AUC math | ✅ Offline metric utilities |
| `src/outfitmatch/metrics/retrieval.py` | Recall@K + graph FITB recall | ✅ Graph regression metric |
| `src/outfitmatch/pipeline.py` | `RecommendRequest` → retrieval/rerank/size result | ✅ Qwen explanation deferred |
| `src/outfitmatch/ui/gradio_app.py` | Demo entry point | 🚧 Placeholder |

---

## 3. Controlled Vocabulary Invariant

`src/outfitmatch/vocab.py` is the only allowed source for controlled values:

1. Scraper normalization and catalog quality checks.
2. LLM semantic tagging prompt/output validation.
3. `search_outfits` tool schema for the stylist.
4. Qdrant `items` payload index values.
5. `OutfitRecord` derived tags and quiz preferences.

Rules:

- Internal values are English `snake_case`.
- Vietnamese display strings live only in `*_LABELS_VI` or schema display fields.
- Do **not** rename existing enum values; old parquet/Qdrant payloads would become invalid.
- New enum values require tests and migration consideration for existing artifacts.

---

## 4. Data Flow

### 4.1 Offline catalog and graph build

```text
scripts/data/scrape/*
  → data/custom/catalog/catalog_metadata.parquet
  → data/custom/catalog/item_store_links.parquet
  → src/outfitmatch/kb/catalog.py loads ItemRecord
  → scripts/data/kb/tag_items.py writes semantic item tags/colors/notes
  → src/outfitmatch/kb/pair_scoring.py scores valid pairs
  → src/outfitmatch/kb/graph.py applies category/gender/formality gates
  → src/outfitmatch/kb/graph_store.py writes data/custom/graph/item_edges.parquet
  → optional Qdrant `items` index for seed filtering
```

### 4.2 Runtime retrieval path

```text
RecommendRequest / search_outfits filters
  → qdrant_filter_seed_ids() for top/dress seeds, or direct graph scan fallback
  → assemble_outfits() builds clique-valid candidate outfits
  → to_outfit_record() derives occasion/style/body/season/color/price fields
  → post-filter style, body_shape, price_max, exclude_colors
  → rerank_by_preference() if quiz answers are present
  → suggest_sizes_for_outfit() if height/weight + item sizes are available
  → RecommendResult
```

### 4.3 Planned conversational path

```text
User text/image
  → Qwen3-VL parse intent or ask follow-up
  → Qwen calls search_outfits tool
  → retrieval/rerank returns allowed OutfitRecords
  → validate_response() blocks hallucinated OF_ IDs
  → validate_sizes() blocks impossible explicit sizes
  → Vietnamese explanation + UI/API response
```

The final Qwen explanation generation is **not implemented yet**; `pipeline.py` currently keeps
`explanation_vi` empty or deterministic/testable.

---

## 5. Knowledge Base Schema

Graph KB stores **item nodes** plus **canonical item-item edges**. `OutfitRecord` is derived at
retrieval time.

```jsonc
// ItemRecord node
{
  "item_id": "item_custom_00001",
  "category": "top",
  "image_path": "data/custom/catalog/images/item_custom_00001.webp",
  "item_embedding": [/* encoder dimension inferred from checkpoint/data */],
  "gender": "women",
  "formality": "smart_casual",
  "body_shapes_fit": ["pear", "rectangle"],
  "season": ["summer", "transitional"],
  "stylist_notes_vi": "Áo dáng suông dễ phối.",
  "store": {
    "store_id": "canifa_vn",
    "product_url": "https://...",
    "price_vnd": 299000,
    "colors": ["beige", "navy"],
    "in_stock": true,
    "available_sizes": ["S", "M", "L"],
    "sizes_in_stock": ["M", "L"]
  }
}

// OutfitRecord derived from graph traversal
{
  "outfit_id": "OF_00001",
  "schema_version": "3.1",
  "items": [/* clique item nodes */],
  "compatibility_score": 0.87,
  "occasion": ["office", "cafe_hangout"],
  "style": ["minimalist", "korean"],
  "body_shapes_fit": ["pear"],
  "season": ["transitional"],
  "color_palette": ["beige", "navy"],
  "price_total_vnd": 850000,
  "price_tier": "mid",
  "has_vn_store": true,
  "gen_method": "graph_traversal"
}
```

Derivation rules in `assemble_record.py`:

- `occasion`: from outfit formality via `FORMALITY_OCCASIONS`.
- `style`: from item/store `style_tags`.
- `body_shapes_fit` / `season`: from primary garments (`dress`, `top`, `bottom`, `outerwear`),
  preferring shared tags and falling back to union when needed.
- `color_palette`: from item colors.
- `price_tier`: derived from total VND price.

---

## 6. Retrieval Design Details

`src/outfitmatch/retrieval.py` implements `search_outfits()`:

1. Candidate seed IDs are `top` / `dress` nodes.
2. Occasion is converted to allowed formality bands (`formalities_for_occasion`).
3. Qdrant `items` filters by category/gender/formality/stock/store when available.
4. If Qdrant is unavailable or no `seed_ids` are provided in tests, retrieval scans graph nodes.
5. `traversal.py` builds clique-safe combinations. Valid cores are:
   - `dress` (+ optional shoes/outerwear/bag/accessory)
   - `top + bottom` (+ optional shoes/outerwear/bag/accessory)
6. `assemble_record.py` derives outfit-level metadata.
7. Post-filters apply style/body/price/color constraints.
8. Results are sorted/deduplicated by score.

Important nuance: shoes are **preferred but not a hard validity requirement** because catalog shoe
coverage is sparse. Audits report shoeless valid cores as `missing_recommended_shoes` low severity,
not invalid outfits.

---

## 7. Operational Scripts

| Script | Purpose |
|---|---|
| `scripts/data/scrape/run.py` | Crawl supported VN stores, normalize, quality-gate, write catalog parquets/images |
| `scripts/data/scrape/quality.py` | Validate persisted catalog/link outputs |
| `scripts/data/scrape/retag_catalog.py` | Re-run category/gender/formality mapping from raw cache without re-crawl |
| `scripts/data/kb/tag_items.py` | Run semantic item tagging and write validated tags/colors/notes to catalog |
| `scripts/data/kb/audit_tagging_quality.py` | Read-only audit of item semantic tags |
| `scripts/data/kb/build_graph.py` | Build/persist graph KB and optionally index Qdrant `items` |
| `scripts/data/kb/eval_graph.py` | Evaluate coverage/coherence/reuse/FITB recall and ablations |
| `scripts/data/kb/audit_outfit_tags.py` | Read-only audit of derived outfit tags from traversal |
| `scripts/data/kb/eval_tagging_models.py` | Small same-sample tagging model evaluation |
| `scripts/data/kb/eval_turboquant_tagging_large.py` | Large local vision model tagging benchmark |
| `scripts/data/kb/generate_outfits.py` | Legacy materialized outfit generation |
| `scripts/setup_databases.py` | Local database/Qdrant setup helper |

---

## 8. Guardrails

### Hallucinated outfit IDs

```python
from outfitmatch.stylist.validation import validate_response

ok, invalid_ids = validate_response(response_text, valid_outfit_id_set)
if not ok:
    # Do not show response; regenerate or fallback.
    ...
```

### Hallucinated sizes

Only explicit mentions like `size M` / `cỡ L` are validated. The allowed set must come from real
`available_sizes` / `sizes_in_stock` in `item_store_links.parquet`.

### Data quality gates

- Scraper batches must pass `quality.check_frames()` before merge.
- Semantic tags are sanitized/validated against `vocab.py` before writeback.
- Graph edges are category/gender/formality-gated.
- Graph reports must keep `coherence_violations = 0`.

---

## 9. Grading Targets and Current Guards

| Metric | Target / role | Current note |
|---|---|---|
| Recall@5 graph FITB | Regression guard | Full-sweep baseline historically ≈ 0.98 |
| Catalog coverage | ≥ 0.60 full-sweep | Graph report target |
| Coherence violations | = 0 hard | Edge gate regression guard |
| FITB accuracy | ≥ 55% | OT-labse Polyvore benchmark, separate from VN catalog |
| Compatibility AUC | ≥ 0.85 | OT-labse Polyvore benchmark |
| Body-cond. Precision@5 | Requires semantic tags | Item tags now available; final benchmark still to run |
| E2E latency | < 5–8s GPU/cloud | Pending real Qwen/UI integration |
| LLM-as-judge | mean ≥ 3.5/5 | Pending final E2E outputs |

Required ablations:

1. Encoder variants — OT-labse zero-shot vs fine-tuned Polyvore.
2. Body conditioning on/off — now unblocked by item semantic tags, final eval still pending.
3. Occasion conditioning on/off — `eval_graph` with/without formality mapping.
4. Greedy vs beam — `AssemblyConfig(beam=1)` vs beam 3.

---

## 10. Python / Tooling Constraints

| Không dùng | Dùng thay |
|---|---|
| `mediapipe` | Không cần pose-extract trong v3.1-lite |
| `faiss-cpu` pip | `qdrant-client` + Docker Qdrant |
| `black` / `flake8` / `isort` | `ruff` |
| `flask` | `fastapi` + `uvicorn` nếu cần API |
| `streamlit` | `gradio` |
| `AutoModelForCausalLM` cho Qwen3-VL | `Qwen3VLForConditionalGeneration` |
| `evaluation_strategy` | `eval_strategy` |

Quality commands:

```bash
make test-fast
make test
make lint
make format
```

---

## 11. Definition of Done

Feature DONE khi:

1. Code có test tương ứng và CI xanh.
2. Public functions có docstring.
3. Enum/schema thay đổi được phản ánh trong `vocab.py`, docs, tests, và data migration notes.
4. Entry được cập nhật trong `docs/feature.md`.
5. Nếu đụng graph/retrieval: chạy/audit graph guard (`eval_graph` hoặc focused tests) và đảm bảo
   không sinh invalid core / coherence violations.
