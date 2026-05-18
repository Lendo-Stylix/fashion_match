# Phase 1B — Catalog Encoder Dataset

> **Sprint:** S4, S5 (encoder training / ablation cycles)  
> **Mục đích:** Train và evaluate catalog encoder (image + text → 768-dim embedding) dùng cho vector retrieval

---

## 1. Label Schema

### File: `data/raw/catalog/catalog_metadata.parquet`

| Column | Type | Valid values | Required | Ví dụ |
|---|---|---|---|---|
| `item_ID` | string | unique | ✅ | `item_00001` |
| `image_path` | string | relative to `data/raw/catalog/images/` | ✅ | `item_00001.jpg` |
| `text` | string | caption/description, 10–200 chars | ✅ | `"White cotton slim-fit shirt with button collar"` |
| `category1` | string | top-level category | ✅ | `tops` |
| `category2` | string | mid-level category | ✅ | `shirts` |
| `category3` | string | fine-grained label | ❌ | `button_down_shirt` |
| `color` | string | dominant color (lowercase) | ❌ | `white` |
| `source` | string | tên dataset / người collect | ✅ | `deepfashion2` |
| `split` | enum | `train` · `val` · `test` | ✅ | `train` |

**Valid `category1` values:**
```
tops · bottoms · dresses · outerwear · shoes · bags · accessories
```

**Valid `category2` examples:**

| category1 | category2 examples |
|---|---|
| tops | shirts · t-shirts · blouses · hoodies · sweaters |
| bottoms | jeans · trousers · skirts · shorts · leggings |
| dresses | midi-dress · maxi-dress · mini-dress · wrap-dress |
| outerwear | jackets · coats · blazers · cardigans |
| shoes | sneakers · heels · boots · sandals · loafers |
| bags | handbags · backpacks · clutches · tote-bags |
| accessories | belts · scarves · hats · jewelry |

**Ví dụ 1 row (CSV representation):**
```csv
item_ID,image_path,text,category1,category2,category3,color,source,split
item_00001,item_00001.jpg,White cotton slim-fit shirt with button collar,tops,shirts,button_down_shirt,white,deepfashion2,train
```

---

## 2. Yêu cầu ảnh

| Tiêu chí | Yêu cầu |
|---|---|
| **Background** | Trắng thuần (preferred) hoặc xám nhạt — không có người model nếu có thể |
| **Góc chụp** | Front view chính; có thể thêm side/back view (nhưng `image_path` luôn là front) |
| **Khoảng cách** | Item chiếm 60–80% diện tích ảnh, không bị cắt |
| **Ánh sáng** | Studio light hoặc daylight đồng đều — không bóng đổ mạnh |
| **Resolution** | Tối thiểu 512×512px |
| **Format** | `.jpg` hoặc `.png` |
| **Chất liệu** | Ảnh flat-lay hoặc trên mannequin (tránh ảnh người mặc nếu muốn tập trung item) |

---

## 3. Hướng dẫn viết `text` caption

Caption cần mô tả:
1. **Màu sắc chủ đạo** (white, navy blue, floral pattern, etc.)
2. **Chất liệu** nếu biết (cotton, linen, denim, polyester)
3. **Kiểu dáng** (slim-fit, oversized, A-line, wrap)
4. **Chi tiết đặc biệt** (button collar, V-neck, ruffled hem, embroidery)

**Template:** `"[color] [material] [fit/style] [category2] [notable details]"`

**Ví dụ đúng:**
```
"Navy blue linen wide-leg trousers with elastic waistband"
"Floral print chiffon wrap dress with tie waist, midi length"
"Black leather zip-up biker jacket with silver hardware"
```

**Tránh:**
```
"Nice shirt" — quá ngắn, không mô tả
"This is a white shirt" — filler phrase
"Item #1234" — không phải description
```

---

## 4. Cấu trúc thư mục

```
data/custom/catalog/
├── images/
│   ├── item_custom_001.jpg
│   ├── item_custom_002.jpg
│   └── ...
└── catalog_metadata.csv    # Dùng CSV khi collect thủ công; merge script convert → parquet
```

---

## 5. Thu thập từ nguồn mở

### Nguồn HuggingFace (đã verified)

| Dataset | Rows | Size | Chất lượng |
|---|---:|---:|---|
| `Marqo/deepfashion-inshop` | 52.6K | 216 MB | Cao — studio white bg |
| `Marqo/deepfashion-multimodal` | 42.5K | 153 MB | Cao — có caption |
| `Marqo/fashion200k` | 201.6K | 3.5 GB | Trung bình — web-scraped |

**Download nhanh:**
```python
from datasets import load_dataset
ds = load_dataset("Marqo/deepfashion-inshop", split="train")
```

### Maping schema DeepFashion → catalog_metadata

| DeepFashion field | catalog_metadata field |
|---|---|
| `id` | `item_ID` |
| `image` (PIL) | save to `images/`, `image_path` |
| `title` | `text` |
| `category_label` | `category2` (map to our taxonomy) |

---

## 6. Target distribution

| category1 | Min % | Min rows (tổng 50K) |
|---|---|---|
| tops | ≥ 20% | 10,000 |
| bottoms | ≥ 15% | 7,500 |
| dresses | ≥ 15% | 7,500 |
| outerwear | ≥ 10% | 5,000 |
| shoes | ≥ 15% | 7,500 |
| bags | ≥ 10% | 5,000 |
| accessories | ≥ 5% | 2,500 |

---

## 7. Validation script

```bash
uv run python scripts/validate_custom_data.py --phase 1B
```

Script kiểm tra:
- Tất cả `image_path` tồn tại
- `category1` trong 7 values hợp lệ
- `text` length 10–200 chars
- Không có `item_ID` duplicate
- In distribution report

---

## 8. Embedding dimension

Catalog encoder (`Marqo/marqo-fashionSigLIP`) output: **768-dim** L2-normalized vectors.  
Qdrant collection `catalog` được setup với `size=768`, `distance=Cosine`.
