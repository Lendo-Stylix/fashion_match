# Training Pipeline — OutfitMatch

> **Branch:** Model  
> **Updated:** 2026-05-20  
> **Tham chiếu:** `docs/ARCHITECTURE.md`, `docs/superpowers/plans/2026-05-18-outfitmatch-experiment-cycles.md`

---

## Tổng quan

Pipeline training gồm **4 thành phần học** chạy theo thứ tự phụ thuộc — không song song vì đầu ra của bước trước là đầu vào của bước sau.

```
[Catalog Data]          [Outfit Pair Data]      [Triplet Data]
      │                        │                      │
      ▼                        ▼                      ▼
Component 1          Component 2+3             Component 4
Encoder FT     →    Index Build + Composer   →   Pref Post-train
                         Base Train
      │
      ▼ (optional, parallel với Component 1-4)
Component 5
Body Classifier Train
```

---

## Component 1 — Catalog Encoder Fine-tuning

**Mục đích:** Đưa `Marqo/marqo-fashionSigLIP` từ general fashion domain → specific catalog domain.

### Input
- `data/processed/encoder_ft/` — anchor/positive pairs (item image + caption)
- Nguồn: DeepFashion2 in-shop, Fashion200K, DeepFashion-Multimodal

### Process

```
Frozen CLIP backbone (khởi tạo từ fashionSigLIP)
         │
         ▼
SigLIP contrastive loss:
  L = -mean(log σ(s_ii)) - mean(log σ(-s_ij))  [i≠j]
  s_ij = <image_i, text_j> / τ
  labels = 2*eye(N) - 1                          ← sigmoid target
         │
         ▼
Unfreeze top K transformer layers (progressive unfreezing)
         │
         ▼
Evaluate Recall@1/5/10 trên val set
```

### Config axes (ablation)
| Axis | Options |
|---|---|
| encoder | `fashionsiglip_zs`, `marqo_fashionclip_zs`, `fashionclip_zs`, `clip_zs` |
| dataset | `deepfashion_inshop`, `fashion200k`, `deepfashion_multimodal` |
| rows | `ft_5k`, `ft_25k`, `ft_100k` |

### Output
- Fine-tuned encoder checkpoint: `models/encoder/fashionsiglip_ft_v{N}.pt`
- Metric gate: **Recall@5 ≥ CLIP zero-shot + 5%** (bắt buộc trước khi sang Component 2)

### Code
- `src/outfitmatch/train/contrastive.py` — `finetune_encoder()`
- `src/outfitmatch/metrics/retrieval.py` — `recall_at_k()`
- `src/outfitmatch/eval/retrieval.py` — `evaluate_retrieval()`

---

## Component 2 — Embedding Index Build

**Mục đích:** Embed toàn bộ catalog → Qdrant vector store.  
**Dependency:** Component 1 phải hoàn thành trước.

### Process

```
Fine-tuned encoder (frozen)
         │
         ▼
Batch encode catalog images + text
(data/raw/catalog/catalog_metadata.parquet)
         │
         ▼
768-dim L2-normalized vectors
         │
         ▼
Upsert vào Qdrant collection `catalog`:
  - size=768, distance=Cosine
  - payload: {item_ID, category1, category2, color, body_shapes, ...}
```

### Output
- Qdrant collection `catalog` fully populated
- Index stats logged to W&B

### Code
- `scripts/build_catalog_index.py` (planned)
- Qdrant Docker `:6333`

---

## Component 3 — OutfitTransformer Base Training

**Mục đích:** Train OutfitTransformer để học compatibility scoring.  
**Dependency:** Component 2 phải hoàn thành (cần item embeddings từ encoder).

### Input
- `data/processed/outfit_pairs/` — Polyvore dataset: positive/negative outfit sets
- Các outfit set gồm N items (đã được embed bằng encoder đã fine-tune)

### Process

```
Frozen encoder (từ Component 1)
         │
         ▼ encode items → item_embeds (B, N, 512)
         │
         ▼
OutfitTransformer forward:
  [CLS] + [item×N] + [BODY]? + [OCC]?
         │
         ▼
Conditional Bradley-Terry pairwise loss:
  L = -log σ(score_pos - score_neg)
         │
         ▼
Evaluate FITB accuracy + Compatibility AUC
```

### Config axes (ablation)
| Axis | Options |
|---|---|
| outfit split | `disjoint`, `nondisjoint` |
| conditioning | `cond_none`, `cond_body`, `cond_body_occ` |
| embed_dim | 512 (fixed) |
| n_heads / n_layers | 8 / 4 (fixed per paper) |

### Output
- Composer checkpoint: `models/composer/composer_base_v{N}.pt`
- Metric gates:
  - **FITB accuracy ≥ 55%**
  - **Compatibility AUC ≥ 0.85**
  - **Body-conditional Precision@5 ≥ +10% vs non-conditional baseline**

### Code
- `src/outfitmatch/train/composer.py` — `OutfitTransformer`
- `src/outfitmatch/train/preference.py` — `pairwise_bt_loss()`
- `src/outfitmatch/data/polyvore.py` — `PolyvoreCompatDataset`, `PolyvoreFITBDataset`

