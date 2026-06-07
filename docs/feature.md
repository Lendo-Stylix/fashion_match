# Feature Log

Each merged feature gets one entry here. Format: `## feature-name` → brief description → sprint.

---

## vocab — Controlled Vocabulary

`src/outfitmatch/vocab.py` — single source of truth for all enum values (OCCASION, STYLE, BODY_SHAPE, SEASON, PRICE_TIER, ITEM_CATEGORY, SKIN_TONE). Frozen sets for O(1) membership checks. Vietnamese labels in `*_LABELS_VI` dicts (display-only). `validate_enum_values()` helper used by Gemini LLM-tagging pipeline to reject stray values before writing to KB.

Sprint 0 — scaffolding. Commit: `feat: add controlled vocabulary module (vocab.py) for v3.1-lite`

---

## kb-schema — Knowledge Base Data Types

`src/outfitmatch/kb/schema.py` — `ItemRecord` (graph/item-node catalog entry with VN store block) and `OutfitRecord` (standard derived/legacy outfit shape used across retrieval, rerank, validation, and serialization). `schema_version="3.1"` for traceability. `occasion` + `style` remain primary conditioning fields; in the graph path they are derived when assembling outfits from item nodes. `gen_method` distinguishes `graph_traversal` from legacy materialized builders like FITB-beam / random-scored.

Sprint 0 — scaffolding. Commit: `feat: add kb/ module scaffold (schema + stubs for Sprint 1-4)`

---

## stylist-tools — Qwen3-VL Tool Definition + Hallucination Check

`src/outfitmatch/stylist/tools.py` — `SEARCH_OUTFITS_TOOL` dict with enum-typed parameters sourced directly from `vocab.py` (guarantees consistency with Qdrant payload indexes).

`src/outfitmatch/stylist/validation.py` — `extract_outfit_ids()` (regex `OF_\d{5,}`) and `validate_response()` for post-generation hallucination detection. Any unrecognised outfit_id blocks the response from being shown to the user.

Sprint 0 — scaffolding. Commit: `feat: add stylist/ module (tools + validation fully implemented, model stub)`

---

## quiz-rerank — Preference-Based Re-rank

`src/outfitmatch/quiz/schema.py` — `QuizAnswers` (5-question onboarding: style, occasions, favorite_colors, price_tier, height/weight), `PreferenceProfile`, `quiz_to_profile()`.

`src/outfitmatch/quiz/rerank.py` — `score_outfit_for_preference()` (additive scoring: style match +0.10/hit, occasion match +0.10/hit, color match +0.05/hit, wrong price_tier −0.10) and `rerank_by_preference()` returns sorted Top-K.

Sprint 0 — scaffolding. Commit: `feat: add quiz/ module (QuizAnswers, PreferenceProfile, preference re-rank)`

---

## quiz-sizing — Rule-Based Body → Size Suggestion

`src/outfitmatch/quiz/sizing.py` — deterministic resolver mapping `(height_cm, weight_kg, gender)` to an alpha clothing size for `top`, `dress`, and `outerwear`, then intersecting with the item's real `sizes_in_stock` / `available_sizes`. Numeric bottoms and footwear stay display-only in MVP.

`src/outfitmatch/stylist/validation.py` also adds `extract_size_mentions()` and `validate_sizes()` so Qwen3-VL may present a size but cannot hallucinate one the store does not carry.

Sprint 8 — sizing support for runtime personalization. Commit: pending

---

## pipeline-v31 — v3.1-lite E2E Request/Result Types

`src/outfitmatch/pipeline.py` defines `RecommendRequest` (occasion required; everything else optional: height_cm, weight_kg, style, body_shape, skin_tone, price_max, exclude_colors, quiz_answers, image_path) and `RecommendResult` (outfits, body_shape, occasion, explanation_vi, latency_ms, suggested_sizes). `recommend_outfit()` now wires Tầng 3 graph retrieval into Tầng 4 quiz rerank + runtime size suggestion, with injectable `graph` / `seed_ids` / `qdrant_url` hooks for tests and smoke runs.

Qwen explanation generation is still deferred, so `explanation_vi` stays empty here; the retrieval/personalization path is fully runnable. See `docs/ARCHITECTURE.md §7` for the broader flow.

Sprint 5/8 — graph retrieval pipeline wire-up. Commit: pending

---

## vn-catalog-scraper — Store Catalog Collection Pipeline

`scripts/data/scrape/` — operational VN fashion catalog scraper for the Tầng 1 KB input stream. Seeds `data/cache/store_registry.db`, collects product rows into `data/custom/catalog/catalog_metadata.parquet` + `item_store_links.parquet`, and downloads local images under `data/custom/catalog/images/`.

Adapters support Shopify `/products.json`, sitemap + per-product JSON (Aristino/Haravan-style), and sitemap + HTML OpenGraph/embedded-price fallback (YODY/Canifa). Normalization validates item categories against `vocab.py`, applies price guards, preserves stable `item_id`s across re-scrapes via `(store_id, source_product_id)`, and now captures per-item `available_sizes` / `sizes_in_stock` from variant options for runtime size suggestion.

