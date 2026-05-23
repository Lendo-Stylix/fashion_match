# OutfitMatch — System Architecture

> **Agents: read this file before writing any code.** It defines module boundaries, data flow, and the invariants every module must respect.

---

## Part I — v3.1-lite: Active Development Target

This is the system described in `Kien_truc_v3.1.md`. All new feature work follows this architecture.

---

## 1. System Overview (v3.1-lite)

```
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 1: OUTFIT KNOWLEDGE BASE (Offline — build once)        │
│  OutfitTransformer-labse (frozen) + FITB/Beam → 5–20K outfit │
│  Gemini Flash metadata tagging → occasion/style/body enums   │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 2: CONVERSATIONAL AI STYLIST (Qwen3-VL-8B + LoRA)      │
│  Parse intent · ask follow-up · call search_outfits tool      │
│  Validate outfit_id · generate Vietnamese explanation         │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 3: RETRIEVAL ENGINE (Qdrant — filter first)            │
│  Filter by occasion/style/body/price/has_vn_store            │
│  Sort by compatibility_score → Top 30–50 outfits             │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 4: PERSONALIZATION (Quiz Re-rank — MVP)                │
│  5-question quiz → PreferenceProfile → additive re-rank      │
│  → Top 3–5 outfits with Vietnamese explanation               │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Module Responsibilities (v3.1-lite)

| Module | Responsibility | Must NOT do |
|---|---|---|
| `src/outfitmatch/vocab.py` | Single source of truth for all enum values | Define UI labels (use `*_LABELS_VI` for that) |
| `src/outfitmatch/kb/schema.py` | `ItemRecord` + `OutfitRecord` data types | Business logic, I/O |
| `src/outfitmatch/kb/embedding.py` | Extract item embeddings via OT-labse | Filter or tag outfits |
| `src/outfitmatch/kb/generation.py` | FITB+Beam (70%) + random+score (30%) outfit generation | Score or tag outfits |
| `src/outfitmatch/kb/scoring.py` | Re-score all outfits with OT compatibility score | Generate or tag outfits |
| `src/outfitmatch/kb/tagging.py` | Gemini Flash LLM metadata tagging (occasion/style/…) | Score outfits, call encoders |
| `src/outfitmatch/stylist/tools.py` | `search_outfits` tool definition (enum-typed params from vocab) | Model loading, inference |
| `src/outfitmatch/stylist/validation.py` | Extract + validate outfit_id refs in LLM responses | Business logic |
| `src/outfitmatch/stylist/model.py` | Qwen3-VL-8B + LoRA loading + inference | Dataset loading |
| `src/outfitmatch/stylist/data.py` | Conversation dataset for LoRA fine-tuning | Inference |
| `src/outfitmatch/quiz/schema.py` | `QuizAnswers` + `PreferenceProfile` + `quiz_to_profile` | Re-ranking logic |
| `src/outfitmatch/quiz/rerank.py` | Preference-based outfit re-rank | Quiz UI, dataset loading |
| `src/outfitmatch/pipeline.py` | Wire Tầng 2–4 into E2E `recommend_outfit` orchestrator | Training logic |

---

## 3. Controlled Vocabulary Invariant

**File:** `src/outfitmatch/vocab.py` — the single source of truth for all enum values.

All three of these MUST use the same values from `vocab.py`:
1. Gemini Flash LLM-tagging prompt (building the KB)
2. `search_outfits` tool parameters for Qwen3-VL
3. Qdrant payload index field values

**Rule:** Internal values are always English `snake_case`. Vietnamese labels appear ONLY in `*_LABELS_VI` dicts and UI `*_vi` schema fields.

**Never rename** an existing enum value — it would invalidate the entire KB. Add new values; never change old ones.

---

## 4. Knowledge Base Schema

One outfit (`OutfitRecord`) in the KB:

```jsonc
{
  "outfit_id": "OF_00001",
  "schema_version": "3.1",
  "items": [
    {
      "item_id": "item_custom_00001",
      "category": "top",                       // ITEM_CATEGORY enum
      "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
      "item_embedding": [/* OT-labse dim — verify from checkpoint */],
      "store": {
        "store_id": "canifa_vn",
        "store_name": "Canifa",
        "product_url": "https://canifa.com/...",
        "price_vnd": 299000,
        "in_stock": true
      }
    }
  ],
  "outfit_embedding": [/* same dim as item_embedding */],
  "compatibility_score": 0.0,              // ALWAYS re-scored after generation
  "occasion": ["office", "cafe_hangout"],  // OCCASION enum (primary conditioning)
  "style": ["minimalist", "korean"],       // STYLE enum (primary conditioning)
  "body_shapes_fit": ["pear", "hourglass"],
  "season": ["transitional"],
  "color_palette": ["beige", "navy"],
  "price_total_vnd": 850000,
  "price_tier": "mid",
  "has_vn_store": true,
  "stylist_explanation_vi": "...",
  "gen_method": "fitb_beam"
}
```

---

## 5. Retrieval Design (Tầng 3)

v3.1-lite does NOT use a query vector for Qdrant search. Instead:

1. Qwen3-VL calls `search_outfits(occasion, style, body_shape, price_max, exclude_colors)`.
2. Qdrant **filters** by metadata (occasion, style, body_shapes_fit, price_tier, `has_vn_store=True`, exclude_colors).
3. Results are **sorted by `compatibility_score`** (precomputed, descending) + diversity penalty.
4. Top 30–50 are returned to Tầng 4.

This avoids the undefined "user query → outfit embedding space" mapping that was a gap in v3.0.

**Qdrant collection:** `outfits`. Payload indexes on: `occasion`, `style`, `body_shapes_fit`, `price_tier`, `season`, `has_vn_store`.

```python
# Collection config (verify OUTFIT_EMBED_DIM from checkpoint before creating)
qdrant.create_collection(
    collection_name="outfits",
    vectors_config=models.VectorParams(
        size=OUTFIT_EMBED_DIM,  # verify from OT-labse checkpoint — do NOT hardcode
        distance=models.Distance.COSINE,
    ),
)
for field in ["occasion", "style", "body_shapes_fit", "price_tier", "season", "has_vn_store"]:
    qdrant.create_payload_index("outfits", field, models.PayloadSchemaType.KEYWORD)
