# Store Catalog VN — Catalog + Graph KB Input Guide (v3.1-lite)

> **Mục đích:** Thu thập item từ store VN/local purchasable để build **graph KB** của dự án và hiển thị link mua thật trong kết quả recommend.
> **Trạng thái hiện tại:** repo **đã có** pipeline scrape + quality gate + graph build. Manual curation vẫn hữu ích khi cần sửa nhãn hoặc bổ sung item đặc biệt.
> **Quan trọng:** store/price data phục vụ **catalog, retrieval, serving**. Không dùng làm training signal cho OutfitTransformer-labse hoặc Qwen3-VL LoRA.

---

## 1. Vai trò trong v3.1-lite

```text
Tầng 1 (KB Builder — src/outfitmatch/kb/)
  VN store items -> ItemRecord (category / gender / formality / store)
  -> OT-labse item_embedding
  -> build_graph -> data/custom/graph/item_edges.parquet

Tầng 3 (Retrieval — Qdrant collection "items")
  Payload item node: category / gender / formality / price_tier / has_vn_store / in_stock / store_id
  -> filter seed item (top / dress) -> graph traversal ráp outfit động

API Response (pipeline.py -> RecommendResult)
  -> mỗi item vẫn giữ link mua + giá VND + size/stock từ store thật
```

**Lưu ý:** `price_tier` và `price_max` hiện chủ yếu phục vụ post-filter / quiz rerank trên
`OutfitRecord` dẫn xuất; seed filter chính của graph path là `category + gender + formality + stock + VN store`.

---

## 2. Storage layout

| Mục đích | Format | Vị trí |
|---|---|---|
| **Store registry** (master list) | SQLite | `data/cache/store_registry.db` |
| **Catalog metadata** | Parquet | `data/custom/catalog/catalog_metadata.parquet` |
| **Item ↔ store links** | Parquet | `data/custom/catalog/item_store_links.parquet` |
| **Graph edges** | Parquet | `data/custom/graph/item_edges.parquet` |
| **Qdrant item nodes** | Vector collection | `items` |
| **Ảnh sản phẩm** | `.jpg` / `.png` | `data/custom/catalog/images/item_custom_NNNNN.jpg` |
| **Raw scrape replay cache** | files | `data/cache/raw/<store_id>/` |

> `item_edges.parquet` là artifact graph baseline hiện hành. Catalog/images/raw cache vẫn được share ngoài Git; file edge nhỏ nên có thể được track để làm regression baseline.

---

## 3. Schema — Store Registry (SQLite)

File: `data/cache/store_registry.db`

```sql
CREATE TABLE stores (
    store_id      TEXT PRIMARY KEY,    -- "canifa_vn", "format_vn"
    store_name    TEXT NOT NULL,
    store_type    TEXT NOT NULL,       -- chain_brand | local_boutique | international_chain | ecommerce_only
    website       TEXT,
    price_tier    TEXT NOT NULL,       -- PRICE_TIER enum (budget|mid|premium)
    target_gender TEXT NOT NULL,       -- men | women | unisex
    style_tags    TEXT,                -- JSON array of STYLE enum values
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

---

## 4. Schema — Catalog parquet inputs

### `catalog_metadata.parquet`

Mỗi row là 1 item, tương thích với `ItemRecord` trong `src/outfitmatch/kb/schema.py`.

| Column | Type | Required | Ghi chú |
|---|---|---|---|
| `item_id` | string | ✅ | Stable ID dạng `item_custom_NNNNN` |
| `category` | string | ✅ | `ITEM_CATEGORY` enum |
| `source_product_type` | string | ❌ | Nhãn gốc của store trước khi map category |
| `gender` | string | ✅ | `GENDER` enum (`men`, `women`, `unisex`, `kid`) |
| `formality` | string | ✅ | `FORMALITY` enum (`athletic`, `casual`, `smart_casual`, `formal`) |
| `image_path` | string | ✅ | repo-relative path tới ảnh local |
| `title_vi` | string | ✅ | tên sản phẩm từ store |
| `desc_vi` | string | ❌ | mô tả sản phẩm |
| `colors` | string (JSON list) | ❌ | màu hiển thị |
| `collected_date` | date/string | ✅ | ngày scrape / collect |
| `collector` | string | ✅ | người hoặc job thu thập |

### `item_store_links.parquet`

| Column | Type | Required | Ví dụ |
|---|---|---|---|
| `item_id` | string | ✅ | `item_custom_00001` |
| `store_id` | string (FK → stores) | ✅ | `canifa_vn` |
| `source_product_id` | string | ✅ | stable upstream product id / handle |
| `product_url` | string | ✅ | `https://canifa.com/...` |
| `price_vnd` | integer | ✅ | `299000` |
| `sale_price_vnd` | integer | ❌ | `199000` |
| `sku` | string | ❌ | `CNF-AT-001-WHT` |
| `in_stock` | boolean | ✅ | `true` |
| `available_sizes` | JSON list[str] | ❌ | tất cả size store niêm yết |
| `sizes_in_stock` | JSON list[str] | ❌ | subset còn hàng |

