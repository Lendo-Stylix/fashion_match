# Phase 1C — Outfit Composer Dataset

> **Sprint:** S5, S6, S7 (compatibility training + occasion conditioning)  
> **Mục đích:** Train OutfitTransformer: outfit compatibility (AUC) + FITB accuracy + occasion-conditioned retrieval

---

## 1. Label Schema — Outfit Sets

### File: `data/raw/outfits/outfits.jsonl`

Mỗi dòng là một JSON object:

```json
{
  "outfit_id": "outfit_00001",
  "items": [
    {"item_ID": "item_00123", "role": "top"},
    {"item_ID": "item_00456", "role": "bottom"},
    {"item_ID": "item_00789", "role": "shoes"}
  ],
  "compatible": true,
  "occasion": "casual",
  "source": "polyvore_nondisjoint",
  "split": "train"
}
```

### Schema chi tiết

| Field | Type | Valid values | Required | Ghi chú |
|---|---|---|---|---|
| `outfit_id` | string | unique | ✅ | `outfit_00001` |
| `items` | list[object] | 2–8 items | ✅ | Mỗi object có `item_ID` + `role` |
| `items[].item_ID` | string | phải tồn tại trong catalog | ✅ | Cross-ref với catalog_metadata |
| `items[].role` | enum | `top · bottom · shoes · bag · outerwear · accessory` | ✅ | Slot trong outfit |
| `compatible` | bool | `true · false` | ✅ | Ground-truth compatibility |
| `occasion` | enum | xem bảng bên dưới | ❌ | Nếu có từ Gemini labeling |
| `source` | string | tên dataset | ✅ | |
| `split` | enum | `train · val · test` | ✅ | |

### Valid `occasion` values

```
casual · formal · business_casual · sport · party · beach · date_night · outdoor
```

---

## 2. Occasion Labeling — Gemini Workflow

Occasion labels được sinh tự động bằng Gemini Vision API và cache vào SQLite.

### Cache Schema: `data/raw/occasion_cache/occasion_cache.db`

```sql
CREATE TABLE occasion_labels (
    outfit_id     TEXT PRIMARY KEY,
    occasion      TEXT NOT NULL,
    confidence    REAL,
    model         TEXT DEFAULT 'gemini-2.0-flash',
    created_at    TEXT DEFAULT (datetime('now'))
);
```

### Prompt template

```python
OCCASION_PROMPT = """
Look at this outfit and classify it into exactly ONE occasion:
casual, formal, business_casual, sport, party, beach, date_night, outdoor

Outfit items:
{item_descriptions}

Reply with only the occasion word, nothing else.
"""
```

### Chạy labeling

```bash
uv run python scripts/label_occasions.py \
    --outfits data/raw/outfits/outfits.jsonl \
    --catalog data/raw/catalog/catalog_metadata.parquet \
    --cache data/raw/occasion_cache/occasion_cache.db \
    --limit 1000
```

---

## 3. Polyvore Dataset — Sử dụng trực tiếp

Dataset `owj0421/polyvore-outfits` đã có pre-split configs:

| HF Config | Task | Splits |
|---|---|---|
| `nondisjoint_compatibility` | Compatibility (AUC) | train/val/test |
| `nondisjoint_fill_in_the_blank` | FITB accuracy | train/val/test |
| `disjoint_compatibility` | Harder AUC | train/val/test |
| `disjoint_fill_in_the_blank` | Harder FITB | train/val/test |

**Load trực tiếp:**
```python
from datasets import load_dataset

compat_ds = load_dataset("owj0421/polyvore-outfits",
                          "nondisjoint_compatibility",
                          split="train")
fitb_ds = load_dataset("owj0421/polyvore-outfits",
                        "nondisjoint_fill_in_the_blank",
                        split="train")
```

**Mapping → outfits.jsonl format:**

| Polyvore field | outfits.jsonl field |
|---|---|
| `set_id` | `outfit_id` |
| `items` (list) | `items` (add role = `f"slot_{i}"`) |
| `question` / `answers` (FITB) | handled by `PolyvoreFITBDataset` |
| `label` (1/0) | `compatible` (bool) |

---

## 4. Cấu trúc thư mục

```
data/custom/outfits/
├── outfits.jsonl          # Outfit sets tự thu thập
└── occasion_labels.csv    # Optional manual occasion labels
```

---

## 5. Thu thập outfit thủ công

Cách 1: Screenshot outfit từ Pinterest / Instagram → tách items
Cách 2: Kết hợp items từ catalog đã có, đánh label compatible/not

**Form thu thập nhanh:**
```csv
outfit_id,item_ids,compatible,occasion,source
outfit_c001,"item_00123;item_00456;item_00789",true,casual,custom_nhom
outfit_c002,"item_00123;item_00999",false,,custom_nhom
```

Script `merge_custom_data.py` sẽ tự convert CSV → JSONL format.

---

## 6. Target distribution

### Compatibility balance

| Label | Target % |
|---|---|
| compatible=true | 50% |
| compatible=false | 50% |

Polyvore đã balanced — custom data cần bổ sung negative samples bằng random pairing.

### Occasion distribution (nếu có labels)

| Occasion | Target % |
|---|---|
| casual | ≥ 25% |
| formal | ≥ 10% |
| business_casual | ≥ 15% |
| sport | ≥ 10% |
| party | ≥ 10% |
| beach, date_night, outdoor | ≥ 5% each |

---

## 7. Validation script

```bash
uv run python scripts/validate_custom_data.py --phase 1C
```

Script kiểm tra:
- `outfit_id` unique
- Mỗi `item_ID` trong outfit tồn tại trong catalog
- `compatible` là bool
- `occasion` (nếu có) trong valid set
- Items per outfit: 2–8
- In compatibility ratio và occasion distribution

---

## 8. Metric targets

| Metric | Threshold (pass) | Dataset |
|---|---|---|
| AUC (compatibility) | ≥ 0.85 | Polyvore nondisjoint |
| FITB accuracy | ≥ 0.60 | Polyvore nondisjoint |
| AUC (disjoint) | ≥ 0.80 | Polyvore disjoint |
