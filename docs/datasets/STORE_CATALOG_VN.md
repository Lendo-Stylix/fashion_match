# Store Catalog VN — Manual Collection Guide (v3.1-lite)

> **Mục đích:** Thu thập item từ store VN có chọn lọc để build Tầng 1 KB và hiển thị
> link mua tại store local bên cạnh outfit recommend.
> **Project status:** chỉ là skeleton — toàn bộ catalog sẽ được **scrape thủ công**;
> không có pipeline auto-scrape trong repo.
> **Quan trọng:** store/price data phục vụ **serving** (hiển thị UI). Không dùng làm
> training signal cho OutfitTransformer-labse hoặc Qwen3-VL LoRA.

---

## 1. Vai trò trong v3.1-lite

```
Tầng 1 (KB Builder — src/outfitmatch/kb/)
  VN store items → ItemRecord với store{} block
  → OT-labse item_embedding offline + outfit compatibility_score

Tầng 3 (Retrieval — Qdrant collection "outfits")
  Payload: has_vn_store=true, price_tier, … → filter nhanh chỉ trả kết quả mua được tại VN

API Response (pipeline.py → RecommendResult)
  → mỗi OutfitRecord.items[i].store có đủ link mua + giá VND
```

Ngoại lệ duy nhất giữa store data và Tầng 4: `price_tier` được dùng làm Qdrant filter
nếu quiz capture ngân sách user.

---

## 2. Storage layout

| Mục đích | Format | Vị trí |
|---|---|---|
| **Store registry** (master list) | SQLite | `data/cache/store_registry.db` |
| **Catalog metadata** | Parquet | `data/custom/catalog/catalog_metadata.parquet` |
| **Item ↔ store links** | Parquet | `data/custom/catalog/item_store_links.parquet` |
| **Qdrant payload** (Tầng 3) | JSON payload / point | Collection `outfits` |
| **Ảnh sản phẩm** | `.jpg` / `.png` | `data/custom/catalog/images/item_custom_NNNNN.jpg` |

> Volume MVP: vài trăm đến vài nghìn items → SQLite + Parquet + Qdrant đủ. Không thêm
> Postgres/Mongo. DVC/git-lfs sẽ chốt sau khi user thực sự thu thập đủ dữ liệu.

---

## 3. Schema — Store Registry (SQLite)

File: `data/cache/store_registry.db`

```sql
CREATE TABLE stores (
    store_id      TEXT PRIMARY KEY,    -- "canifa_vn", "format_vn"
    store_name    TEXT NOT NULL,       -- "Canifa", "Format"
    store_type    TEXT NOT NULL,       -- chain_brand | local_boutique | international_chain | ecommerce_only
    website       TEXT,                -- "https://canifa.com"
    price_tier    TEXT NOT NULL,       -- PRICE_TIER enum (budget|mid|premium) — vocab.py
    target_gender TEXT NOT NULL,       -- women | men | unisex
    style_tags    TEXT,                -- JSON array of STYLE enum values (vocab.py)
    notes         TEXT
);

CREATE TABLE branches (
    branch_id  TEXT PRIMARY KEY,
    store_id   TEXT NOT NULL REFERENCES stores(store_id),
    city       TEXT NOT NULL,
    district   TEXT,
    address    TEXT,
    maps_url   TEXT,
    is_active  INTEGER DEFAULT 1
);
```

### Seed data

```sql
INSERT INTO stores VALUES
  ('canifa_vn',   'Canifa',    'chain_brand',         'https://canifa.com',         'mid',     'unisex', '["casual","minimalist"]',     NULL),
  ('format_vn',   'Format',    'chain_brand',         'https://formatstore.vn',     'mid',     'men',    '["casual","streetwear"]',     NULL),
  ('theblues_vn', 'The Blues', 'chain_brand',         'https://theblues.vn',        'mid',     'unisex', '["casual"]',                  NULL),
  ('libe_vn',     'Libé',      'local_boutique',      'https://libe.vn',            'premium', 'women',  '["feminine","elegant"]',      NULL),
  ('uniqlo_vn',   'Uniqlo',    'international_chain', 'https://www.uniqlo.com/vn',  'mid',     'unisex', '["minimalist","casual"]',     NULL),
  ('zara_vn',     'Zara',      'international_chain', 'https://www.zara.com/vn',    'premium', 'unisex', '["elegant","streetwear"]',    NULL),
  ('hm_vn',       'H&M',       'international_chain', 'https://www2.hm.com/vi_vn',  'mid',     'unisex', '["casual"]',                  NULL),
  ('yody_vn',     'YODY',      'chain_brand',         'https://yody.vn',            'budget',  'unisex', '["casual","sporty"]',         NULL),
  ('hnoss_vn',    'HNOSS',     'local_boutique',      'https://hnoss.vn',           'mid',     'women',  '["feminine","vintage"]',      NULL);
```

