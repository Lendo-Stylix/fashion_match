# Data Pipeline — OutfitMatch

> **Branch:** Model  
> **Updated:** 2026-05-20  
> **Tham chiếu:** `docs/datasets/CATALOG_ENCODER.md`, `docs/ARCHITECTURE.md`

---

## Tổng quan

Pipeline dữ liệu gồm **7 giai đoạn** từ raw sources → training-ready tensors. Mỗi giai đoạn có đầu vào, xử lý, đầu ra và dependency rõ ràng.

```
[External Sources]
  HuggingFace (DeepFashion, Fashion200K)
  Polyvore dataset
  Custom catalog (thủ công)
         │
         ▼ Stage 1
  Catalog Ingest & Validate
         │
         ▼ Stage 2
  Encoder Fine-tuning Data Prep
         │
         ▼ Stage 3
  Embed + Index (Qdrant)
         │
         ▼ Stage 4
  Outfit Compatibility Data Prep
         │
         ▼ Stage 5
  Occasion Labeling (Gemini)
         │
         ▼ Stage 6
  Preference Triplet Generation
         │
         ▼ Stage 7
  Train/Val/Test Splits
```

---

## Stage 1 — Catalog Ingest & Validate

**Mục đích:** Thu thập, chuẩn hóa và validate toàn bộ catalog items từ nhiều nguồn.

### Input Sources

| Nguồn | Dataset | Rows | Size | Chất lượng |
|---|---|---:|---:|---|
| HuggingFace | `Marqo/deepfashion-inshop` | 52.6K | 216 MB | Cao — studio white bg |
| HuggingFace | `Marqo/deepfashion-multimodal` | 42.5K | 153 MB | Cao — có caption |
| HuggingFace | `Marqo/fashion200k` | 201.6K | 3.5 GB | Trung bình — web-scraped |
| Custom | Manual collect | varies | — | Tùy thuộc vào thu thập |

### Process

```python
# Download từ HuggingFace
from datasets import load_dataset
ds = load_dataset("Marqo/deepfashion-inshop", split="train")

# Map sang catalog schema
{
  "item_ID":    row["id"],
  "image_path": save_to_images(row["image"]),   # save PIL → jpg
  "text":       row["title"],                   # caption
  "category1":  map_to_taxonomy(row["category_label"]),
  "category2":  row["category_label"],
  "color":      extract_color(row["title"]),    # optional
  "source":     "deepfashion2",
  "split":      assign_split(row["id"])         # 80/10/10
}
```

### Output

```
data/raw/catalog/
├── images/
│   ├── item_00001.jpg
│   └── ...
└── catalog_metadata.parquet
```

**Schema catalog_metadata.parquet:**

| Column | Type | Required | Ví dụ |
|---|---|---|---|
| `item_ID` | string | ✅ | `item_00001` |
| `image_path` | string | ✅ | `item_00001.jpg` |
| `text` | string (10–200 chars) | ✅ | `"White cotton slim-fit shirt"` |
| `category1` | enum (7 values) | ✅ | `tops` |
| `category2` | string | ✅ | `shirts` |
| `category3` | string | ❌ | `button_down_shirt` |
| `color` | string | ❌ | `white` |
| `source` | string | ✅ | `deepfashion2` |
| `split` | enum | ✅ | `train` |

**Valid category1 values:** `tops · bottoms · dresses · outerwear · shoes · bags · accessories`

### Validate

```bash
uv run python scripts/validate_custom_data.py --phase 1B
```

Script kiểm tra:
- Tất cả `image_path` tồn tại
- `category1` trong 7 values hợp lệ
- `text` length 10–200 chars
- Không có `item_ID` duplicate
- Distribution report theo category

### Target Distribution (50K total)

| category1 | Min % | Min rows |
|---|---|---|
| tops | ≥ 20% | 10,000 |
| bottoms | ≥ 15% | 7,500 |
| dresses | ≥ 15% | 7,500 |
| outerwear | ≥ 10% | 5,000 |
| shoes | ≥ 15% | 7,500 |
| bags | ≥ 10% | 5,000 |
| accessories | ≥ 5% | 2,500 |

---

## Stage 2 — Encoder Fine-tuning Data Prep

**Mục đích:** Tạo anchor/positive pairs cho SigLIP contrastive training.  
**Dependency:** Stage 1 hoàn thành.

### Process

