# Experiment Guide — OutfitMatch (v3.1-lite + Grading)

> Read `docs/ARCHITECTURE.md` first. This file explains both the v3.1-lite product eval and the grading experiment workflow.

---

## Two Evaluation Tracks

| Track | Purpose | When |
|---|---|---|
| **v3.1-lite product eval** | LLM-as-judge, E2E latency, body-conditional precision | Sprint 9 |
| **Grading experiment cycles** | Encoder ablations, FITB accuracy, Compatibility AUC | Continuous via `om-exp sweep` |

---

## v3.1-lite Evaluation (Sprint 9)

### LLM-as-Judge (Gemini)

Rate each `RecommendResult` on a 1–5 scale using Gemini as judge. Target: mean ≥ 3.5/5.

```bash
uv run python scripts/llm_judge.py \
    --results data/eval/recommend_results.jsonl \
    --out docs/experiments/llm_judge_results.csv
```

### Body-Conditional Precision@5 Ablation (v3.1-lite Tầng 3)

Compare Qdrant retrieval with and without `body_shapes_fit` filter. Target: +10pp with filter ON.

```bash
uv run python scripts/ablation_body_filter.py \
    --out docs/experiments/ablation_body_filter_v31.csv
```

### E2E Latency Measurement

```bash
# Target: < 5-8s on GPU with streaming UX
uv run python scripts/measure_latency.py \
    --n-requests 50 \
    --out docs/experiments/latency_v31.csv
```

### Ablation 4 — Greedy vs Beam Decoding (KB Build)

Baked into Tầng 1 KB build pipeline (`Kien_truc_v3.1.md` §3.4 Bước 3). Measure FITB accuracy of resulting KB under each method:

```bash
uv run python scripts/ablation_decoding.py \
    --kb-greedy data/kb/kb_greedy.parquet \
    --kb-beam   data/kb/kb_beam.parquet \
    --out docs/experiments/ablation_decoding.csv
```

---

## Grading Experiment Cycles (encoder / composer)

---

## Quick Start: Running a Grading Experiment

```bash
# 1. Start vector store
make qdrant-up

# 2. Single experiment (dry-run check)
uv run om-exp run configs/encoder/clip_zs.yaml --dry-run

# 3. Single experiment (real run, logs to W&B offline)
uv run om-exp run configs/encoder/clip_zs.yaml

# 4. Full cycle (all configs in a directory)
uv run om-exp sweep configs/encoder/ --out-csv docs/experiments/ablation_encoder.csv

# 5. View results
cat docs/experiments/ablation_encoder.csv
```

---

## Experiment Cycle Structure

Each cycle is a directory of YAML configs that differ on **exactly one axis**:

```
configs/
  encoder/       # Axis: model (4 YAML files, same dataset/rows)
  dataset/       # Axis: dataset type (3 YAML files, same model/rows)
  rows/          # Axis: max_rows (3 YAML files, same model/dataset)
  composer/      # Axis: dataset config + conditioning (5 YAML files)
  body/          # Axis: pose model (2 YAML files)
```

Results accumulate in `docs/experiments/<ablation_name>.csv`. The `name` field in the YAML is the row key.

---

## W&B Dashboard

All runs log to project `outfitmatch-grading`. Group by:
- `group` = directory name (e.g. `encoder`, `rows`)
- `job_type` = task (`retrieval`, `fitb`, `compatibility`)

Key metrics logged per run:
- `recall@1`, `recall@5`, `recall@10`, `map` (retrieval)
- `fitb_accuracy` (composer)
- `compatibility_auc` (composer)
- `train/loss` per step (during fine-tuning)

To sync offline runs: `uv run wandb sync wandb/offline-run-*/`

---

## Adding a New Experiment Config

1. Copy the closest existing YAML from `configs/<axis>/`.
2. Change `name` to a unique, descriptive string (e.g. `encoder-dinov2-zs`).
3. Change the ONE field that represents the axis (e.g. `model.checkpoint`).
4. Run `uv run om-exp run configs/<axis>/<new>.yaml --dry-run` to validate.
5. Run it for real; it will auto-append to the CSV.

**Do not change multiple axes in one config** — this breaks ablation interpretability.

---

## Evaluating Results

Use the aggregation script:

```bash
uv run python scripts/aggregate_ablations.py
# writes docs/experiments/RESULTS.md
```

RESULTS.md contains one comparison table per axis with the winning row bolded. This is the source for the final report's Experiments section.

---

## Saving Model Checkpoints

Fine-tuned models are saved to `models/checkpoints/<name>.pt`. They are **not committed** (in `.gitignore`). Track them with DVC:

```bash
dvc add models/checkpoints/encoder-fashionsiglip-ft.pt
git add models/checkpoints/encoder-fashionsiglip-ft.pt.dvc
git commit -m "chore: track fine-tuned encoder checkpoint with DVC"
dvc push
```

---

## Dataset Sizes Reference

| HF Dataset | HF Config | Split | Rows | Size |
|---|---|---|---:|---:|
| `Marqo/deepfashion-inshop` | default | data | 52.6K | 216 MB |
| `Marqo/deepfashion-multimodal` | default | data | 42.5K | 153 MB |
| `Marqo/fashion200k` | default | data | 201.6K | 3.5 GB |
| `owj0421/polyvore-outfits` | disjoint_fill_in_the_blank | train | 17.0K | small |
| `owj0421/polyvore-outfits` | nondisjoint_fill_in_the_blank | train | 53.3K | small |
| `owj0421/polyvore-outfits` | disjoint_compatibility | train | 34.0K | small |
| `owj0421/polyvore-outfits` | nondisjoint_compatibility | train | 106.6K | small |

Row-count scaling cycle uses `max_rows: 5000 / 25000 / 100000 / null` on top of these.
