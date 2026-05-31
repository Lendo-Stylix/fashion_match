# OutfitMatch Dataset README

README này dùng để share dataset giữa các thành viên team. Dataset **không commit lên Git** vì có ảnh, cache, Parquet lớn và dữ liệu giá có thể stale. Khi share, gửi folder `data/` hoặc các file được liệt kê ở dưới qua Google Drive/OneDrive/DVC artifact.

---

## 1. Dataset gồm những gì?

OutfitMatch hiện có 2 nhóm data chính phục vụ Knowledge Base (KB):

| Nhóm | Mục đích | File/thư mục chính |
|---|---|---|
| **VN Store Catalog** | Item thời trang từ store Việt Nam/local VN, có giá và link mua được | `data/custom/catalog/catalog_metadata.parquet`, `data/custom/catalog/item_store_links.parquet`, `data/custom/catalog/images/` |
| **Generated Outfit KB** | Tổ hợp outfit hợp lệ để index/recommend | `data/custom/outfits/generated_outfits.parquet` |

Các file phụ trợ:

| Path | Nội dung |
|---|---|
| `data/cache/store_registry.db` | SQLite registry store/brand được scraper seed từ `scripts/data/scrape/config.py` |
| `data/cache/raw/<store_id>/` | Raw HTTP/text cache để replay parse mà không crawl lại store |
| `link_web.txt` | Danh sách website/store đã khảo sát |

> Lưu ý: `data/custom/**/*.parquet`, `data/custom/catalog/images/*`, `data/cache/` đã được `.gitignore`. Muốn coworker có dataset thì phải share artifact riêng, không chỉ pull Git.

---

## 2. Current snapshot

Snapshot gần nhất đã validate:

### VN Store Catalog

- `5845` catalog items (token + store-tag categoriser dropped out-of-scope SKUs: underwear, swimwear, phone cases, perfume, gift vouchers, 2-piece sets)
- `5845` item-store links
- `0` hard errors
- `1` warning: `552` item thiếu `desc_vi`; chấp nhận được vì bước tagging sau có thể dựa vào title/image

Store distribution:

| Store | Items |
|---|---:|
| `yody_vn` | 2227 |
| `aristino_vn` | 1472 |
| `canifa_vn` | 1190 |
| `rubies` | 467 |
| `huelleyrose` | 302 |
| `dirtycoins` | 187 |

Category distribution (store-tag first, title fallback):

| Category | Items |
|---|---:|
| `top` | 3004 |
| `bottom` | 1531 |
| `outerwear` | 500 |
| `dress` | 314 |
| `accessory` | 232 |
| `bag` | 140 |
| `shoes` | 124 |

> Cột `source_product_type` trong `catalog_metadata.parquet` lưu nhãn gốc của store
> (vd. `T-SHIRTS`, `Quần Âu`, `VQ`) để truy vết nguồn phân loại.

### Generated Outfit KB

- `1000` generated outfits
- `1000` unique item combinations
- `0` invalid category-rule combinations
- Compatibility score range: `0.650–0.980`
- Method mix: `700` FITB-beam / `300` random-scored
- Price-tier mix, tuned for Vietnamese mainstream users:
  - `budget`: `200` outfits (`20%`)
  - `mid`: `500` outfits (`50%`)
  - `premium`: `300` outfits (`30%`)

---

## 3. Folder layout coworker cần có

Sau khi unzip/copy artifact, project nên có layout như sau:

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
    │   └── images/
    │       ├── item_custom_00001.jpg
    │       └── ...
    └── outfits/
        └── generated_outfits.parquet
```

Minimum files để chạy KB generation/evaluation:

```text
data/custom/catalog/catalog_metadata.parquet
data/custom/catalog/item_store_links.parquet
data/custom/catalog/images/
data/custom/outfits/generated_outfits.parquet
```

Nếu chỉ muốn regenerate outfits từ catalog thì `generated_outfits.parquet` không bắt buộc; có thể tạo lại bằng command ở §7.

---

## 4. Schema — `catalog_metadata.parquet`

Mỗi row là 1 item, tương thích với `ItemRecord` trong `src/outfitmatch/kb/schema.py`.

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `item_id` | string | ✅ | Stable ID dạng `item_custom_NNNNN` |
| `category` | string | ✅ | `top`, `bottom`, `dress`, `outerwear`, `shoes`, `bag`, `accessory` |
| `source_product_type` | string | optional | Nhãn gốc của store trước khi map (vd. `T-SHIRTS`, `Quần Âu`, `VQ`); rỗng nếu store không cung cấp |
| `gender` | string | ✅ | Giới tính người mặc: `men`, `women`, `unisex`, `kid` (suy ra từ title + brand + category) |
| `image_path` | string | ✅ | Repo-relative path, ví dụ `data/custom/catalog/images/item_custom_00001.jpg` |
| `title_vi` | string | ✅ | Tên sản phẩm từ store |
| `desc_vi` | string | optional | Mô tả sản phẩm; có thể rỗng |
| `colors` | JSON string list | optional | Ví dụ `["trắng", "navy"]` |
| `collected_date` | date/string | ✅ | Ngày crawl/collect |
| `collector` | string | ✅ | Người hoặc job collect |

Ví dụ đọc nhanh:

```python
import pandas as pd