```
catalog_metadata.parquet [train split]
         │
         ▼
Tạo cặp (image, text) cho mỗi item
  anchor = image embedding
  positive = text embedding (same item)
  negative = in-batch random negatives (không cần tạo trước)
         │
         ▼
Augmentation (train only):
  RandomHorizontalFlip(p=0.5)
  ColorJitter(brightness=0.2, contrast=0.2)
  RandomCrop(scale=(0.85, 1.0))
         │
         ▼
Resize → 224×224, normalize ImageNet mean/std
```

### Output

```
data/processed/encoder_ft/
├── train.parquet    # item_ID, image_path, text (train split)
├── val.parquet
└── test.parquet
```

### Code
- `src/outfitmatch/data/retrieval.py` — `RetrievalDataset`
- DataLoader collate: batch = `{images: Tensor(B,3,224,224), texts: list[str], item_IDs: list[str]}`

---

## Stage 3 — Embed + Index

**Mục đích:** Embed toàn bộ catalog và nạp vào Qdrant.  
**Dependency:** Stage 1 hoàn thành + encoder checkpoint từ training Component 1.

### Process

```
Fine-tuned encoder (frozen, eval mode)
         │
         ▼
Batch encode (batch_size=256, GPU if available):
  images → 768-dim vector
  text   → 768-dim vector
  combined = mean(image_vec, text_vec) [hoặc image_vec only cho retrieval]
         │
         ▼
L2 normalize → upload to Qdrant
  collection: "catalog"
  size: 768, distance: Cosine
  payload: {item_ID, category1, category2, color, body_shapes}
```

### Output
- Qdrant collection `catalog`: ~50K vectors × 768-dim
- `body_shapes` collection: 512-dim vectors cho body shape filtering

### Code
- `scripts/build_catalog_index.py`
- Qdrant Docker: `make qdrant-up` → `:6333`

---

## Stage 4 — Outfit Compatibility Data Prep

**Mục đích:** Tạo positive/negative outfit sets cho OutfitTransformer training.  
**Dependency:** Stage 1 hoàn thành.

### Input Source

**Polyvore dataset** (primary):
- `polyvore_outfits/` — JSON files với outfit sets
- Positive: outfits từ human stylists
- Negative: random item substitution

### Process

```
Polyvore raw JSON
         │
         ▼
PolyvoreCompatDataset:
  - label 1 = compatible (positive outfit)
  - label 0 = incompatible (negative outfit)
  - Mỗi outfit = list of item_IDs (đã có trong catalog)
         │
         ▼
PolyvoreFITBDataset (Fill-in-the-Blank):
  - Một item bị che (blank)
  - 4 candidates (1 correct + 3 random)
  - label = index của correct candidate
```

### Output

```
data/processed/outfit_pairs/
├── compatibility_train.jsonl
├── compatibility_val.jsonl
├── compatibility_test.jsonl
├── fitb_train.jsonl
├── fitb_val.jsonl
└── fitb_test.jsonl
```

### Code
- `src/outfitmatch/data/polyvore.py` — `PolyvoreCompatDataset`, `PolyvoreFITBDataset`

---

## Stage 5 — Occasion Labeling

**Mục đích:** Gán `occasion` tag cho từng outfit/item dùng Gemini API.  
**Dependency:** Stage 4 hoàn thành.

### Process

```
Outfit item list (item_ID, category, text description)
         │
         ▼
Gemini API prompt:
  "Given these clothing items: [list]
   What occasion is this outfit most appropriate for?
   Choose from: casual, business, formal, sport, party, date"
         │
         ▼
Response cache (diskcache):
  key = SHA256(EXTRACTOR_VERSION + outfit_description)
  → avoid re-calling for same outfit
         │
         ▼
occasion: str  →  append to outfit metadata
```

### Output
- `data/processed/outfit_pairs/*.jsonl` — updated với `occasion` field
- `data/raw/occasion_cache/` — diskcache cho API responses

### Code
- `src/outfitmatch/preference/structuring.py` — cùng `PromptStructurer` (dual use)
- `configs/preference/instructions.yaml` — system prompts

### Cost estimate
- ~50K outfits × 1 API call = ~50K calls
- Gemini Flash: ~$0.0001/call → ~$5 total
- Cache saves ~95% calls nếu re-run

---

## Stage 6 — Preference Triplet Generation