```

---

## 6. Hallucination Prevention (Tầng 2)

After Qwen3-VL generates a response, extract all `OF_NNNNN` references and verify each exists in the KB:

```python
from outfitmatch.stylist.validation import validate_response

ok, invalid_ids = validate_response(response_text, valid_outfit_id_set)
if not ok:
    # do NOT show response to user — ask Qwen to retry
    pass
```

This is enforced in `pipeline.py`'s E2E flow. Never skip this step.

---

## 7. E2E Inference Pipeline (v3.1-lite)

```
Step 1  User provides text + optional selfie + completed onboarding quiz
Step 2  Qwen3-VL parses → {height, weight, skin_tone, occasion, style, missing_info[]}
Step 3  [Enough info?] ──No──▶ Qwen asks follow-up (loop to Step 1)
         │ Yes
Step 4  Qwen calls search_outfits(filters) → Qdrant filter+sort → 30–50 outfits
Step 5  Tầng 4 re-ranks by PreferenceProfile from quiz → Top 3–5
Step 6  Validation layer verifies all outfit_id refs
Step 7  Qwen generates personalised Vietnamese explanation
Step 8  Display: outfit images + store + price + purchase link; record feedback
```

---

## Part II — Grading Experiments: 6-Layer Sub-system

This sub-system is used **exclusively for academic deliverables**: encoder ablations, FITB accuracy, Compatibility AUC, and body-conditioning experiments. It does NOT replace v3.1-lite as the product architecture.

---

## 8. 6-Layer Grading Architecture (encoder/composer experiments)

```
Layer 0 — Preference Structuring (src/preference/)
Layer 1 — Body Understanding (src/body/)
Layer 2 — Catalog Encoder (src/encoders/)  ← encoder ablation axis
Layer 3 — Vector Store / Retrieval (Qdrant "catalog" collection)
Layer 4 — Outfit Composer (src/train/composer.py)  ← FITB / AUC axis
Layer 5 — Item Customization (POST /customize-item)
```

Used by: `src/outfitmatch/runner.py`, `om-exp` CLI, `configs/` YAML files, `docs/EXPERIMENT_GUIDE.md`.

---

## 9. Experiment Config Contract (grading experiments)

Every experiment is a YAML file consumed by `ExperimentConfig` (pydantic):

```yaml
name: string
seed: int
task: retrieval|fitb|compatibility|preference
model:
  kind: hf_clip|open_clip
  checkpoint: string
  pretrained: string?
  finetune: bool
