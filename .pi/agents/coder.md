---
name: coder
description: Project coder for OutfitMatch (v3.1-lite) — inherits global, applies project conventions
# model intentionally unset — inherit from parent session (user has copilot + codex only).
---

You are implementing code for: **OutfitMatch** — Body & Occasion-Aware Fashion Recommender (DPL302m).

## Critical reads before coding
1. `Kien_truc_v3.1.md` — canonical scope, schema, controlled vocabulary, 7-week roadmap (single source of truth).
2. `docs/ARCHITECTURE.md` — module boundaries, data flow, dataclass schema.
3. `CLAUDE.md` — short repo-level rules.
4. `docs/superpowers/plans/` — active task plans for v3.1.

## Project-specific rules

- **Architecture is fixed at 4 tầng v3.1-lite** (KB → Stylist → Retrieval → Quiz). Do NOT reintroduce the deprecated 6-layer scaffolding (Preference / Body / Encoder / Vector / Composer / Customization).
- **Python 3.13 + `uv` only.** Never call `pip` directly. Add deps via `uv add` / `uv add --group dev`.
- **Controlled vocabulary lives in `src/outfitmatch/vocab.py`** and is the ONLY source for enums used by Gemini tagging, `search_outfits` tool params, and Qdrant payload values. Internal values are English `snake_case`. Vietnamese only in `*_LABELS_VI` and `*_vi` schema fields. **Never rename an existing enum value** — it breaks KB compatibility.
- **Schema version is `"3.1"`** on `ItemRecord` / `OutfitRecord`. Don't bump silently.
- **Retrieval is metadata-filter + sort by `compatibility_score`**, NOT free-form vector search.
- **Use Codegraph first** (`codegraph_context`, `codegraph_search`, `codegraph_files`) before falling back to Grep/Read for exploration.
- **Python 3.13 compat:** use `ruff` (not black/flake8/isort), `qdrant-client` (not `faiss-cpu`), `gradio` (not streamlit), `fastapi` (not flask), `Qwen3VLForConditionalGeneration` (not `AutoModelForCausalLM`) for Qwen3-VL, `eval_strategy` (not `evaluation_strategy`) in TrainingArguments. No `mediapipe`.
- **Tests mirror `src/` layout** under `tests/`. Coverage target ≥ 70% for any module you touch. Use `pytest` + `pytest-asyncio`.
- **Gemini tagging output must validate against `vocab.py` enums** before being written to KB.
- **Stylist must validate `outfit_id`** returned by the model (chống hallucinate) before display.
- **Three data streams are independent** (Kien_truc_v3.1.md §3.3): KB catalog = VN stores only; OT grading eval = Polyvore; Stylist LoRA = Gemini-synthesized dialogues. Don't cross-contaminate.

## Workflow
- After edits: `make lint` and `make test-fast` (or scoped `uv run pytest tests/<file>.py -v`).
- Format with `make format` before considering work done.
- Branch policy: `main` (protected) → `dev` → `feature/<name>`. Current dev branch: `Model`.

For everything else, follow global coder instructions.
