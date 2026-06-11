# OutfitMatch — Báo cáo Cấu trúc Project

> Mục tiêu của file này: giúp một thành viên mới hiểu **repo đang có gì, luồng nào là chính,
> folder nào để làm gì, file nào là source-of-truth**, và phần nào vẫn là planned/stub.

OutfitMatch hiện dùng kiến trúc **v3.1-lite graph-first**. Đường dẫn production/MVP chính không
phải là vector-search outfit đã materialize sẵn, mà là:

```text
VN store catalog
  → ItemRecord nodes
  → semantic item tags + item embeddings
  → sparse item compatibility graph (`item_edges.parquet`)
  → seed item filtering (`top`/`dress`) bằng Qdrant `items` hoặc graph scan fallback
  → clique-safe traversal ráp outfit động
  → derived OutfitRecord
  → quiz preference rerank + size suggestion
```

Materialized outfit files và Qdrant `outfits` vẫn còn trong repo, nhưng hiện được xem là
**legacy/comparison path**.

---

## 1. Executive Summary

| Khu vực | Vai trò | Trạng thái hiện tại |
|---|---|---|
| `src/outfitmatch/vocab.py` | Vocabulary enum/source of truth | ✅ Implemented |
| `src/outfitmatch/kb/` | Tầng 1 — KB schema/catalog/tagging/graph/traversal/eval | ✅ Core graph path implemented |
| `src/outfitmatch/retrieval.py` | Tầng 3 — search_outfits graph retrieval | ✅ Implemented |
| `src/outfitmatch/quiz/` | Tầng 4 — quiz profile/rerank/sizing | ✅ Implemented |
| `src/outfitmatch/pipeline.py` | Request/result orchestration | ✅ Retrieval/rerank path implemented; Qwen explanation deferred |
| `src/outfitmatch/stylist/` | Tầng 2 — tool schema, validation, Qwen model/data | 🟡 Validation/tool done; model/data stubs |
| `src/outfitmatch/ui/` | Gradio app | 🚧 Placeholder |
| `scripts/data/scrape/` | Catalog collection pipeline | ✅ Implemented with batch quality gate |
| `scripts/data/kb/` | Build/tag/audit/eval CLIs | ✅ Implemented for graph path + legacy helpers |
| `tests/` | Unit/regression tests | ✅ Mirrors source/script domains |
| `data/custom/` | Local generated artifacts | ✅ Contains current catalog/graph/legacy outfits |
| `data/reports/` | Audit reports | ✅ Contains tagging/outfit audit summaries |

---

## 2. Top-level Repo Map

```text
fashion_match_project/
├── Kien_truc_v3.1.md              # Canonical product/architecture plan
├── CLAUDE.md                      # Agent/dev operating instructions
├── README.md                      # Quickstart + current status
├── pyproject.toml                 # Python 3.13 deps, ruff, mypy, pytest config
├── Makefile                       # install/test/lint/format/qdrant/demo shortcuts
├── docker-compose.yml             # Qdrant local service
├── src/outfitmatch/               # Importable app/library package
├── scripts/                       # Operational CLIs, data pipelines, DB setup
├── tests/                         # Unit/regression tests
├── docs/                          # Architecture, experiments, dataset contract, reports
├── data/                          # Local/generated data artifacts and reports
└── .pi/                           # Project-level Pi agent/skill config
```

Mental model:

- **`src/`** is reusable library/application code.
- **`scripts/`** is how we operate data pipelines and build artifacts.
- **`tests/`** verifies both library code and operational scripts.
- **`docs/`** explains the design, status, and experiment protocol.
- **`data/`** is generated/local state. Treat artifacts as reproducible outputs unless explicitly
  committed as baselines.

---

## 3. `src/outfitmatch/` — Application Package

```text
src/outfitmatch/
├── __init__.py
├── vocab.py
├── seeding.py
├── pipeline.py
├── retrieval.py
├── kb/
├── stylist/
├── quiz/
├── metrics/
└── ui/
```

### 3.1 `vocab.py` — Controlled Vocabulary

This is the **single source of truth** for enum-like values used across scraping, tagging,
Qdrant payloads, tool schemas, quiz preferences, and derived outfit records.

Contains/exports:

- occasion/style/body shape/season/price tier/item category/gender/formality/skin tone values;
- Vietnamese display labels (`*_LABELS_VI`);
- frozen sets for validation;
- helpers such as `validate_enum_values()`, `occasions_for_formality()`,
  `formalities_for_occasion()`.

Do not duplicate enum constants in other modules. If a value changes here, existing parquet and
Qdrant payloads may need migration.

### 3.2 `seeding.py`

Small deterministic seeding helper. Used by tests/experiments when reproducibility matters.

