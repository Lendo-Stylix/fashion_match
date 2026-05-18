# OutfitMatch — System Architecture

> **Agents: read this file before writing any code.** It defines module boundaries, data flow, and the invariants every module must respect. Violating these boundaries breaks experiment reproducibility.

---

## 1. System Overview

OutfitMatch is a 5-layer fashion recommendation pipeline:

```
User input (image + height + weight + occasion)
        │
        ▼
┌────────────────────┐
│  Layer 1: Body     │  PoseExtractor (YOLO-pose) → keypoints
│  Understanding     │  → rule-based shape classifier → 5-class label
│  src/body/         │  → body_vector: [shape_embed(512) ‖ bmi ‖ ratios]
└─────────┬──────────┘
          │ body_vector
          ▼
┌────────────────────┐
│  Layer 2: Catalog  │  Marqo/marqo-fashionSigLIP (fine-tuned)
│  Encoder           │  image + text → L2-normalised embedding
│  src/encoders/     │  BaseEncoder ABC: encode_image / encode_text
└─────────┬──────────┘
          │ item embeddings
          ▼
┌────────────────────┐
│  Layer 3: Vector   │  Qdrant (Docker :6333) — collection "catalog"
│  Store / Retrieval │  ANN query with payload filters (category, color)
└─────────┬──────────┘
          │ candidate items
          ▼
┌────────────────────┐
│  Layer 4: Outfit   │  OutfitTransformer (Sarkar 2022, arXiv:2204.04812)
│  Composer          │  Tokens: [CLS] [BODY] [OCC] [item×N]
│  src/train/        │  Trained on Polyvore FITB — 4-layer, 8-head, d=512
└─────────┬──────────┘
          │ ranked outfit
          ▼
┌────────────────────┐
│  Layer 5: Item     │  Qdrant filter (color, fit, style) + re-rank
│  Customization     │  API: POST /customize-item
└────────────────────┘
          │
          ▼
   Gradio demo / FastAPI
```

---

## 2. Module Responsibilities

Each module has ONE responsibility. Do not mix concerns.

| Module | Responsibility | Must NOT do |
|---|---|---|
| `src/outfitmatch/config.py` | Load + validate YAML experiment configs | Execute training or I/O |
| `src/outfitmatch/data/` | Load HF datasets, cap rows, return dicts | Encode images; call models |
| `src/outfitmatch/encoders/` | Embed images/text via `BaseEncoder` ABC | Load datasets; write to disk |
| `src/outfitmatch/metrics/` | Pure metric functions (no I/O, no model calls) | Log to W&B; call encoders |
| `src/outfitmatch/eval/` | Compose encoder + dataset + metrics → dict | Save models; call W&B |
| `src/outfitmatch/train/` | Training loops (contrastive, composer) | Load configs directly |
| `src/outfitmatch/body/` | Pose extraction; rule-based body shape | Encode fashion items |
| `src/outfitmatch/runner.py` | Wire config → data → train → eval → W&B | Business logic |
| `src/outfitmatch/cli.py` | CLI entrypoint via Typer | Training logic |
| `src/outfitmatch/ui/` | Gradio UI | Model training |

---

## 3. Experiment Config Contract

Every experiment is a YAML file consumed by `ExperimentConfig` (pydantic). Fields:

```yaml
name: string           # W&B run name, also the CSV row key
seed: int              # set_seed() called before any model init
task: retrieval|fitb|compatibility
model:
  kind: hf_clip|open_clip
  checkpoint: string   # HF repo ID or open_clip "hf-hub:X" string
  pretrained: string?  # open_clip pretrained tag (optional)
  finetune: bool       # if true, runner calls finetune_encoder
dataset:
  hf_id: string        # HuggingFace dataset ID
  config: string?      # HF dataset config name
  split: string        # default "data"
  max_rows: int?       # null = use all rows (data-scaling axis)
train:
  epochs: int
  batch_size: int
  lr: float
  weight_decay: float
  num_workers: int
composer:              # only needed for task=fitb/compatibility
  n_heads: int
  n_layers: int
  use_body: bool
  use_occ: bool
wandb_project: string  # default "outfitmatch-grading"
```

**Invariant:** `max_rows` is the ONLY way to vary dataset size. Never hard-code slice logic in model or trainer code.

---

## 4. BaseEncoder Interface

