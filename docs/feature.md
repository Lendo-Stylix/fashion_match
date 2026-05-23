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