### 3.3 `pipeline.py`

Defines the public E2E request/result objects:

- `RecommendRequest`: occasion, style/body/skin/price/color filters, height/weight, quiz answers,
  optional image path.
- `RecommendResult`: selected outfits, body/occasion, Vietnamese explanation field, latency,
  suggested sizes.
- `recommend_outfit()`: currently wires graph retrieval → quiz rerank → size suggestion.

Important: full Qwen3-VL response generation is still deferred, so `pipeline.py` should be read as
an orchestrator for the deterministic retrieval/personalization path, not the final chat UX.

### 3.4 `retrieval.py`

Primary Tầng 3 retrieval implementation.

Main responsibilities:

1. Convert request filters into seed-node constraints.
2. Use Qdrant `items` for `top`/`dress` seed filtering when available.
3. Fall back to graph scan for tests/offline runs.
4. Call `kb.traversal.assemble_outfits()`.
5. Convert candidates via `kb.assemble_record.to_outfit_record()`.
6. Post-filter style/body/price/excluded colors.
7. Return ranked `OutfitRecord`s.

This module must not load/train Qwen models. It is the deterministic retrieval service underneath
future tool-calling.

---

## 4. `src/outfitmatch/kb/` — Tầng 1 Knowledge Base

```text
src/outfitmatch/kb/
├── schema.py
├── catalog.py
├── tagging.py
├── embedding.py
├── outfit_transformer.py
├── pair_scoring.py
├── graph.py
├── graph_store.py
├── traversal.py
├── assemble_record.py
├── graph_eval.py
├── generation.py          # legacy materialized path
├── scoring.py             # legacy materialized path
├── build_outfits.py       # legacy/materialized helper
├── evaluation.py          # legacy/metric helper
└── qdrant_index.py        # legacy Qdrant `outfits`
```

### 4.1 `schema.py`

Defines the two canonical dataclasses:

- `ItemRecord`: one store catalog item/node, including category, image, embedding, gender,
  formality, body/season tags, and store metadata.
- `OutfitRecord`: standard outfit shape used by retrieval/rerank/UI. In the graph path it is
  derived dynamically from assembled item nodes.

The schema version is `3.1` for traceability.

### 4.2 `catalog.py`

Loads `data/custom/catalog/catalog_metadata.parquet` and `item_store_links.parquet` into
`ItemRecord` objects. It is the adapter between scraper outputs and graph/retrieval code.

Important behavior:

- can filter by gender (`men|women|unisex` for adult graph builds);
- can filter stock/store availability;
- preserves store fields such as price, URL, colors, sizes.

### 4.3 `tagging.py`

Semantic item tagging layer for graph KB. It calls Gemini/OpenAI-compatible/local backends,
parses/sanitizes JSON payloads, validates controlled fields, and mutates `ItemRecord`s with:

- `body_shapes_fit`;
- `season`;
- `colors`;
- `stylist_notes_vi`.

It is intentionally item-level. Outfit-level body/season tags are derived later by
`assemble_record.py`.

### 4.4 `embedding.py` and `outfit_transformer.py`

Embedding adapter and OutfitTransformer-labse checkpoint wrapper. The code is designed so tests can
inject lightweight encoders while production can use `fkuyumcu/OutfitTransformer-labse`.

### 4.5 `pair_scoring.py`

Defines a pluggable pair-scoring protocol plus deterministic heuristic scorer. The scorer returns
bounded compatibility weights; it does not decide whether an edge is structurally allowed.

### 4.6 `graph.py`

Builds sparse compatibility edges between item nodes. Structural gates live here:

- category compatibility (avoid invalid pairs like top-top);
- gender compatibility;
- formality compatibility;
- top-K neighbor retention per partner category.

Output rows become canonical edges with `src_id`, `dst_id`, category columns, and `weight`.

### 4.7 `graph_store.py`

Storage/indexing for the graph path:

- writes/reads `data/custom/graph/item_edges.parquet`;
- loads an in-memory `OutfitGraph` adjacency;
- creates/indexes Qdrant `items` collection for seed filtering.

Qdrant `items` is a speed/index layer. The graph parquet remains the canonical matching artifact.

### 4.8 `traversal.py`

Assembles clique-safe outfits from seed item IDs. Valid clothing cores:

- `dress`;
- `top + bottom`.

Shoes, outerwear, bags, and accessories are optional completion items. Shoes are preferred but not
hard-required because current shoe catalog coverage is small.

### 4.9 `assemble_record.py`

Converts assembled item sets into `OutfitRecord`s. It derives occasion, style, body/season tags,
color palette, price totals/tiers, and `gen_method="graph_traversal"`.

### 4.10 `graph_eval.py`

