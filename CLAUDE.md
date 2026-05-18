# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical: Read Before Coding

- **`docs/ARCHITECTURE.md`** — module boundaries, data flow, BaseEncoder interface, dataset schemas, experiment cycle design. Read before touching any `src/` file.
- **`docs/EXPERIMENT_GUIDE.md`** — how to run cycles, add configs, interpret results, use W&B.
- **`docs/superpowers/plans/2026-05-18-outfitmatch-experiment-cycles.md`** — full sprint/task plan with bite-sized TDD steps.

---

## Project Overview

**OutfitMatch** — Body & Occasion-Aware Fashion Recommender (DPL302m grading project, Sprints 0–9, 10 weeks).

Multimodal DL system: given a user selfie + height/weight + occasion, recommend compatible outfits from a fashion catalog. Core pipeline: body shape classification → catalog retrieval (Fashion-SigLIP) → Transformer outfit composition.

## Python & Package Manager

- **Python 3.13** (see `.python-version`)
- **Package manager: `uv`** (not pip directly)

## Commands

```bash
# Setup
uv sync                          # install production deps
uv sync --group dev              # install dev deps + pre-commit

# Development
make demo                        # run Gradio UI (src/ui/gradio_app.py)
make api                         # run FastAPI server on :8000 (reload)
make qdrant-up                   # start Qdrant vector DB via Docker

# Quality
make test                        # pytest + coverage report
make lint                        # ruff check + ruff format --check + mypy
make format                      # ruff format + ruff check --fix

# Run a single test file
uv run pytest tests/path/to/test_file.py -v

# Run a single test function
uv run pytest tests/path/to/test_file.py::test_function_name -v
```

## Source Layout

```
src/outfitmatch/
  config.py          # ExperimentConfig pydantic + yaml loader
  seeding.py         # set_seed
  tracking.py        # W&B init wrapper
  cli.py             # om-exp CLI (run / sweep)
  runner.py          # config → train → eval → W&B
  pipeline.py        # E2E recommend_outfit orchestrator
  data/              # HF dataset loaders (RetrievalDataset, Polyvore*)
  encoders/          # BaseEncoder ABC + HfClipEncoder + OpenClipEncoder + factory
  metrics/           # pure functions: recall_at_k, fitb_accuracy, compat_auc
  eval/              # evaluate_retrieval (encoder + dataset → metric dict)
  train/             # SigLIP contrastive trainer + OutfitTransformer
  body/              # PoseExtractor (YOLO) + rule-based shape classifier
  ui/                # Gradio demo
configs/             # YAML experiment configs (one axis per subdirectory)
tests/               # pytest, mirrors src structure
docs/                # ARCHITECTURE.md, EXPERIMENT_GUIDE.md, experiments/
```

## Architecture (5 layers) — see `docs/ARCHITECTURE.md` for full detail

1. **Body** (`src/body/`): YOLOv8-pose keypoints → 5-class shape rule classifier → `body_vector`.
2. **Encoder** (`src/encoders/`): `Marqo/marqo-fashionSigLIP` (fine-tuned) via `BaseEncoder` ABC.
3. **Vector Store**: Qdrant Docker (`:6333`), collection `catalog`.
4. **Composer** (`src/train/composer.py`): OutfitTransformer — 4-layer, 8-head, d=512, `[BODY]`/`[OCC]` tokens.
5. **Customization**: Qdrant filter + composer re-rank → `POST /customize-item`.

Module boundaries and interfaces (BaseEncoder, dataset schemas, config contract) are defined in `docs/ARCHITECTURE.md` — do not violate them.

## API Endpoints

- `POST /recommend` — `{image_b64, height, weight, occasion}` → outfit suggestion (E2E latency target: <3s CPU)
- `POST /search` — `{query_text}` → top-K catalog items
- `POST /customize-item` — `{outfit_id, item_slot, target_attrs}` → replacement items

## Python 3.13 Compatibility Constraints

| Do NOT use | Use instead |
|---|---|
| `mediapipe` (no cp313 wheel) | `ultralytics` (YOLOv8-pose) |
| `faiss-cpu` via pip (no cp313 wheel) | `qdrant-client` + Docker, or `usearch` |
| `black`, `flake8`, `isort` | `ruff` (covers all three) |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |

FAISS via conda (`faiss-cpu=1.14.1`) works if the team uses conda, but Qdrant is the primary vector store.

## Tooling

- **Linter/formatter**: `ruff` (target `py313`, line-length 100, selects E/F/I/UP/B/SIM)
- **Type checker**: `mypy` (non-strict, `ignore_missing_imports = true`)
- **Tests**: `pytest` + `pytest-asyncio` (asyncio_mode="auto"), `pytest-cov`; test coverage target ≥70%
- **Experiment tracking**: Weights & Biases (`wandb`) — project `outfitmatch-grading`
- **Data versioning**: DVC with Google Drive remote
- **Occasion labeling**: Gemini API (`google-generativeai`) with `diskcache` to avoid re-calling

## Branch & Definition of Done

Branch policy: `main` (protected) → `dev` → `feature/<name>`

A feature is **done** when:
1. PR merged to `dev` with ≥1 peer review
2. `pytest` coverage ≥70%, CI (GitHub Actions) green
3. Docstring present + entry added to `docs/feature.md`
4. Reproducible end-to-end via `make demo`

## Evaluation Targets (grading criteria)

| Metric | Target |
|---|---|
| Recall@5 (catalog retrieval) | CLIP zero-shot + 5% |
| FITB accuracy | ≥55% |
| Compatibility AUC | ≥0.85 |
| Body-conditional Precision@5 | +10% vs non-conditional baseline |
| E2E latency | <3s on CPU |
| LLM-as-judge (Gemini) | Mean ≥3.5/5 |

Required ablations: (1) encoder variants, (2) body conditioning on/off, (3) occasion conditioning on/off, (4) greedy vs beam decoding.