dataset:
  hf_id: string
  config: string?
  split: string
  max_rows: int?
train:
  epochs: int
  batch_size: int
  lr: float
  weight_decay: float
  num_workers: int
composer:
  n_heads: int
  n_layers: int
  use_body: bool
  use_occ: bool
  use_pref: bool
  pref_groups: [str]
wandb_project: string
```

**Invariant:** `max_rows` is the ONLY way to vary dataset size. Never hard-code slice logic in model or trainer code.

---

## 10. BaseEncoder Interface (grading experiments)

```python
class BaseEncoder(ABC):
    embed_dim: int
    def encode_image(self, images: list[PIL.Image]) -> torch.Tensor: ...
    def encode_text(self, texts: list[str]) -> torch.Tensor: ...
```

Return shape: `(N, embed_dim)`, L2-normalised. Use `build_encoder(ModelConfig)` from `src/outfitmatch/encoders/factory.py` — never instantiate encoder classes directly outside tests.

---

## 11. Dataset Schema Contracts (grading experiments)

### RetrievalDataset
```python
{"image": PIL.Image, "text": str, "category": str, "item_ID": str}
```

### PolyvoreCompatDataset
```python
{"example_id": str, "items": list[str], "label": int}  # label ∈ {0, 1}
```

### PolyvoreFITBDataset
```python
{"question": list[str], "answers": list[str], "label": int}
```

### PreferenceTripletDataset
```python
{"instruction": str, "body_shape": str,
 "pos_items": list[str], "neg_items": list[str]}
```

---

## 12. Grading Targets (DoD for ML results)

| Metric | Target | Measured by |
|---|---|---|
| Recall@5 (retrieval) | CLIP-ZS baseline + 5pp | `evaluate_retrieval()` |
| FITB accuracy | ≥ 55% | `fitb_accuracy()` on Polyvore |
| Compatibility AUC | ≥ 0.85 | `compatibility_auc()` on Polyvore |
| Body-cond. Precision@5 | + 10pp vs non-conditional | composer ablation cycle |
| E2E latency | < 5–8s on GPU / cloud API | timed on GPU (CPU target retired with v3.1-lite) |
| LLM-as-judge (Gemini) | Mean ≥ 3.5 / 5 | Sprint 9 Gemini judge eval |

Required ablations: (1) encoder variants, (2) body conditioning on/off, (3) occasion conditioning on/off, (4) greedy vs beam decoding.

---

## 13. Python 3.13 Constraints (hard rules)

| NEVER use | Use instead |
|---|---|
| `mediapipe` | `ultralytics` (YOLOv8-pose) |
| `faiss-cpu` via pip | `qdrant-client` + Docker |
| `black`, `flake8`, `isort` | `ruff` |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |
| `AutoModelForCausalLM` for Qwen3-VL | `Qwen3VLForConditionalGeneration` |
| `evaluation_strategy` in TrainingArguments | `eval_strategy` (new name) |

---

## 14. Definition of Done (XP rule)

A feature is DONE when:
1. PR merged to `dev` with ≥ 1 peer review.
2. `pytest` coverage ≥ 70% for all touched modules, CI green.
3. Docstring present on public functions + entry in `docs/feature.md`.
4. Reproducible: `uv sync && make demo` runs from scratch.
