# OutfitMatch Dataset README

README này dùng để share artifact dữ liệu giữa các thành viên team. **Primary KB path hiện là graph**: catalog item nodes + `data/custom/graph/item_edges.parquet` + Qdrant `items`. Materialized `generated_outfits.parquet` chỉ còn giữ cho mục đích legacy/comparison.

> Hầu hết dữ liệu catalog/images/cache **không commit lên Git**. Ngoại lệ hiện tại là `data/custom/graph/item_edges.parquet` có thể được track như baseline nhỏ (~MB-level) cho retrieval/eval regression.

---

## 1. Dataset gồm những gì?

| Nhóm | Mục đích | File/thư mục chính |
|---|---|---|
| **VN Store Catalog** | Item thời trang từ store VN/local VN, có giá và link mua được | `data/custom/catalog/catalog_metadata.parquet`, `data/custom/catalog/item_store_links.parquet`, `data/custom/catalog/images/` |
| **Graph KB (primary)** | Sparse item-compatibility graph để retrieval ráp outfit động | `data/custom/graph/item_edges.parquet` |
| **Legacy Materialized Outfits** | Snapshot outfit materialized để so sánh / debug | `data/custom/outfits/generated_outfits.parquet` |

Các file phụ trợ:

| Path | Nội dung |
|---|---|
| `data/cache/store_registry.db` | SQLite registry store/brand |
| `data/cache/raw/<store_id>/` | Raw HTTP/text cache để replay parse mà không crawl lại |
| `data/custom/catalog/scrape_manifest.json` | Kết quả quality gate từng batch |
| `data/custom/catalog/quarantine/` | Chỉ xuất hiện khi có batch fail quality gate |
| `link_web.txt` | Danh sách website/store đã khảo sát |

---

## 2. Current snapshot

Snapshot gần nhất (rebuild/catalog quality gate `2026-06-01`) đã validate:

### VN Store Catalog

- `5618` catalog items
- `5618` item-store links
- `25/25` manifest batches passed; không có quarantine directory
- `0` hard errors
- `1` warning: `556` item thiếu `desc_vi` (chấp nhận được)

Store distribution:

| Store | Items |
|---|---:|
| `yody_vn` | 2301 |
| `aristino_vn` | 1606 |
| `canifa_vn` | 684 |
| `rubies` | 468 |
| `huelleyrose` | 328 |
| `dirtycoins` | 231 |

Category distribution:

| Category | Items |
|---|---:|
| `top` | 2800 |
| `bottom` | 1457 |
| `outerwear` | 383 |
| `dress` | 364 |
| `accessory` | 348 |
| `bag` | 136 |
| `shoes` | 130 |

### Graph KB (primary)

Adult graph build (`men|women|unisex`) hiện hành:

- `4694` item nodes
- `316559` canonical edges trong `item_edges.parquet`
- Historical build time baseline ~`27.4s`
- Historical degree min / median / max = `60 / 76 / 2809`
- `catalog_coverage = 0.7069`
- `coherence_violations = 0`
- `fitb_recall@5 = 0.9813`
- `n_assembled = 7350`
- `item_reuse_p95 = 27`

### Legacy Materialized Outfits (comparison only)

- `1000` generated outfits
- `1000` unique item combinations
- `0` invalid category-rule combinations
- Compatibility score range: `0.600–0.980`
- `0` mixed-gender outfits; `0` formality-clash outfits
- Method mix: `700` FITB-beam / `300` random-scored

---

## 3. Folder layout coworker cần có

```text
data/
├── cache/
│   ├── store_registry.db
│   └── raw/
│       ├── yody_vn/
│       ├── canifa_vn/
│       ├── aristino_vn/
│       ├── huelleyrose/
│       ├── dirtycoins/
│       └── rubies/
└── custom/
    ├── catalog/
    │   ├── catalog_metadata.parquet
    │   ├── item_store_links.parquet
    │   ├── scrape_manifest.json
    │   └── images/
    │       ├── item_custom_00001.jpg
    │       └── ...
    ├── graph/
    │   └── item_edges.parquet
    └── outfits/
        └── generated_outfits.parquet   # optional legacy snapshot
```

Minimum files để chạy **graph retrieval / eval**:

```text
data/custom/catalog/catalog_metadata.parquet
data/custom/catalog/item_store_links.parquet
data/custom/catalog/images/
data/custom/graph/item_edges.parquet
```

Nếu chỉ muốn so sánh với pipeline cũ thì mới cần `data/custom/outfits/generated_outfits.parquet`.

---

## 4. Schema — `catalog_metadata.parquet`

Mỗi row là 1 item, tương thích với `ItemRecord` trong `src/outfitmatch/kb/schema.py`.

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `item_id` | string | ✅ | Stable ID dạng `item_custom_NNNNN` |
| `category` | string | ✅ | `top`, `bottom`, `dress`, `outerwear`, `shoes`, `bag`, `accessory` |
| `source_product_type` | string | optional | Nhãn gốc của store trước khi map |
| `gender` | string | ✅ | `men`, `women`, `unisex`, `kid` |
| `formality` | string | ✅ | `athletic`, `casual`, `smart_casual`, `formal` |
| `image_path` | string | ✅ | Repo-relative path |
| `title_vi` | string | ✅ | Tên sản phẩm từ store |
| `desc_vi` | string | optional | Mô tả sản phẩm |
| `colors` | JSON string list | optional | Ví dụ `["trắng", "navy"]` |
| `collected_date` | date/string | ✅ | Ngày crawl/collect |
| `collector` | string | ✅ | Người hoặc job collect |

