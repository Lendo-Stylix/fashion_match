---
language:
- vi
tags:
- fashion
- vietnamese
- outfit-recommendation
- e-commerce
task_categories:
- image-classification
size_categories:
- 1K<n<10K
pretty_name: VN Fashion Data
---

# VN Fashion Data

Dataset snapshot for the OutfitMatch project.

This repository stores the **contents of the local `data/` folder** (not the codebase). To use it inside the project, copy this repo's files into:

```text
data/
```

## Current validated snapshot

### Catalog

- **5618** catalog items
- **5618** item-store links
- **0** invalid rows in the latest item-tag audit
- **0** high-severity semantic flags in the latest item-tag audit
- **556** items have empty `desc_vi` (accepted warning)
- Categorization rule: **store-native `product_type` first, title-token fallback**
- Semantic tagging coverage: **5618 / 5618 non-empty rows**
- Color tagging coverage: **5618 / 5618 non-empty rows**
- Main-garment semantic completeness (`top | bottom | dress | outerwear`): **5004 / 5004**

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

Gender distribution:

| Gender | Items |
|---|---:|
| `men` | 2549 |
| `women` | 1873 |
| `kid` | 696 |
| `unisex` | 500 |

### Graph KB (primary retrieval artifact)

- **4694** adult item nodes (`men | women | unisex`)
- **316559** canonical compatibility edges in `custom/graph/item_edges.parquet`
- Latest audit/eval status:
  - `coherence_violations = 0`
  - `fitb_recall@5(mask shoes) = 1.0000`
  - Shoeless outfits are treated as **valid clothing cores**; missing shoes are tracked as a completion gap rather than an invalid core combo.

### Legacy materialized outfits

- `custom/outfits/generated_outfits.parquet` is retained only for legacy comparison/debug.
- The project's **primary KB path is graph retrieval**, not materialized outfits.
- Latest outfit-tag audit over assembled graph outfits:
  - `total_outfits = 824`
  - `valid_core_outfit_count = 824`
  - `complete_outfit_count = 816`
  - `shoeless_valid_core_count = 8`
  - `high_severity_flag_count = 0`

## Layout

Repo root mirrors the project `data/` folder:

```text
cache/
  store_registry.db
  raw/<store_id>/...
custom/
  catalog/
    catalog_metadata.parquet
    item_store_links.parquet
    images/
  graph/
    item_edges.parquet
  outfits/
    generated_outfits.parquet   # legacy/comparison only
```

## Minimum files for graph retrieval / eval

```text
custom/catalog/catalog_metadata.parquet
custom/catalog/item_store_links.parquet
custom/catalog/images/
custom/graph/item_edges.parquet
```

## Schema highlights

### `custom/catalog/catalog_metadata.parquet`

| Column | Meaning |
|---|---|
| `item_id` | Stable item id: `item_custom_NNNNN` |
| `category` | `top`, `bottom`, `dress`, `outerwear`, `shoes`, `bag`, `accessory` |
| `source_product_type` | Original store taxonomy value before mapping |
| `gender` | `men`, `women`, `unisex`, `kid` |
| `formality` | `athletic`, `casual`, `smart_casual`, `formal` |
| `image_path` | Relative image path |
| `title_vi` | Product title |
| `desc_vi` | Product description |
| `colors` | JSON string list |
| `collected_date` | Collection date |
| `collector` | Collector/job name |

### `custom/catalog/item_store_links.parquet`

| Column | Meaning |
|---|---|
| `item_id` | FK to catalog |
| `store_id` | Store identifier |
| `source_product_id` | Raw source product id |
| `product_url` | Purchase URL |
| `price_vnd` | Normalized VND price |
| `sale_price_vnd` | Optional sale price |
| `sku` | Optional SKU |
| `in_stock` | Stock flag |
| `available_sizes` | JSON string list |
| `sizes_in_stock` | JSON string list |

### `custom/graph/item_edges.parquet`

| Column | Meaning |
|---|---|
| `src_id` | Source item id |
| `dst_id` | Destination item id |
| `src_category` | Source item category |
| `dst_category` | Destination item category |
| `weight` | Compatibility weight |

## Notes

- Out-of-scope SKUs have been removed: underwear, swimwear, phone cases, perfume, gift vouchers, keychains, 2-piece sets.
- `source_product_type` is persisted for traceability.
- The project code that consumes this dataset lives in a separate repository: `fashion_match_project`.