> Một `item_id` tương ứng một item catalog chuẩn hoá; data hiện hành thường là **1 link / 1 store / 1 item**, nhưng schema vẫn cho phép nhiều dòng nếu sau này cùng item bán ở nhiều nguồn.

---

## 5. Graph artifacts + Qdrant item payload

### `data/custom/graph/item_edges.parquet`

Đây là output chính của KB graph. Mỗi row là **1 cạnh chuẩn hoá một chiều**:

| Column | Type | Ý nghĩa |
|---|---|---|
| `src_id` | string | item nguồn |
| `dst_id` | string | item đích |
| `src_category` | string | category của nguồn |
| `dst_category` | string | category của đích |
| `weight` | float | compatibility weight |

File này được `src/outfitmatch/kb/graph_store.py` đọc lại để tạo `OutfitGraph`
phục vụ `neighbors()` / `edge_weight()` / `item()`.

### Qdrant collection `items`

`index_item_nodes()` mirror item nodes vào Qdrant để **filter seed item** nhanh:

```python
{
    "item_id": "item_custom_00001",
    "category": "top",
    "gender": "women",
    "formality": "smart_casual",
    "price_vnd": 299000,
    "price_tier": "budget",
    "has_vn_store": True,
    "in_stock": True,
    "store_id": "canifa_vn",
    "colors": ["beige", "navy"],
    "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
    "product_url": "https://canifa.com/...",
}
```

Payload indexes hiện dùng: `category`, `gender`, `formality`, `price_tier`,
`has_vn_store`, `in_stock`, `store_id`.

> **Primary path:** Qdrant chỉ giữ **item nodes**. Outfit được ráp động ở retrieval; collection `outfits` chỉ còn giá trị legacy/comparison.

---

## 6. Cấu trúc thư mục

```text
data/
├── cache/
│   ├── store_registry.db
│   ├── raw/
│   │   └── <store_id>/
│   └── gemini_tagging.db
└── custom/
    ├── catalog/
    │   ├── images/
    │   ├── catalog_metadata.parquet
    │   ├── item_store_links.parquet
    │   └── scrape_manifest.json
    ├── graph/
    │   └── item_edges.parquet
    └── outfits/
        └── generated_outfits.parquet   # legacy comparison only
```

---

## 7. Workflow: scrape -> quality -> graph

### A. Smoke scrape / crawl catalog

```powershell
uv run python -m scripts.data.scrape.run --limit 20 --no-images --dry-run
uv run python -m scripts.data.scrape.run --store yody_vn
uv run python -m scripts.data.scrape.run
```

### B. Validate catalog

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.quality
```

### C. Build graph KB

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80
```

### D. Grade graph / smoke retrieval quality

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office
```

### E. Manual curation (khi cần)

- sửa `catalog_metadata.parquet` / `item_store_links.parquet` để vá nhãn hiếm;
- re-run `scripts.data.scrape.retag_catalog` nếu thay logic category / gender / formality;
- rebuild graph sau khi catalog đổi.

---

## 8. Stores đề xuất / hiện có

Ưu tiên store có ảnh item sạch, giá rõ ràng, link ổn định, và style/budget đa dạng:

| Store | Type | Tier | Style chính |
|---|---|---|---|
| YODY | chain_brand | budget | casual, sporty |
| Canifa | chain_brand | mid | casual, minimalist |
| Aristino | chain_brand | mid | smart_casual, men |
| DirtyCoins | streetwear/local | mid | streetwear |
| Huelleyrose | local_boutique | mid/premium | feminine |
| Rubies | local_boutique | mid | feminine |
| Uniqlo VN | international_chain | mid | minimalist |
| Zara VN | international_chain | premium | elegant, streetwear |

---

## 9. Liên kết với Tầng 4 (Quiz / Sizing)

- `PreferenceProfile.price_tier` được dùng ở `quiz/rerank.py` để boost/penalty sau khi Tầng 3 trả danh sách outfit ráp động.
- `available_sizes` / `sizes_in_stock` được `quiz/sizing.py` và `validate_sizes()` dùng để tránh Qwen gợi ý size không có thật.
- `body_shape` hiện **chưa** được filter ở graph seed/node level; cần item semantic tagging follow-up để bật body-conditioning ablation.

---

## 10. Lưu ý quan trọng

1. **Không đổi enum value** trong `vocab.py` (`category`, `gender`, `formality`, `price_tier`, ...).
2. **Ưu tiên taxonomy của store (`source_product_type`) hơn title parsing** khi phân loại category.
3. **Ảnh phải là file local**; không dùng hotlink remote làm `image_path`.
4. **Luôn giữ `collected_date`** vì giá/stock stale nhanh.
5. **Graph là đường dẫn chính.** `generated_outfits.parquet` / Qdrant `outfits` chỉ còn phục vụ so sánh legacy.
6. **Một item thêm/sửa có thể đổi graph rộng hơn seed của nó**; sau khi retag catalog, nên rebuild hoặc chạy incremental build có kiểm tra lại metric coverage/coherence.