Graph-native evaluation. Produces `GraphReport` fields such as catalog coverage, coherence
violations, degree stats, number of assembled outfits, item reuse p95, and graph FITB recall.

### 4.11 Legacy materialized modules

`generation.py`, `scoring.py`, `build_outfits.py`, `evaluation.py`, and `qdrant_index.py` support the
older materialized outfit path. Keep them for comparison; do not treat them as current serving.

---

## 5. `src/outfitmatch/stylist/` — Tầng 2 Stylist

```text
src/outfitmatch/stylist/
├── tools.py
├── validation.py
├── model.py
└── data.py
```

Implemented now:

- `tools.py`: `SEARCH_OUTFITS_TOOL`, with enum parameters sourced from `vocab.py`.
- `validation.py`: validates `OF_xxxxx` references and explicit size mentions.

Still planned/stub:

- `model.py`: `load_stylist_model()` raises `NotImplementedError`.
- `data.py`: `load_conversation_dataset()` raises `NotImplementedError`.

So this folder currently provides contracts and guardrails, not a finished chat model.

---

## 6. `src/outfitmatch/quiz/` — Tầng 4 Personalization

```text
src/outfitmatch/quiz/
├── schema.py
├── rerank.py
└── sizing.py
```

- `schema.py`: `QuizAnswers`, `PreferenceProfile`, `quiz_to_profile()`.
- `rerank.py`: additive rule-based preference scoring and top-K rerank.
- `sizing.py`: maps height/weight/gender to alpha clothing sizes and intersects with real
  `available_sizes` / `sizes_in_stock` from store links.

---

## 7. `src/outfitmatch/metrics/`

```text
src/outfitmatch/metrics/
├── outfit.py
└── retrieval.py
```

- `outfit.py`: FITB accuracy and compatibility AUC utilities for Polyvore/OT-labse evaluation.
- `retrieval.py`: generic Recall@K and graph-native FITB recall used by `graph_eval.py`.

VN graph retrieval and Polyvore encoder grading are separate evaluation streams.

---

## 8. `src/outfitmatch/ui/`

`gradio_app.py` is currently a Sprint 8 placeholder. `make demo` points here, but final UI/API
integration still needs real `recommend_outfit()` calls, product cards, store links, images, and
feedback.

---

## 9. `scripts/` — Operational Commands

```text
scripts/
├── setup_databases.py
└── data/
    ├── scrape/
    └── kb/
```

Scripts are operational entry points, not core library APIs.

### 9.1 `scripts/data/scrape/`

```text
scripts/data/scrape/
├── README.md / QUICKSTART.md
├── config.py / base.py
├── build_registry.py
├── run.py / run.bat
├── shopify.py / sitemap.py
├── normalize.py
├── category_map.py / store_category_map.py
├── gender_map.py / formality_map.py
├── quality.py / batch_gate.py / manifest.py
├── download_images.py
└── retag_catalog.py
```

Purpose: build the VN catalog input stream.

```text
StoreConfig registry
  → adapter fetches raw products/sitemaps
  → raw cache under data/cache/raw/<store_id>/
  → normalize to catalog/link rows
  → batch quality gate
  → write catalog_metadata.parquet + item_store_links.parquet + images
```

Currently supported adapter-backed stores: YODY, Canifa, Aristino, Huelley Rose, Dirty Coins, and
Rubies.

### 9.2 `scripts/data/kb/`

```text
scripts/data/kb/
├── build_graph.py
├── eval_graph.py
├── tag_items.py
├── audit_tagging_quality.py
├── audit_outfit_tags.py
├── eval_tagging_models.py
├── eval_turboquant_tagging_large.py
└── generate_outfits.py
```

Purpose: operate the KB after catalog exists.

- `tag_items.py`: semantic item tagging writeback.
- `audit_tagging_quality.py`: validates and samples item semantic tags.
- `build_graph.py`: builds canonical `item_edges.parquet` and optionally Qdrant `items`.
- `eval_graph.py`: graph coverage/coherence/FITB recall and ablations.
- `audit_outfit_tags.py`: validates derived outfit records from traversal.
- `eval_tagging_models.py`, `eval_turboquant_tagging_large.py`: model-selection tooling for semantic tagging.
- `generate_outfits.py`: legacy materialized outfit snapshot builder.

---

## 10. `tests/` — Test Layout

```text
tests/
├── conftest.py
├── test_vocab.py
├── test_retrieval.py
├── test_pipeline_v31.py
├── test_stylist.py
├── test_quiz.py
├── test_seeding.py
├── kb/
├── data/scrape/
├── metrics/
└── quiz/
```

Important groups:

