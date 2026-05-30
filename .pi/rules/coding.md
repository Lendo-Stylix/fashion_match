# OutfitMatch Coding Conventions

## Language & tooling
- **Python 3.13** (see `.python-version`).
- **Package manager: `uv`** — never call `pip` directly. Add deps via `uv add` or `uv add --group dev`.
- **Linter/formatter:** `ruff` (target `py313`, line-length 100, rules `E/F/I/UP/B/SIM`).
- **Type checker:** `mypy` (non-strict, `ignore_missing_imports=true`).
- **Tests:** `pytest` + `pytest-asyncio`. Coverage ≥ 70% on touched modules.

## File organization
- Source under `src/outfitmatch/`, tests mirror under `tests/`.
- Module boundaries follow the 4-tầng v3.1-lite split: `kb/`, `stylist/`, `quiz/`, `metrics/`, plus top-level `vocab.py`, `pipeline.py`, `seeding.py`, `ui/`.
- One v3.1 module → one test file (e.g. `src/outfitmatch/quiz/rerank.py` → `tests/quiz/test_rerank.py`).
- Do not create new top-level packages without updating `docs/ARCHITECTURE.md`.

## Naming
- Functions / variables / modules: `snake_case`.
- Classes / dataclasses: `PascalCase`.
- Enum / vocabulary internal values: English `snake_case` (e.g. `office_formal`, `pear`). Vietnamese display strings only in `*_LABELS_VI` constants and `*_vi` schema fields.
- Test functions: `test_<unit>_<behavior>`.

## Schema & vocabulary invariants
- `ItemRecord` / `OutfitRecord` have `schema_version="3.1"`. Don't bump silently.
- **Never rename an existing enum value in `vocab.py`** — it breaks the indexed KB.
  Adding new values is fine; deletions/renames require a KB rebuild plan.
- All enum-typed inputs (Gemini tagging output, `search_outfits` tool args, Qdrant payload writes) MUST round-trip through the validator in `vocab.py`.

## Architecture rules
- 4 tầng only (KB → Stylist → Retrieval → Quiz). Do not reintroduce the deprecated 6-layer code.
- Retrieval is **metadata filter + sort by precomputed `compatibility_score`**, not free-form vector similarity.
- Stylist responses must pass `extract_outfit_ids` + `validate_response` before being shown to the user.

## Forbidden / replaced
| Don't use | Use instead |
|---|---|
| `pip install ...` | `uv add ...` |
| `black` / `flake8` / `isort` | `ruff` |
| `faiss-cpu` (no cp313 wheel) | `qdrant-client` + Docker |
| `mediapipe` (no cp313 wheel) | _(not needed in v3.1)_ |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |
| `AutoModelForCausalLM` for Qwen3-VL | `Qwen3VLForConditionalGeneration` |
| `evaluation_strategy=` in `TrainingArguments` | `eval_strategy=` |
| Free-form vector search on outfits | Qdrant payload-filter + sort by `compatibility_score` |

## Definition of Done (per feature)
1. PR merged to `dev` with ≥ 1 peer review.
2. `pytest` coverage ≥ 70% on touched modules; CI (GitHub Actions) green.
3. Docstring on public functions + entry in `docs/feature.md`.
4. Reproducible E2E via `make demo`.

## Quick commands
```bash
make test            # full pytest + coverage
make test-fast       # fail-fast, no coverage
make lint            # ruff check + ruff format --check + mypy
make format          # ruff format + ruff check --fix
uv run pytest tests/<file>.py::<test_fn> -v
```