Sprint 0/1 — dataset ingestion tooling. Commit: pending

---

## scrape-batch-gate — Per-Batch Scrape Quality Gate

`scripts/data/scrape/batch_gate.py` splits each store into `--batch-size` chunks, reuses in-memory `quality.check_frames()` before merge, and quarantines only the failing batches. `scripts/data/scrape/manifest.py` records batch outcomes in `data/custom/catalog/scrape_manifest.json` so `run.py --rescrape-failed` can retry only the quality-failed chunks instead of re-scraping everything.

This keeps bad data out of the main catalog parquet, makes reruns resumable, and lets agent sessions close the loop `scrape -> quarantine -> regression test -> fix -> rerun` without manual bookkeeping.

Sprint 1 — scrape reliability / batch QA. Commit: pending

---

## catalog-quality — Scraped Catalog Validation

`scripts/data/scrape/quality.py` — CLI/reporting checks for the canonical scraper outputs: required Parquet columns, unique `item_id`, unique item-store links, valid `ITEM_CATEGORY`, non-empty titles, JSON-list colors, existing local images, catalog/link join integrity, registered `store_id`, absolute product URLs, sane prices, and sale-price consistency.

Current validated scrape: `5618` items / `5618` links across YODY, Canifa, Aristino, Huelleyrose, Dirtycoins, and Rubies. All `25` manifest batches passed with no quarantine directory. Hard errors are zero; remaining warning is `empty_description` on `556` rows, acceptable because downstream Gemini tagging can use title/image.

Sprint 1 — data QA. Commit: pending

---

## outfit-transformer-prototype — HF Checkpoint Wrapper + KB Generation Prototype

`src/outfitmatch/kb/outfit_transformer.py` — HuggingFace cache wrapper for `fkuyumcu/OutfitTransformer-labse`, config reader, and local `OutfitTransformerCIR` loader. Verified snapshot contains `config.json`, `model.py`, `pytorch_model.bin`, and `README.md`; checkpoint loads on CPU and returns a `(1, 128)` embedding for dummy features.

`src/outfitmatch/kb/embedding.py` now accepts testable encoder adapters (`encode_items` / `encode_item`). `src/outfitmatch/kb/generation.py` includes deterministic prototype generation for valid category rules: `(top + bottom + shoes)` or `(dress + shoes)`, with optional outerwear/bag/accessory and placeholder metadata ready for later OT re-scoring/tagging.

Sprint 1/3 — OT experiment scaffold. Commit: pending

---

## qdrant-index — Legacy Outfit Collection Indexing

`src/outfitmatch/kb/qdrant_index.py` creates the legacy `outfits` collection with Cosine dense vectors and payload indexes for `occasion`, `style`, `body_shapes_fit`, `price_tier`, `season`, and `has_vn_store`. `index_outfits()` infers vector dimension from populated `OutfitRecord.outfit_embedding`, validates consistent embedding shape, creates the collection on demand, and batch-upserts one Qdrant point per outfit.

This module is **no longer the primary retrieval path**. Current graph retrieval uses `src/outfitmatch/kb/graph_store.py` to index **item nodes** into Qdrant `items`, then `src/outfitmatch/retrieval.py` performs seed filtering + graph traversal. Keep `qdrant_index.py` only for legacy comparison / migration support.

Qdrant point IDs are deterministic UUID5 values derived from `outfit_id` because raw IDs like `OF_00001` are not valid Qdrant point IDs; the canonical ID remains in payload as `payload["outfit_id"]` for validation/retrieval display.

Sprint 3/5 — legacy materialized indexing implementation. Commit: pending

---

## outfit-graph-kb — Compatibility Graph Construction

`src/outfitmatch/kb/pair_scoring.py` adds a pluggable `PairScorer` protocol plus deterministic `HeuristicPairScorer` for sparse graph edge weights. `src/outfitmatch/kb/graph.py` builds canonical item-item edges only when category, gender, and formality constraints all hold, then keeps top-K neighbors per partner category.

`src/outfitmatch/kb/graph_store.py` persists `data/custom/graph/item_edges.parquet`, loads an in-memory `OutfitGraph` adjacency (`neighbors()` / `edge_weight()` / `item()`), and indexes item nodes into Qdrant `items` with filterable payload fields for future seed-node retrieval. Operational CLI: `uv run python -m scripts.data.kb.build_graph` (`--incremental`, `--no-qdrant`, `--limit-per-category`).

Current adult-catalog graph build (`men|women|unisex`): `4694` item nodes, `316103` canonical edges, build time `27.4s`, degree min/median/max `60 / 76 / 2809`, and no forbidden `top-top` / `top-dress` edges in the output parquet.

Sprint 1/3 — Graph KB construction + storage. Commit: pending

---

## graph-retrieval — Seed Filter + Clique Traversal + Derived OutfitRecord