```python
class BaseEncoder(ABC):
    embed_dim: int                          # must be set in __init__
    def encode_image(self, images: list[PIL.Image]) -> torch.Tensor: ...
    def encode_text(self, texts: list[str]) -> torch.Tensor: ...
```

- Return shape: `(N, embed_dim)`, L2-normalised.
- Both methods are `@torch.no_grad()` during eval. During fine-tuning, `finetune_encoder()` wraps the model in train mode — do not add gradient-blocking logic inside the encoder class.
- Use `build_encoder(ModelConfig) -> BaseEncoder` from `src/outfitmatch/encoders/factory.py` — never instantiate encoder classes directly outside tests.

---

## 5. Dataset Schema Contracts

### RetrievalDataset (DeepFashion / Fashion200K)

`__getitem__` returns:
```python
{"image": PIL.Image, "text": str, "category": str, "item_ID": str}
```

### PolyvoreCompatDataset

`__getitem__` returns:
```python
{"example_id": str, "items": list[str], "label": int}  # label ∈ {0, 1}
```

### PolyvoreFITBDataset

`__getitem__` returns:
```python
{"question": list[str], "answers": list[str], "label": int}  # label = correct answer index
```

---

## 6. Experiment Cycle Design

Each Scrum sprint runs a **grid over exactly one axis**; other axes are fixed:

| Axis | What varies | Fixed values |
|---|---|---|
| Model | encoder kind/checkpoint | dataset=deepfashion-inshop, max_rows=5000 |
| Dataset type | hf_id + config | model=fashionSigLIP-ZS, max_rows=10000 |
| Rows (scaling) | max_rows ∈ {5K, 25K, 100K, null} | model=fashionSigLIP-FT, dataset=fashion200k |
| Conditioning | composer.use_body / use_occ | model=fashionSigLIP-ZS, dataset=polyvore-nondisjoint |

Run a cycle: `om-exp sweep configs/<axis-dir>/ --out-csv docs/experiments/ablation_<axis>.csv`

All cycle results accumulate in `docs/experiments/`. The `name` field in each config is the row key in the CSV and the W&B run name. Use descriptive names like `encoder-fashionsiglip-zs` so W&B charts are self-documenting.

---

## 7. Key Model Choices (research-backed)

| Component | Selected model | Rationale |
|---|---|---|
| Catalog encoder | `Marqo/marqo-fashionSigLIP` (203M, Apache-2.0) | SOTA fashion retrieval on 7 datasets, sigmoid loss matches fine-tune plan |
| Encoder baseline | `openai/clip-vit-base-patch32` | The floor all experiments beat |
| Encoder ablation | `patrickjohncyh/fashion-clip`, `Marqo/marqo-fashionCLIP` | Domain-CLIP variants |
| Body pose | `ultralytics` YOLOv8n-pose / YOLO11n-pose | Only Python-3.13-safe pose option (mediapipe broken) |
| Outfit composer | OutfitTransformer (Sarkar 2022, arXiv:2204.04812) | Reference architecture for Polyvore FITB |
| Outfit dataset | `owj0421/polyvore-outfits` | Ships disjoint/nondisjoint × compat/FITB configs — the dataset experiment axis |

---

## 8. Python 3.13 Constraints (hard rules)

| NEVER use | Use instead |
|---|---|
| `mediapipe` | `ultralytics` (YOLOv8-pose) |
| `faiss-cpu` via pip | `qdrant-client` + Docker, or `usearch` |
| `black`, `flake8`, `isort` | `ruff` (covers all three) |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |

---

## 9. Grading Targets (DoD for ML results)

| Metric | Target | Measured by |
|---|---|---|
| Recall@5 (retrieval) | CLIP-ZS baseline + 5pp | `evaluate_retrieval()` |
| FITB accuracy | ≥ 55% | `fitb_accuracy()` |
| Compatibility AUC | ≥ 0.85 | `compatibility_auc()` |
| Body-cond. Precision@5 | + 10pp vs non-conditional | composer ablation cycle |
| E2E latency | < 3s on CPU | `pipeline.recommend_outfit()` timed |
| LLM-as-judge (Gemini) | Mean ≥ 3.5 / 5 | Sprint 8 |

---

## 10. Definition of Done (XP rule)

A feature is DONE when:
1. PR merged to `dev` with ≥ 1 peer review.
2. `pytest` coverage ≥ 70% for all touched modules, CI green.
3. Docstring present on public functions + entry in `docs/feature.md`.
4. Reproducible: `uv sync && make demo` runs from scratch.
