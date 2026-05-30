# Feature Log

Each merged feature gets one entry here. Format: `## feature-name` → brief description → sprint.

---

## vocab — Controlled Vocabulary

`src/outfitmatch/vocab.py` — single source of truth for all enum values (OCCASION, STYLE, BODY_SHAPE, SEASON, PRICE_TIER, ITEM_CATEGORY, SKIN_TONE). Frozen sets for O(1) membership checks. Vietnamese labels in `*_LABELS_VI` dicts (display-only). `validate_enum_values()` helper used by Gemini LLM-tagging pipeline to reject stray values before writing to KB.

Sprint 0 — scaffolding. Commit: `feat: add controlled vocabulary module (vocab.py) for v3.1-lite`

---

## kb-schema — Knowledge Base Data Types

`src/outfitmatch/kb/schema.py` — `ItemRecord` (per-item catalog entry with VN store block) and `OutfitRecord` (full KB entry with `to_qdrant_payload()`). `schema_version="3.1"` for traceability. `occasion` + `style` as primary conditioning fields (enum-typed, ready for token conditioning in Phụ lục A). `gen_method` tracks FITB-beam vs random-scored origin.

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

## pipeline-v31 — v3.1-lite E2E Request/Result Types

`src/outfitmatch/pipeline.py` — `RecommendRequest` (occasion required; everything else optional: height_cm, weight_kg, style, body_shape, skin_tone, price_max, exclude_colors, quiz_answers, image_path) and `RecommendResult` (outfits, body_shape, occasion, explanation_vi, latency_ms) establishing the v3.1-lite pipeline contract.

Full pipeline implementation in Sprint 5–8. See `docs/ARCHITECTURE.md §7` for the flow.

Sprint 0 — scaffolding. Commit: `refactor: update pipeline.py to v3.1-lite RecommendRequest/Result flow`

---

## vn-catalog-scraper — Store Catalog Collection Pipeline

`scripts/data/scrape/` — operational VN fashion catalog scraper for the Tầng 1 KB input stream. Seeds `data/cache/store_registry.db`, collects product rows into `data/custom/catalog/catalog_metadata.parquet` + `item_store_links.parquet`, and downloads local images under `data/custom/catalog/images/`.

Adapters support Shopify `/products.json`, sitemap + per-product JSON (Aristino/Haravan-style), and sitemap + HTML OpenGraph/embedded-price fallback (YODY/Canifa). Normalization validates item categories against `vocab.py`, applies price guards, and preserves stable `item_id`s across re-scrapes via `(store_id, source_product_id)`.

Sprint 0/1 — dataset ingestion tooling. Commit: pending

---

## catalog-quality — Scraped Catalog Validation

`scripts/data/scrape/quality.py` — CLI/reporting checks for the canonical scraper outputs: required Parquet columns, unique `item_id`, unique item-store links, valid `ITEM_CATEGORY`, non-empty titles, JSON-list colors, existing local images, catalog/link join integrity, registered `store_id`, absolute product URLs, sane prices, and sale-price consistency.

Current validated scrape: `6242` items / `6242` links across YODY, Canifa, Aristino, Huelleyrose, Dirtycoins, and Rubies. Hard errors are zero; remaining warning is empty descriptions for some rows, acceptable because downstream Gemini tagging can use title/image.

Sprint 1 — data QA. Commit: pending

---

## outfit-transformer-prototype — HF Checkpoint Wrapper + KB Generation Prototype

`src/outfitmatch/kb/outfit_transformer.py` — HuggingFace cache wrapper for `fkuyumcu/OutfitTransformer-labse`, config reader, and local `OutfitTransformerCIR` loader. Verified snapshot contains `config.json`, `model.py`, `pytorch_model.bin`, and `README.md`; checkpoint loads on CPU and returns a `(1, 128)` embedding for dummy features.

`src/outfitmatch/kb/embedding.py` now accepts testable encoder adapters (`encode_items` / `encode_item`). `src/outfitmatch/kb/generation.py` includes deterministic prototype generation for valid category rules: `(top + bottom + shoes)` or `(dress + shoes)`, with optional outerwear/bag/accessory and placeholder metadata ready for later OT re-scoring/tagging.

Sprint 1/3 — OT experiment scaffold. Commit: pending

---

## outfit-combination-build — Deterministic Outfit Combination Output

`src/outfitmatch/kb/catalog.py` loads validated scraper Parquet files into `ItemRecord`s and samples each category across its price range to avoid overfitting to early-scraped stores. `src/outfitmatch/kb/scoring.py` now has a deterministic `HeuristicOutfitScorer` baseline plus generic `rescore_outfits()`; later OT-labse scorer adapters can use the same interface.

`src/outfitmatch/kb/build_outfits.py` mixes FITB-beam and random-scored candidates, re-scores, renumbers `OF_00001...`, and writes Parquet-friendly rows. Operational CLI: `uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60`.

Current generated output: `data/custom/outfits/generated_outfits.parquet` with `1000` valid outfits (`700` FITB-beam / `300` random-scored), `1000` unique item combinations, score range `0.65–0.98`, and zero invalid category-rule combinations. Price-tier balancing now targets affordable users by default (`budget=0.20`, `mid=0.50`, `premium=0.30`) and the latest build hit the target exactly (`max_price_tier_deviation=0.0000`).

Sprint 1/3 — KB combination prototype. Commit: pending