**`price_tier`** (PRICE_TIER enum trong `src/outfitmatch/vocab.py`):

| Tier | Khoảng giá (VND) | Áp dụng |
|---|---|---|
| `budget` | < 300,000 | Áo dưới 300K, quần dưới 400K |
| `mid` | 300,000 – 800,000 | Phần lớn chain brands VN |
| `premium` | > 800,000 | International brands, local luxury |

**`style_tags`** chỉ chứa giá trị từ `STYLE` enum trong `vocab.py`
(`minimalist | korean | streetwear | elegant | casual | vintage | sporty | feminine`).

---

## 4. Schema — Item / Item-Store Links (Parquet)

### `catalog_metadata.parquet`

Mỗi item ăn khớp 1-1 với `ItemRecord` trong `src/outfitmatch/kb/schema.py`.

| Column | Type | Required | Ghi chú |
|---|---|---|---|
| `item_id` | string | ✅ | `item_custom_NNNNN` (5+ digit sequential) |
| `category` | string | ✅ | `ITEM_CATEGORY` enum (top/bottom/dress/outerwear/shoes/bag/accessory) |
| `image_path` | string | ✅ | path relative tới repo: `data/custom/catalog/images/item_custom_NNNNN.jpg` |
| `title_vi` | string | ✅ | Tiêu đề sản phẩm theo store (LaBSE xử lý đa ngôn ngữ) |
| `desc_vi` | string | ❌ | Mô tả sản phẩm |
| `colors` | string (JSON list) | ❌ | màu hiển thị, free-form (vd `["trắng","navy"]`) |
| `collected_date` | date | ✅ | `YYYY-MM-DD` — flag stale nếu > 90 ngày |
| `collector` | string | ✅ | Tên người thu thập (để trace) |

### `item_store_links.parquet`

| Column | Type | Required | Ví dụ |
|---|---|---|---|
| `item_id` | string | ✅ | `item_custom_00001` |
| `store_id` | string (FK → stores) | ✅ | `canifa_vn` |
| `product_url` | string | ✅ | `https://canifa.com/...` |
| `price_vnd` | integer | ✅ | `299000` |
| `sale_price_vnd` | integer | ❌ | `199000` (null nếu không có sale) |
| `sku` | string | ❌ | `CNF-AT-001-WHT` |
| `in_stock` | boolean | ✅ | `true` |
| `available_sizes` | JSON list[str] | ❌ | Tất cả size store niêm yết (upper-cased), trích từ variant options. |
| `sizes_in_stock` | JSON list[str] | ❌ | Subset còn hàng (`variant.available == true`). |

> Một `item_id` có thể có nhiều rows (cùng item bán ở nhiều store). Lúc index Qdrant,
> merge thành array trong `ItemRecord.store` payload.

---

## 5. Qdrant Payload (Tầng 3)

`OutfitRecord.to_qdrant_payload()` trong `src/outfitmatch/kb/schema.py` trả về payload
chuẩn cho collection `outfits`. Các field store-related quan trọng:

```python
{
    # ── conditioning fields (Tầng 3 filter) ──────────────────────────
    "occasion":        ["office", "cafe_hangout"],   # OCCASION enum
    "style":           ["minimalist", "korean"],     # STYLE enum
    "body_shapes_fit": ["pear", "hourglass"],        # BODY_SHAPE enum
    "season":          ["transitional"],             # SEASON enum

    # ── store info ──────────────────────────────────────────────────
    "price_total_vnd": 850000,                       # tổng giá thấp nhất
    "price_tier":      "mid",                        # PRICE_TIER enum
    "has_vn_store":    True,                         # filter nhanh
    "color_palette":   ["beige", "navy"],            # free-form

    # ── meta ─────────────────────────────────────────────────────────
    "compatibility_score": 0.83,
    "stylist_explanation_vi": "Set blazer oversized...",
    "gen_method": "fitb_beam",
}
```