`src/outfitmatch/retrieval.py` replaces materialized-outfit lookup with Tầng 3 graph retrieval: filter anchor `top` / `dress` items on Qdrant `items` by formality→occasion, stock, and store availability; fall back to a direct graph scan when Qdrant seeds are unavailable; then assemble clique-safe outfits via `src/outfitmatch/kb/traversal.py`.

`src/outfitmatch/kb/tagging.py` now implements Gemini item semantic tagging for the graph path: validate enum-constrained `body_shapes_fit` / `season`, cache responses with `diskcache`, and mutate `ItemRecord`s in place. Operational CLI: `uv run python -m scripts.data.kb.tag_items` writes validated tags back into `data/custom/catalog/catalog_metadata.parquet`.

`src/outfitmatch/kb/assemble_record.py` converts assembled item sets back into standard `OutfitRecord`s by deriving `occasion` from formality, `style` from store `style_tags`, and `color_palette` from item colors. Outfit `body_shapes_fit` / `season` now derive deterministically from primary garments (`dress`, `top`, `bottom`, `outerwear`): prefer shared tags, fall back to the union when needed, preserve canonical vocab order, and ignore accessory-driven body-shape pollution.
`src/outfitmatch/kb/traversal.py` treats `dress` and `top+bottom` as valid clothing cores; `shoes` remain an optional-but-preferred completion item so the graph can return usable outfits even while shoe coverage is sparse.
`scripts/data/kb/audit_outfit_tags.py` audits derived `OutfitRecord` metadata read-only from graph traversal outputs, validates enum/core-shape integrity, distinguishes invalid cores from shoeless-but-valid outfits (`missing_recommended_shoes`), and writes CSV/JSON reports under `data/reports/outfit_tagging_quality/`.

Smoke E2E on the real graph: `uv run python -c "from outfitmatch.kb.catalog import load_catalog_items; from outfitmatch.kb.graph_store import load_graph; from outfitmatch.retrieval import search_outfits; from outfitmatch.pipeline import RecommendRequest; from scripts.data.scrape.base import CATALOG_DIR; items=load_catalog_items(CATALOG_DIR/'catalog_metadata.parquet', CATALOG_DIR/'item_store_links.parquet'); graph=load_graph(items=items); seeds=[it.item_id for it in items if it.category in ('top','dress')][:200]; recs=search_outfits(RecommendRequest(occasion='office'), graph=graph, seed_ids=seeds, top_n=10); print('outfits:', len(recs)); print('sample cats:', [[item.category for item in rec.items] for rec in recs[:3]])"`.

Sprint 2/3 — Graph traversal retrieval + pipeline integration; item semantic tagging follow-up implemented for graph KB. Commit: pending

---

## graph-grading — Coverage / Coherence / FITB Recall for Graph KB

`src/outfitmatch/metrics/retrieval.py` adds generic `recall_at_k()` plus graph-native `fitb_recall_at_k()`: mask one item from an assembled outfit, rank clique-valid completions by mean edge weight, and measure top-K recovery. `src/outfitmatch/kb/graph_eval.py` replaces materialized-KB diversity grading with `GraphReport` (`catalog_coverage`, `coherence_violations`, degree stats, reuse p95).

Operational CLI: `uv run python -m scripts.data.kb.eval_graph --seeds 0 --occasion office` for full-sweep grading, or `--seeds 300` for a quick sanity sweep. Current full-sweep baseline on the adult graph: `4694` nodes, `316103` edges, `catalog_coverage=0.7069`, `coherence_violations=0`, `fitb_recall@5=0.9813`, `n_assembled=7350`, `item_reuse_p95=27`. Occasion ablation (`office`) drops coverage to `0.3613`; greedy traversal (`beam=1`) drops coverage to `0.6451`.

Sprint 3/3 — Graph-native grading + ablation harness. Commit: pending

---

## outfit-combination-build — Deterministic Outfit Combination Output

`src/outfitmatch/kb/catalog.py` loads validated scraper Parquet files into `ItemRecord`s and samples each category across its price range to avoid overfitting to early-scraped stores. `src/outfitmatch/kb/scoring.py` now has a deterministic `HeuristicOutfitScorer` baseline plus generic `rescore_outfits()`; later OT-labse scorer adapters can use the same interface.

`src/outfitmatch/kb/build_outfits.py` mixes FITB-beam and random-scored candidates, re-scores, renumbers `OF_00001...`, and writes Parquet-friendly rows. Operational CLI: `uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60`.

Current generated output: `data/custom/outfits/generated_outfits.parquet` with `1000` valid outfits (`700` FITB-beam / `300` random-scored), `1000` unique item combinations, score range `0.60–0.98`, zero invalid category-rule combinations, zero mixed-gender outfits, and zero formality-clash outfits. Price-tier balancing now targets affordable users by default (`budget=0.20`, `mid=0.50`, `premium=0.30`) and the latest build hit the target exactly (`max_price_tier_deviation=0.0000`).

Sprint 1/3 — KB combination prototype. Commit: pending