catalog = pd.read_parquet("data/custom/catalog/catalog_metadata.parquet")
print(catalog.head())
print(catalog["category"].value_counts())
```

---

## 5. Schema — `item_store_links.parquet`

Mỗi row là link mua + giá cho một item ở một store.

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `item_id` | string | ✅ | FK sang `catalog_metadata.item_id` |
| `store_id` | string | ✅ | Ví dụ `yody_vn`, `canifa_vn` |
| `source_product_id` | string | ✅ | ID/handle sản phẩm gốc, dùng để giữ stable `item_id` khi re-scrape |
| `product_url` | string | ✅ | URL mua hàng, phải absolute `https://...` |
| `price_vnd` | int | ✅ | Giá VND chuẩn hóa |
| `sale_price_vnd` | int/null | optional | Giá sale nếu có |
| `sku` | string/null | optional | SKU/variant |
| `in_stock` | bool | ✅ | Chỉ item in-stock được dùng để build outfit |

---

## 6. Schema — `generated_outfits.parquet`

Mỗi row là 1 outfit generated, compact để dễ share/index.

| Column | Type | Required | Ghi chú |
|---|---|---:|---|
| `outfit_id` | string | ✅ | `OF_00001`, `OF_00002`, ... |
| `schema_version` | string | ✅ | Hiện tại là `3.1` |
| `gender` | string | ✅ | Giới tính outfit: `men`, `women`, `unisex`, `kid`. Mọi item trong outfit luôn cùng giới (unisex ghép được cả hai) |
| `item_ids` | JSON string list | ✅ | Danh sách item trong outfit |
| `categories` | JSON string list | ✅ | Category tương ứng với item |
| `compatibility_score` | float | ✅ | Score sau re-score deterministic baseline |
| `price_total_vnd` | int | ✅ | Tổng giá outfit |
| `price_tier` | string | ✅ | `budget`, `mid`, `premium` |
| `has_vn_store` | bool | ✅ | Hiện tại luôn `true` cho catalog này |
| `gen_method` | string | ✅ | `fitb_beam` hoặc `random_scored` |

Luật outfit hợp lệ:

1. `top + bottom + shoes`
2. `dress + shoes`
3. Có thể thêm optional add-ons: `outerwear`, `bag`, `accessory`

Ví dụ đọc và kiểm tra:

```python
import json
import pandas as pd

outfits = pd.read_parquet("data/custom/outfits/generated_outfits.parquet")
print(outfits["price_tier"].value_counts())
print(outfits["gen_method"].value_counts())

valid = outfits["categories"].map(
    lambda raw: {"top", "bottom", "shoes"} <= set(json.loads(raw))
    or {"dress", "shoes"} <= set(json.loads(raw))
)
print("invalid outfits:", int((~valid).sum()))
```

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

Expected summary gần nhất:

```text
items: 5845
links: 5845
errors: 0
warnings: 1
```

Regenerate outfit KB từ catalog:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60
```

Expected outfit report:

```text
outfits: 1000
price_tiers: {"budget": 200, "mid": 500, "premium": 300}
gen_methods: {"fitb_beam": 700, "random_scored": 300}
unique_combos: 1000
invalid_rules: 0
max_price_tier_deviation: 0.0000
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

Các store JS-heavy/blocked/custom hiện để `platform="skip"` trong `scripts/data/scrape/config.py` và cần adapter riêng nếu muốn mở rộng coverage.

---

## 9. Cách đóng gói để share

Khuyến nghị tạo archive chỉ chứa artifact cần thiết:

```powershell
Compress-Archive -Path `
  data/custom/catalog/catalog_metadata.parquet,`
  data/custom/catalog/item_store_links.parquet,`
  data/custom/catalog/images,`
  data/custom/outfits/generated_outfits.parquet,`
  data/cache/store_registry.db `
  -DestinationPath outfitmatch_dataset_snapshot.zip
```

Nếu muốn coworker debug/replay scraper, share thêm:

```text
data/cache/raw/
```

Không cần share:

```text
.venv/
.ruff_cache/
.pytest_cache/
.mypy_cache/
wandb/
```

---

## 10. Data governance / lưu ý khi dùng

1. **Chỉ dùng store VN/local purchasable data cho serving/recommendation.** Không dùng giá/store làm training signal cho OutfitTransformer hoặc Qwen LoRA.
2. **Giá có thể stale.** Nếu `collected_date` quá cũ hoặc store đổi giá, chạy lại scraper hoặc validate thủ công trước demo.
3. **Không đổi enum value.** `category`, `price_tier`, style/occasion/body fields phải theo `src/outfitmatch/vocab.py`.
4. **Không commit dataset.** Git chỉ track code, README, schema/docs. Dataset đi qua artifact share riêng.
5. **Ảnh là local path.** `image_path` phải trỏ tới file trong repo, không dùng hotlink remote làm input cho KB.
6. **Generated Outfit KB hiện là prototype deterministic.** Metadata tagging đầy đủ (`occasion`, `style`, `body_shapes_fit`, `season`, explanation) sẽ được bổ sung ở bước Gemini tagging/Qdrant indexing sau.

---

## 11. Liên quan trong repo

| File | Vai trò |
|---|---|
| `docs/datasets/STORE_CATALOG_VN.md` | Schema catalog/store registry chi tiết |
| `docs/PROJECT_STRUCTURE.md` | Cấu trúc repo hiện tại |
| `scripts/data/scrape/README.md` | Hướng dẫn scraper |
| `scripts/data/scrape/quality.py` | Validator catalog |
| `scripts/data/kb/generate_outfits.py` | CLI build outfit KB |
| `src/outfitmatch/kb/catalog.py` | Load catalog Parquet thành `ItemRecord` |
| `src/outfitmatch/kb/build_outfits.py` | Generate + balance outfit records |
| `src/outfitmatch/kb/evaluation.py` | Summary/evaluation cho generated outfit KB |
| `src/outfitmatch/kb/schema.py` | Canonical `ItemRecord` / `OutfitRecord` |