---

## Component 4 — Preference Post-training

**Mục đích:** Dạy OutfitTransformer phản hồi theo preference tokens `[PREF_style]`, `[PREF_color]`, `[PREF_fit]`.  
**Dependency:** Component 3 phải hoàn thành (khởi tạo từ composer base).

### Input
- `data/processed/preference_triplets/triplets.jsonl`
- Format: `{instruction, body_shape, pos_items: [item_ID×N], neg_items: [item_ID×N]}`
- Tạo bằng: `scripts/generate_preference_triplets.py`

### Process

```
Frozen encoder (từ Component 1)
         │
         ▼
PromptStructurer.structure(instruction, body_shape)
→ StructuredPreference {hard, soft}
→ pref_dict: {group: encoded_text_vector}
         │
         ▼
OutfitTransformer(pref_groups=("style","color","fit"))
  forward(pos_items, mask, body, occ, pref=pref_dict) → s_pos
  forward(neg_items, mask, body, occ, pref=pref_dict) → s_neg
         │
         ▼
pairwise_bt_loss(s_pos, s_neg) = -log σ(s_pos - s_neg)
         │
         ▼
Eval: preference_pairwise_accuracy + instruction_flip_consistency
```

### Config axes
| Axis | Options |
|---|---|
| pref scope | `pref_off`, `pref_style_only`, `pref_all_groups` |
| flip ratio | 0.3 (tối thiểu — kiểm tra flip consistency) |

### Output
- Composer checkpoint: `models/composer/composer_pref_v{N}.pt`
- Metric gates:
  - **preference_pairwise_accuracy ≥ 0.65**
  - **instruction_flip_consistency ≥ 0.30** (≥30% pairs phải flip khi instruction đối nghịch)

### Code
- `src/outfitmatch/preference/structuring.py` — `PromptStructurer`
- `src/outfitmatch/train/preference_trainer.py` — `train_preference()`
- `src/outfitmatch/data/preference.py` — `PreferenceTripletDataset`
- `src/outfitmatch/metrics/outfit.py` — `preference_pairwise_accuracy()`, `instruction_flip_consistency()`

---

## Component 5 — Body Shape Classifier (độc lập)

**Mục đích:** Validate rule-based body shape classifier — không cần train DL, chỉ cần unit test đủ coverage.  
**Dependency:** Độc lập — có thể chạy song song với Component 1-4.

### Process

```
YOLO-pose keypoints (COCO-17 format)
         │
         ▼
keypoints_to_measures():
  shoulder_width = dist(LShoulder, RShoulder)
  hip_width      = dist(LHip, RHip)
  waist_width    = (shoulder_width + hip_width) / 2   [proxy]
         │
         ▼
Rule classifier:
  hip > shoulder*1.05  → pear
  shoulder > hip*1.1   → inverted_triangle
  waist < hip*0.75     → hourglass
  all within 5%        → rectangle
  else                 → apple
         │
         ▼
body_shape: str  →  body_vector (512-dim)  →  Qdrant `body_shapes`
```

### Code
- `src/outfitmatch/body/pose.py` — `PoseExtractor`, `keypoints_to_measures()`
- `src/outfitmatch/body/shape.py` — `classify_shape()`

---

## 3 Invariants bắt buộc

| # | Invariant | Mô tả |
|---|---|---|
| INV-1 | **Encoder frozen during composer training** | Encoder KHÔNG được update trong Component 3 và 4. Gradient phải bị detach hoặc `requires_grad=False`. Nếu vi phạm → feature collapse. |
| INV-2 | **Same structurer version in train and inference** | `EXTRACTOR_VERSION` trong `structuring.py` phải giống nhau ở cả train (generate triplets) và inference (online structuring). Khác version → train/inference skew. |
| INV-3 | **Flip invariant ≥ 30%** | Trong `triplets.jsonl`, tối thiểu 30% cặp phải có instruction đối nghịch với label flipped. Đảm bảo composer học phân biệt sở thích thực sự, không chỉ memorize. |

---

## Thứ tự dependency

```
[Catalog Data] ──► Component 1 (Encoder FT)
                          │
                          ▼
                   Component 2 (Index Build)
                          │
                          ▼
               Component 3 (Composer Base)
                          │
                    [Triplet Data] ──► Component 4 (Pref Post-train)

[Pose Data] ──► Component 5 (Body Classifier)   ← independent
```

---

## Experiment Tracking

- W&B project: `outfitmatch-grading`
- Mỗi run log: loss curves, recall@k, FITB acc, compat AUC, pref acc, flip consistency
- Config: `configs/{encoder,dataset,rows,composer,preference}/*.yaml`
- CLI: `uv run om-exp run configs/encoder/fashionsiglip_zs.yaml`

---

## Required Ablations (grading)

| Ablation | Components |
|---|---|
| Encoder variants | Component 1: clip_zs vs fashionsiglip_zs vs marqo_fashionclip_zs |
| Body conditioning on/off | Component 3: cond_none vs cond_body vs cond_body_occ |
| Occasion conditioning on/off | Component 3: cond_none vs cond_body_occ |
| Greedy vs beam decoding | Component 3+4: outfit construction strategy |
