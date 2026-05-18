# OutfitMatch

Body & Occasion-Aware Fashion Recommender — DPL302m Deep Learning project (10-week grading phase).

## Quick Start

```bash
# 1. Install (requires Python 3.13 + uv)
uv sync --group dev

# 2. Start vector store
make qdrant-up

# 3. Run demo
make demo
```

## Run Experiments

```bash
# Single experiment (dry-run)
uv run om-exp run configs/encoder/clip_zs.yaml --dry-run

# Full experiment cycle
uv run om-exp sweep configs/encoder/ --out-csv docs/experiments/ablation_encoder.csv
```

## Documentation

| File | Contents |
|---|---|
| `docs/ARCHITECTURE.md` | System design, module boundaries, interfaces — **read before coding** |
| `docs/EXPERIMENT_GUIDE.md` | How to run & interpret experiment cycles |
| `docs/experiments/RESULTS.md` | Aggregated ablation results (generated) |
| `CLAUDE.md` | Claude Code guidance for this repo |

## Team

| Role | Owner |
|---|---|
| ML Lead (encoder, composer, ablations) | Nhật Quang |
| Data & Backend (pipeline, API, CI/CD) | TBD |
| Vision & Frontend (body pipeline, Gradio) | TBD |
