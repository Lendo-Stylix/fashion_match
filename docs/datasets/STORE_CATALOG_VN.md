# Store Catalog VN — Data Collection Guide

> **Mục đích:** Thu thập data từ các store thời trang Việt Nam để hiển thị thông tin mua hàng (store, giá, link) bên cạnh outfit được recommend.  
> **Input chính:** JSON cào từ API/website của store → normalize → Parquet + Qdrant payload.  
> **Quan trọng:** Store/price data phục vụ **serving layer** (hiển thị UI), KHÔNG phải training signal cho encoder hoặc composer.

---

## 1. Vai trò trong kiến trúc (v3.1-lite)

Store data phục vụ **Tầng 1** (KB Builder) và **Tầng 3** (Retrieval) trong pipeline v3.1-lite:

```
Tầng 1 (KB Builder — src/outfitmatch/kb/)
  Item catalog từ VN stores → ItemRecord với store{} block
  → item_embedding, compatibility_score precomputed offline

Tầng 3 (Retrieval — Qdrant collection "outfits")
  Payload: has_vn_store=true, price_tier, store thông tin
  → filter nhanh để chỉ trả kết quả mua được tại VN

API Response (pipeline.py → RecommendResult)
  → mỗi OutfitRecord.items[i].store có đủ link mua + giá VND
```

Store data **KHÔNG** được dùng làm training signal cho OutfitTransformer hoặc Qwen3-VL LoRA.  
Ngoại lệ duy nhất: `price_tier` có thể làm Qdrant filter bổ sung nếu quiz capture ngân sách user (Tầng 4).

---

## 2. Database sẽ dùng

| Mục đích | Format | Vị trí | Lý do |
|---|---|---|---|
| **Store registry** (master list) | SQLite | `data/raw/stores/store_registry.db` | Quan hệ stores ↔ branches; dễ query theo city/district |
| **Item-store links** | CSV → Parquet | `data/raw/stores/item_store_links.csv` | Merge vào `catalog_metadata.parquet` qua `item_ID` |
| **Qdrant payload** | JSON payload per point | Collection `catalog` | Trả về store info trực tiếp từ ANN search, zero extra lookup |
| **Ảnh sản phẩm** | `.jpg`/`.png` | `data/custom/catalog/images/` | DVC-tracked, cùng thư mục với catalog items |

**Tại sao không dùng PostgreSQL/MongoDB:** Đây là project grading, volume data nhỏ (vài trăm đến vài nghìn items). SQLite + Parquet + Qdrant đủ. Không thêm infra phức tạp.

---

## 3. Schema: Store Registry (SQLite)

File: `data/raw/stores/store_registry.db`

### Bảng `stores`

```sql
CREATE TABLE stores (
    store_id     TEXT PRIMARY KEY,      -- "canifa_vn", "format_vn", "theblues_vn"
    store_name   TEXT NOT NULL,         -- "Canifa", "Format", "The Blues"
    store_type   TEXT NOT NULL,         -- "chain_brand" | "local_boutique" | "ecommerce_only" | "international_chain"
    website      TEXT,                  -- "https://canifa.com"
    price_tier   TEXT NOT NULL,         -- "budget" (<300K) | "mid" (300K-800K) | "premium" (>800K)
    target_gender TEXT NOT NULL,        -- "women" | "men" | "unisex"
    style_tags   TEXT,                  -- JSON array: ["casual", "workwear", "streetwear"]
    notes        TEXT
);
```

### Bảng `branches`

```sql
CREATE TABLE branches (
    branch_id    TEXT PRIMARY KEY,      -- "canifa_cau_giay_01"
    store_id     TEXT NOT NULL REFERENCES stores(store_id),
    city         TEXT NOT NULL,         -- "Hà Nội" | "Hồ Chí Minh" | "Đà Nẵng"
    district     TEXT,                  -- "Cầu Giấy"
    address      TEXT,                  -- địa chỉ đầy đủ
    maps_url     TEXT,                  -- Google Maps link
    is_active    INTEGER DEFAULT 1
);
```

### Ví dụ seed data