---

## 5. Schema — `item_store_links.parquet`

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `item_id` | string | ✅ | FK sang `catalog_metadata.item_id` |
| `store_id` | string | ✅ | Ví dụ `yody_vn`, `canifa_vn` |
| `source_product_id` | string | ✅ | Upstream product id / handle |
| `product_url` | string | ✅ | URL mua hàng, absolute `https://...` |
| `price_vnd` | int | ✅ | Giá VND chuẩn hóa |
| `sale_price_vnd` | int/null | optional | Giá sale nếu có |
| `sku` | string/null | optional | SKU/variant |
| `in_stock` | bool | ✅ | Item còn hàng |
| `available_sizes` | JSON string list | optional | Toàn bộ size option đọc được |
| `sizes_in_stock` | JSON string list | optional | Các size còn hàng |

---

## 6. Schema — `item_edges.parquet` (primary KB artifact)

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `src_id` | string | ✅ | item nguồn |
| `dst_id` | string | ✅ | item đích |
| `src_category` | string | ✅ | category nguồn |
| `dst_category` | string | ✅ | category đích |
| `weight` | float | ✅ | compatibility weight |

Đây là **artifact retrieval chính** của dự án. `src/outfitmatch/kb/graph_store.py`
đọc file này để dựng `OutfitGraph`, còn `retrieval.py` dùng graph + Qdrant `items`
để seed-filter rồi ráp outfit động.

---

## 7. Setup cho coworker

Từ repo root:

```powershell
uv sync --group dev
```

Copy/unzip dataset artifact vào đúng folder `data/`, sau đó validate:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.quality
```

Build graph baseline:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80
```

Smoke grade graph:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office
```

Legacy comparison only:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60
```

---

## 8. Scrape/update catalog

Smoke test không ghi file:

```powershell
uv run python -m scripts.data.scrape.run --limit 20 --no-images --dry-run
```

Crawl active stores:

```powershell
uv run python -m scripts.data.scrape.run
```

Crawl một store:

```powershell
uv run python -m scripts.data.scrape.run --store yody_vn
```

Active adapter-backed stores hiện tại:

| Store | Adapter |
|---|---|
| `yody_vn` | `sitemap_html` |
| `canifa_vn` | `sitemap_html` |
| `aristino_vn` | `sitemap_product_json` |
| `huelleyrose` | `shopify_like` |
| `dirtycoins` | `shopify_like` |
| `rubies` | `shopify_like` |

---

## 9. Cách đóng gói để share

Khuyến nghị tạo archive chỉ chứa artifact cần thiết:

```powershell
Compress-Archive -Path `
  data/custom/catalog/catalog_metadata.parquet,`
  data/custom/catalog/item_store_links.parquet,`
  data/custom/catalog/scrape_manifest.json,`
  data/custom/catalog/images,`
  data/custom/graph/item_edges.parquet,`
  data/cache/store_registry.db `
  -DestinationPath outfitmatch_graph_dataset_snapshot.zip
```

Nếu muốn coworker debug/replay scraper, share thêm:

```text
data/cache/raw/
```

Nếu cần so sánh với pipeline cũ, share thêm:

```text
data/custom/outfits/generated_outfits.parquet
```

---

## 10. Data governance / lưu ý khi dùng

1. **Chỉ dùng store VN/local purchasable data cho serving/recommendation.**
2. **Giá/stock có thể stale.** Kiểm tra `collected_date` trước demo.
3. **Không đổi enum value.** `category`, `gender`, `formality`, `price_tier`, style/occasion phải theo `src/outfitmatch/vocab.py`.
4. **Không commit full dataset.** Catalog/images/cache đi qua artifact share riêng; graph edge baseline có thể track trong repo.
5. **Ảnh là local path.** `image_path` phải trỏ tới file trong repo.
6. **Graph KB là canonical.** `generated_outfits.parquet` và Qdrant `outfits` chỉ còn là legacy comparison path.
7. **Ưu tiên `source_product_type` hơn title parsing** khi map category nếu store có taxonomy tốt.

---

## 11. Liên quan trong repo

| File | Vai trò |
|---|---|
| `docs/datasets/STORE_CATALOG_VN.md` | Schema catalog/store registry chi tiết |
| `docs/PROJECT_STRUCTURE.md` | Cấu trúc repo hiện tại |
| `scripts/data/scrape/README.md` | Hướng dẫn scraper |
| `scripts/data/scrape/quality.py` | Validator catalog |
| `scripts/data/kb/build_graph.py` | CLI build graph KB chính |
| `scripts/data/kb/eval_graph.py` | CLI grade/ablate graph KB |
| `scripts/data/kb/generate_outfits.py` | Legacy materialized comparison CLI |
| `src/outfitmatch/kb/catalog.py` | Load catalog Parquet thành `ItemRecord` |
| `src/outfitmatch/kb/graph.py` | Build sparse compatibility graph |
| `src/outfitmatch/kb/graph_store.py` | Persist/load `item_edges.parquet` + index Qdrant `items` |
| `src/outfitmatch/kb/traversal.py` | Assemble outfit động từ seed item |
| `src/outfitmatch/retrieval.py` | Seed filter + traversal + post-filter |
| `src/outfitmatch/kb/qdrant_index.py` | Legacy Qdrant `outfits` collection |
| `src/outfitmatch/kb/schema.py` | Canonical `ItemRecord` / `OutfitRecord` |