**Mục đích:** Tạo `triplets.jsonl` cho preference post-training.  
**Dependency:** Stage 4 + Stage 5 hoàn thành.

### Process

```
Outfit pairs (pos/neg) + occasion labels
         │
         ▼
scripts/generate_preference_triplets.py
  --n-pairs 5000
  --flip-ratio 0.3
  --limit 100
         │
         ▼
Mỗi triplet:
  {
    "instruction": "I want a casual minimalist look",
    "body_shape": "pear",
    "pos_items": ["item_001", "item_002", "item_003"],
    "neg_items": ["item_010", "item_011", "item_012"]
  }
         │
         ▼
Flip pairs (30% minimum):
  instruction_A: "I prefer bright colors"  → pos > neg
  instruction_B: "I prefer neutral colors" → neg > pos (label flipped)
```

### Output

```
data/processed/preference_triplets/
└── triplets.jsonl
```

### Invariants

- **flip-ratio ≥ 0.30**: Tối thiểu 30% cặp phải có instruction đối nghịch với label flipped
- **EXTRACTOR_VERSION consistency**: Version dùng để generate phải giống version trong inference (`EXTRACTOR_VERSION = "v1"`)
- Nếu bump version → phải regenerate toàn bộ `triplets.jsonl`

### Code
- `scripts/generate_preference_triplets.py`
- `src/outfitmatch/data/preference.py` — `PreferenceTripletDataset`

---

## Stage 7 — Train/Val/Test Splits

**Mục đích:** Đảm bảo không có data leakage giữa các splits.

### Split Strategy

| Dataset | Train | Val | Test |
|---|---|---|---|
| Encoder FT | 80% | 10% | 10% |
| Outfit compat | Polyvore-train | Polyvore-val | Polyvore-test |
| FITB | Polyvore-train | Polyvore-val | Polyvore-test |
| Preference triplets | 80% | 10% | 10% |

### Anti-leakage Rules

1. **Item-level split**: Nếu item_ID xuất hiện trong train, không được xuất hiện trong test
2. **Outfit-level split**: Một outfit set chỉ ở 1 split (không chia item giữa splits)
3. **Preference triplets**: instruction không được copy giữa train và test splits

### DVC Versioning

```bash
# Track data files với DVC
dvc add data/raw/catalog/
dvc add data/processed/

# Push lên Google Drive remote
dvc push
```

> **QUAN TRỌNG:** KHÔNG commit ảnh/data files trực tiếp vào git — dùng DVC cho tất cả files trong `data/`

---

## Dependency Graph đầy đủ

```
HuggingFace Sources ──► Stage 1 (Catalog Ingest)
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              Stage 2        Stage 4     Stage 3
           (Encoder FT    (Outfit Data  (Embed+Index)
            Data Prep)      Prep)           ↑
                │               │    [requires encoder checkpoint]
                ▼               ▼
         [Training:          Stage 5
          Component 1]    (Occasion Labeling)
                                │
                                ▼
                          Stage 6
                       (Triplet Gen)
                                │
                                ▼
                          Stage 7 (Splits)
                                │
                    ┌───────────┼
                    ▼           ▼
             [Training:    [Training:
              Comp 3]       Comp 4]
```

---

## Công cụ & Scripts

| Script | Mục đích |
|---|---|
| `scripts/validate_custom_data.py --phase 1B` | Validate catalog schema |
| `scripts/build_catalog_index.py` | Embed + upload to Qdrant |
| `scripts/generate_preference_triplets.py` | Tạo triplets.jsonl |
| `uv run python -m outfitmatch.data.retrieval` | Test RetrievalDataset |
| `make qdrant-up` | Start Qdrant Docker `:6333` |

---

## Thiếu dữ liệu hiện tại (cần thu thập)

| Dữ liệu | Trạng thái | Ghi chú |
|---|---|---|
| Catalog images (50K) | ❌ Chưa download | Dùng `load_dataset("Marqo/deepfashion-inshop")` |
| Polyvore outfits | ❌ Chưa có | Download từ nguồn gốc hoặc HuggingFace mirror |
| Preference triplets | ❌ Chưa generate | Cần chạy `scripts/generate_preference_triplets.py` |
| Body shape annotations | ⚠️ Rule-based | Không cần labeled data — dùng YOLO-pose + rules |
| Occasion labels | ⚠️ Cần Gemini key | `GOOGLE_API_KEY` trong `.env` |