Payload indexes (tạo bởi `scripts/setup_databases.py`):
`occasion`, `style`, `body_shapes_fit`, `price_tier`, `season`, `has_vn_store`.

### Ví dụ filter

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

vn_only = Filter(must=[
    FieldCondition(key="has_vn_store", match=MatchValue(value=True)),
    FieldCondition(key="price_tier",   match=MatchValue(value="mid")),
])
```

---

## 6. Cấu trúc thư mục

```
data/
├── custom/
│   └── catalog/
│       ├── images/                       # item_custom_NNNNN.jpg
│       ├── catalog_metadata.parquet      # ItemRecord-compatible metadata
│       └── item_store_links.parquet      # item_id ↔ store mapping
└── cache/
    ├── store_registry.db                 # SQLite — stores + branches
    └── gemini_tagging.db                 # Gemini Flash response cache
```

---

## 7. Manual collection workflow

Project chỉ là skeleton — chưa có script auto-scrape. Workflow đề xuất:

1. **Cào / chụp item** từ store website (DevTools → Network response, hoặc copy ảnh + giá).
2. **Đặt ảnh** vào `data/custom/catalog/images/item_custom_NNNNN.jpg`
   (`NNNNN` 5 chữ số sequential).
3. **Thêm 1 row** vào `catalog_metadata.parquet` (dùng `pandas` notebook hoặc 1 script
   nhỏ tự viết) — theo schema §4.
4. **Thêm 1 row** vào `item_store_links.parquet` cho mỗi store bán item đó.
5. **Validate** thủ công: ảnh tồn tại, `category` thuộc `ITEM_CATEGORY` enum, `price_vnd > 0`,
   `collected_date` không quá 90 ngày.

Lưu ý scraping:
- Không DDoS: nếu viết script, sleep 1–3s giữa request.
- Lưu raw response trước khi parse — dễ re-run khi schema thay đổi.
- Download ảnh về local; KHÔNG dùng URL trực tiếp làm `image_path` (URL có thể expire).

---

## 8. Stores đề xuất collect

Ưu tiên theo độ phổ biến và đa dạng style/budget:

| Store | Type | Tier | Style chính |
|---|---|---|---|
| YODY | chain_brand | budget | casual, sporty |
| Canifa | chain_brand | mid | casual, minimalist |
| Format | chain_brand | mid | streetwear (men) |
| The Blues | chain_brand | mid | casual |
| Uniqlo VN | international_chain | mid | minimalist |
| Libé | local_boutique | premium | feminine, elegant |
| Elise | chain_brand | mid | feminine |
| Owen | chain_brand | mid | elegant (men) |
| Zara VN | international_chain | premium | elegant, streetwear |
| H&M VN | international_chain | mid | casual |

**MVP target:** ≥ 20 items/store × 10 stores = **≥ 200 items có VN store**
(spike thực tế sẽ điều chỉnh ở Sprint 0).

---

## 9. Liên kết Tầng 4 (Quiz Re-rank)

User chọn `price_tier` trong quiz onboarding (câu 4). `PreferenceProfile.price_tier`
được dùng bởi `src/outfitmatch/quiz/rerank.py`:

1. `score_outfit_for_preference()` — penalty −0.10 nếu `outfit.price_tier != pref.price_tier`.
2. Có thể bổ sung Qdrant hard-filter `price_tier` ngay từ Tầng 3 (Sprint 8 quyết định).

---

## 10. Lưu ý quan trọng

1. **Price stale fast** — giá VN stores thay đổi thường xuyên. Luôn ghi `collected_date`;
   cảnh báo / re-collect nếu > 90 ngày.
2. **Không commit ảnh lên git** — ảnh chỉ tồn tại local hoặc qua git-lfs nếu bắt buộc.
3. **`store_id` phải snake_case lowercase** — `canifa_vn`, không phải `Canifa VN`.
4. **Một item nhiều store** — chèn nhiều rows trong `item_store_links.parquet`; index script
   sẽ merge thành array trong Qdrant payload.
5. **Không dùng price làm training signal** — OT-labse và Qwen3-VL LoRA train hoàn toàn
   độc lập với price/store data.