```sql
INSERT INTO stores VALUES
  ('canifa_vn',   'Canifa',      'chain_brand',        'https://canifa.com',    'mid',     'unisex', '["casual","workwear","basic"]',    NULL),
  ('format_vn',   'Format',      'chain_brand',        'https://formatstore.vn','mid',     'men',    '["casual","streetwear"]',         NULL),
  ('theblues_vn', 'The Blues',   'chain_brand',        'https://theblues.vn',   'mid',     'unisex', '["casual","denim"]',              NULL),
  ('libe_vn',     'Libé',        'local_boutique',     'https://libe.vn',       'premium', 'women',  '["feminine","workwear","chic"]',  NULL),
  ('uniqlo_vn',   'Uniqlo',      'international_chain','https://www.uniqlo.com/vn','mid',  'unisex', '["minimalist","basic","casual"]', NULL),
  ('zara_vn',     'Zara',        'international_chain','https://www.zara.com/vn','premium','unisex', '["trendy","workwear"]',           NULL),
  ('hm_vn',       'H&M',         'international_chain','https://www2.hm.com/vi_vn','mid',  'unisex', '["casual","trendy"]',            NULL),
  ('yody_vn',     'YODY',        'chain_brand',        'https://yody.vn',        'budget', 'unisex', '["casual","basic","sportswear"]', NULL),
  ('hnoss_vn',    'HNOSS',       'local_boutique',     'https://hnoss.vn',       'mid',    'women',  '["feminine","vintage","casual"]', NULL);
```

**`price_tier` mapping:**

| Tier | Khoảng giá (VND) | Dùng khi |
|---|---|---|
| `budget` | < 300,000 | Áo dưới 300K, quần dưới 400K |
| `mid` | 300,000 – 800,000 | Phần lớn chain brands VN |
| `premium` | > 800,000 | International brands, local luxury |

---

## 4. Schema: Item-Store Links (CSV)

File: `data/raw/stores/item_store_links.csv`  
Đây là bảng nối giữa `item_ID` trong catalog và store data. Merge vào `catalog_metadata.parquet` khi indexing.

| Column | Type | Required | Ví dụ |
|---|---|---|---|
| `item_ID` | string | ✅ | `item_custom_00001` |
| `store_id` | string (FK → stores) | ✅ | `canifa_vn` |
| `product_url` | string | ❌ | `https://canifa.com/ao-thun-co-tron-...` |
| `price_vnd` | integer | ✅ | `299000` |
| `sale_price_vnd` | integer | ❌ | `199000` (null nếu không có sale) |
| `available_sizes` | string (JSON array) | ❌ | `["S","M","L","XL"]` |
| `sku` | string | ❌ | `CNF-AT-001-WHT` (mã sản phẩm của store) |
| `in_stock` | boolean | ✅ | `true` |
| `collected_date` | date (YYYY-MM-DD) | ✅ | `2026-05-21` |
| `collector` | string | ✅ | `quang` (tên người collect, để trace lỗi) |

**Ví dụ rows:**

```csv
item_ID,store_id,product_url,price_vnd,sale_price_vnd,available_sizes,sku,in_stock,collected_date,collector
item_custom_00001,canifa_vn,https://canifa.com/ao-thun-co-tron,299000,,["S","M","L","XL"],,true,2026-05-21,quang
item_custom_00002,zara_vn,https://www.zara.com/vn/vi/dam-midi,899000,699000,["XS","S","M"],,true,2026-05-21,quang
```

**Lưu ý:** Một `item_ID` có thể có NHIỀU rows (bán ở nhiều store). Khi index vào Qdrant, merge thành array.

---

## 5. Schema: Qdrant Payload (Tầng 3 — v3.1-lite collection "outfits")

Mỗi point trong collection `outfits` (v3.1-lite) dùng `OutfitRecord.to_qdrant_payload()`. Các fields store-related trong payload:

```python
# Payload fields hiện tại (giữ nguyên):
{
    "item_ID": "item_custom_00001",
    "category1": "tops",
    "category2": "t-shirts",
    "color": "white",
    "body_shape_fit": ["hourglass", "rectangle"],  # từ outfit composer
    "occasion": ["casual", "weekend"],
}

# Fields bổ sung cho store info:
{
    # ... fields hiện tại ...
    "price_vnd": 299000,                    # giá thấp nhất (nếu nhiều store)
    "price_tier": "mid",                    # "budget" | "mid" | "premium"
    "stores": [                             # list để hỗ trợ multi-store
        {
            "store_id": "canifa_vn",
            "store_name": "Canifa",
            "product_url": "https://canifa.com/...",
            "price_vnd": 299000,
            "in_stock": True,
        }
    ],
    "has_vn_store": True,                   # filter nhanh: chỉ lấy item có store VN
}
```

**Qdrant filter dùng được ngay:**

```python
# Chỉ recommend items có bán ở VN store
from qdrant_client.models import Filter, FieldCondition, MatchValue

vn_filter = Filter(must=[
    FieldCondition(key="has_vn_store", match=MatchValue(value=True))
])

# Filter theo budget (Sprint 9 preference extension):
budget_filter = Filter(must=[
    FieldCondition(key="price_tier", match=MatchValue(value="budget"))
])
```

---

## 6. API Response (RecommendResult — v3.1-lite)

`recommend_outfit()` → `RecommendResult.outfits` — mỗi `OutfitRecord.items[i].store` chứa:

```json
{
  "outfit": [
    {
      "item_ID": "item_custom_00001",
      "category": "tops",
      "image_url": "...",
      "caption": "White cotton slim-fit shirt",
      "store_info": [
        {
          "store_name": "Canifa",
          "store_id": "canifa_vn",
          "price_vnd": 299000,
          "sale_price_vnd": null,
          "product_url": "https://canifa.com/...",
          "in_stock": true
        }
      ],
      "price_display": "299.000 ₫",
      "price_tier": "mid"
    }
  ]
}
```

Nếu item từ HF dataset (không có VN store data), `store_info` trả về `[]` và `price_display` trả về `null`.

---

## 7. Cấu trúc thư mục

```
data/
├── raw/
│   └── stores/
│       ├── store_registry.db         # SQLite — master store list + branches
│       ├── item_store_links.csv      # Item ↔ store mapping (thu thập thủ công)
│       └── item_store_links.parquet  # Generated bởi merge script (DVC-tracked)
└── custom/
    └── catalog/
        ├── images/                   # Ảnh sản phẩm từ VN stores (cùng thư mục)
        └── catalog_metadata.csv      # Metadata catalog (thêm store columns)
```

---

## 8. Quy trình thu thập từ JSON scrape

### Tổng quan pipeline

```
Store website/API
      │  (scrape thủ công hoặc script cào)
      ▼
data/raw/stores/scraped/<store_id>/
      raw_products.json          ← JSON gốc từ store (giữ nguyên)
      │
      │  scripts/normalize_store_json.py
      ▼
data/raw/stores/item_store_links.csv   ← normalized, store-agnostic
data/custom/catalog/images/            ← ảnh downloaded
data/custom/catalog/catalog_metadata.csv
      │
      │  scripts/index_catalog.py
      ▼
Qdrant collection "catalog"
```

---

### Schema: Raw scrape JSON (store-agnostic)

Lưu JSON gốc vào `data/raw/stores/scraped/<store_id>/raw_products.json` **không sửa**. Normalize script sẽ đọc file này.

**Format chuẩn hóa** (mỗi store adapter output ra format này):

```json
[
  {
    "store_id": "canifa_vn",
    "sku": "CNF-AT-001-WHT",
    "name": "Áo thun cổ tròn basic",
    "price_vnd": 299000,
    "sale_price_vnd": null,
    "product_url": "https://canifa.com/ao-thun-co-tron-basic.html",
    "image_urls": [
      "https://canifa.com/img/primary/ao-thun-001-front.jpg",
      "https://canifa.com/img/primary/ao-thun-001-back.jpg"
    ],
    "category_raw": "Áo / Áo thun",
    "colors": ["Trắng", "Đen", "Xanh navy"],
    "sizes": ["S", "M", "L", "XL"],
    "in_stock": true,
    "description": "Áo thun cổ tròn chất liệu cotton 100%...",
    "scraped_at": "2026-05-21T10:30:00+07:00"
  }
]
```

**Trường bắt buộc:** `store_id`, `name`, `price_vnd`, `product_url`, `image_urls` (ít nhất 1), `scraped_at`.  
**Trường tùy chọn:** `sku`, `sale_price_vnd`, `colors`, `sizes`, `description`.

---

### Mapping category_raw → catalog schema

Mỗi store có taxonomy khác nhau. Normalize script dùng bảng mapping per-store:

```python
# scripts/store_adapters/canifa.py
CATEGORY_MAP = {
    "Áo / Áo thun":        ("tops",      "t-shirts"),
    "Áo / Áo sơ mi":       ("tops",      "shirts"),
    "Áo / Áo polo":        ("tops",      "polo"),
    "Áo / Áo khoác":       ("outerwear", "jackets"),
    "Quần / Quần jean":    ("bottoms",   "jeans"),
    "Quần / Quần âu":      ("bottoms",   "trousers"),
    "Quần / Quần short":   ("bottoms",   "shorts"),
    "Váy / Váy liền thân": ("dresses",   "midi-dress"),
    "Giày / Sneaker":      ("shoes",     "sneakers"),
    # ...
}
```

Nếu `category_raw` không có trong map → ghi log warning, set `category1="unknown"`, skip khỏi training split nhưng vẫn giữ trong store links.

---

### Bước 1: Cào JSON từ store

Cào thủ công hoặc script đơn giản. Lưu JSON gốc trước, normalize sau:

```bash
# Ví dụ: cào API listing của Canifa (nếu có public JSON endpoint)
curl "https://canifa.com/api/products?category=ao-thun&limit=100" \
  > data/raw/stores/scraped/canifa_vn/raw_products.json

# Hoặc copy response từ DevTools → Network tab → response JSON → paste vào file
```