- `tests/kb/`: schema, catalog, embedding, graph, traversal, assemble record, graph store, tagging, audit, graph eval, and legacy materialized helpers.
- `tests/data/scrape/`: scraper adapters, normalization, maps, manifest, batch gate, and quality checks.
- `tests/metrics/`: graph retrieval metrics.
- top-level tests: cross-layer contracts such as pipeline, stylist validation, retrieval, vocab.

Common commands:

```bash
uv run pytest tests/kb -v
uv run pytest tests/data/scrape -v
uv run pytest tests/test_retrieval.py tests/test_pipeline_v31.py -v
make test-fast
make test
```

---

## 11. `docs/` — Documentation Layout

```text
docs/
├── ARCHITECTURE.md
├── PROJECT_STRUCTURE.md
├── SPRINT_REPORT.md
├── EXPERIMENT_GUIDE.md
├── feature.md
├── datasets/
├── presentation/
└── superpowers/
```

- `ARCHITECTURE.md`: module boundaries and data flow.
- `PROJECT_STRUCTURE.md`: this detailed folder report.
- `SPRINT_REPORT.md`: Scrum/XP progress and metric snapshot.
- `EXPERIMENT_GUIDE.md`: evaluation workflow and ablation instructions.
- `feature.md`: feature log by implemented module.
- `datasets/STORE_CATALOG_VN.md`: catalog schema/data contract.
- `superpowers/plans` and `superpowers/specs`: implementation plans/specs retained as project history.

---

## 12. `data/` — Local Artifacts

```text
data/
├── cache/
│   ├── raw/<store_id>/
│   └── store_registry.db
├── custom/
│   ├── catalog/
│   │   ├── catalog_metadata.parquet
│   │   ├── item_store_links.parquet
│   │   ├── scrape_manifest.json
│   │   └── images/
│   ├── graph/
│   │   └── item_edges.parquet
│   └── outfits/
│       └── generated_outfits*.parquet
└── reports/
    ├── tagging_quality/
    └── outfit_tagging_quality/
```

Current verified snapshot:

| Artifact | Count / quality |
|---|---|
| Catalog rows | 5,618 |
| Store-link rows | 5,618 |
| Stores | aristino_vn, canifa_vn, dirtycoins, huelleyrose, rubies, yody_vn |
| Adult graph nodes loaded with `men|women|unisex` | 4,694 |
| Graph edges | 316,559 |
| Legacy generated outfits | 1,000 |
| Item semantic tag audit | 5,618 non-empty, 0 pending empty, 0 invalid rows |
| Derived outfit audit | 824 valid core outfits, 816 complete-with-shoes, 8 shoeless valid cores, 0 invalid rows |

Do not blindly delete `data/cache/raw/`: it allows re-tagging/re-normalization without hitting live
store websites.

---

## 13. Main Developer Workflows

### 13.1 Scrape/refresh catalog

```bash
uv run python -m scripts.data.scrape.run --store yody_vn --limit 20 --no-images --dry-run
uv run python -m scripts.data.scrape.run
uv run python -m scripts.data.scrape.quality
```

### 13.2 Re-tag catalog categories without re-crawl

```bash
uv run python -m scripts.data.scrape.retag_catalog --dry-run
uv run python -m scripts.data.scrape.retag_catalog
```

### 13.3 Semantic item tagging

```bash
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.tag_items --limit 50
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.audit_tagging_quality
```

### 13.4 Build/evaluate graph KB

```bash
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.build_graph --no-qdrant
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.audit_outfit_tags
```

### 13.5 Validate codebase

```bash
make test-fast
make test
make lint
```

---

## 14. How to Read This Repo Quickly

If you only have 30 minutes:

1. Read `README.md` for status.
2. Read `docs/ARCHITECTURE.md` sections 0–6.
3. Inspect `src/outfitmatch/vocab.py` to understand legal values.
4. Inspect `src/outfitmatch/kb/schema.py` for data shape.
5. Inspect `src/outfitmatch/retrieval.py` and `src/outfitmatch/kb/traversal.py` for runtime graph search.
6. Inspect `scripts/data/kb/build_graph.py`, `eval_graph.py`, and `tag_items.py` for operational flow.
7. Run focused tests for the area you plan to change.

---

## 15. Current Gaps / Next Engineering Work

1. Implement Qwen3-VL loading/inference in `stylist/model.py`.
2. Implement conversation dataset loader/generation flow in `stylist/data.py`.
3. Wire Gradio UI to real `recommend_outfit()` results.
4. Add API endpoint (`POST /recommend`) if demo needs service mode.
5. Run final body-conditioning evaluation now that item semantic tags exist.
6. Keep improving shoe coverage to reduce shoeless-but-valid graph outfits.
7. Refresh sprint/feature docs whenever an artifact or module contract changes.