**Lưu ý scraping:**
- Không DDoS: thêm `time.sleep(1-3)` giữa các request nếu viết script tự động
- Lưu raw JSON trước khi parse — dễ re-run normalize khi schema thay đổi
- Ảnh: download về local, không dùng URL trực tiếp làm `image_path` (URL có thể expire)

---

### Bước 2: Normalize JSON → CSV + download ảnh

```bash
uv run python scripts/normalize_store_json.py \
    --store canifa_vn \
    --input  data/raw/stores/scraped/canifa_vn/raw_products.json \
    --out-links   data/raw/stores/item_store_links.csv \
    --out-catalog data/custom/catalog/catalog_metadata.csv \
    --out-images  data/custom/catalog/images/
```

Script này:
1. Đọc raw JSON
2. Map `category_raw` → `category1/category2` theo store adapter
3. Download `image_urls[0]` (front view) → `data/custom/catalog/images/item_custom_XXXXX.jpg`
4. Tự động generate `item_ID = item_custom_<5-digit>` (sequential, no collision)
5. Ghi dòng vào `item_store_links.csv` và `catalog_metadata.csv`

---

### Bước 3: Validate

```bash
uv run python scripts/validate_custom_data.py --phase 1B
uv run python scripts/validate_store_links.py
```

`validate_store_links.py` kiểm tra:
- Tất cả `store_id` trong links tồn tại trong `store_registry.db`
- Tất cả `item_ID` trong links có ảnh tương ứng trong `images/`
- `price_vnd > 0`
- `scraped_at` không quá 90 ngày cũ (stale price warning)

---

### Bước 4: Index vào Qdrant

```bash
uv run python scripts/index_catalog.py \
    --catalog data/raw/catalog/catalog_metadata.parquet \
    --store-links data/raw/stores/item_store_links.parquet \
    --qdrant-url http://localhost:6333
```

Script populate `stores`, `price_vnd`, `price_tier`, `has_vn_store` vào Qdrant payload.

---

### Cấu trúc thư mục scraped data

```
data/raw/stores/
├── store_registry.db
├── item_store_links.csv          # normalized, all stores merged
├── item_store_links.parquet      # generated by merge script (DVC-tracked)
└── scraped/
    ├── canifa_vn/
    │   └── raw_products.json     # JSON gốc — không sửa sau khi cào
    ├── format_vn/
    │   └── raw_products.json
    └── uniqlo_vn/
        └── raw_products.json
```

---

## 9. Danh sách store đề xuất để collect

Ưu tiên theo độ phổ biến và đa dạng style/budget:

| Store | Type | Budget tier | Style | Website |
|---|---|---|---|---|
| YODY | chain_brand | budget | casual, basic | yody.vn |
| Canifa | chain_brand | mid | casual, workwear | canifa.com |
| Format | chain_brand | mid | men, streetwear | formatstore.vn |
| The Blues | chain_brand | mid | denim, casual | theblues.vn |
| Uniqlo VN | international_chain | mid | minimalist | uniqlo.com/vn |
| Libé | local_boutique | premium | feminine, chic | libe.vn |
| Elise | chain_brand | mid | women, feminine | elise.vn |
| Owen | chain_brand | mid | men, workwear | owenfashion.vn |
| Zara VN | international_chain | premium | trendy | zara.com/vn |
| H&M VN | international_chain | mid | casual | hm.com/vi_vn |

**Target:** ≥ 20 items/store × 10 stores = 200 items có VN store data.

---

## 10. Liên kết với Tầng 4 (Quiz Re-rank — v3.1-lite)

User chọn `price_tier` trong quiz onboarding (câu 4). `PreferenceProfile.price_tier` được dùng để:
1. Tăng/giảm điểm trong `score_outfit_for_preference()` (penalty nếu sai tier — xem `quiz/rerank.py`)
2. Có thể bổ sung Qdrant pre-filter theo `price_tier` nếu muốn hard constraint (Sprint 8):

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

budget_filter = Filter(must=[
    FieldCondition(key="price_tier", match=MatchValue(value=profile.price_tier))
])
```

---

## 11. Lưu ý quan trọng

1. **Price stale fast** — giá VN stores thay đổi thường xuyên. Ghi `collected_date` và cảnh báo nếu > 90 ngày.
2. **Không commit ảnh lên git** — chỉ commit `.dvc` files; ảnh qua DVC.
3. **store_id phải snake_case lowercase** — `canifa_vn`, không phải `Canifa VN`.
4. **Item từ HF dataset** — để `store_id = null` và `has_vn_store = false` trong Qdrant; UI hiển thị "Không có thông tin mua hàng tại VN".
5. **Một item nhiều store** — chèn nhiều rows trong `item_store_links.csv` cùng `item_ID`, index script sẽ merge thành array trong Qdrant payload.
6. **Không dùng price làm training signal** — encoder và composer train hoàn toàn độc lập với price/store data.
