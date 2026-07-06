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

Dataset snapshot for the **OutfitMatch** project (body & occasion-aware fashion recommender).

This repository mirrors the **contents of the project's local `data/` folder** — the
*dataset*, not the codebase. To use it inside the project, copy this repo's files into:

```text
data/
```

> Snapshot was cleaned & restructured on 2026-07. The catalog/graph audit numbers
> below reflect the 2026-06 tagging review (the most recent full re-tag).

## Scope — what belongs vs. out of scope

| In this dataset repo | NOT here (kept local only — gitignored) |
|---|---|
| `custom/` catalog, graph KB, legacy outfits, body images | Stylist **model checkpoints / LoRA adapters** |
| `cache/store_registry.db` + `cache/raw/<store>/` (scrape provenance) | `cache/hf/`, `cache/turboquant/` downloaded models |
| `reports/` quality audits (CSV/JSON/MD) | Model-eval & inference scratch (`cache/*eval*`, `cache/probe_*.jsonl`, `cache/tagging_*.log`) |
| `stylist/` conversation training corpus (selected JSONL/CSV) | Kaggle run infra, wheelhouses, raw training logs |

Removed on 2026-07 cleanup: stale empty skeletons `raw/` (except `raw/occasion_cache/*.db`,
kept on-disk as a local tagger cache, no longer synced), `processed/`, the unused
DVC pointer `raw.dvc`, and the throwaway `tmp_kaggle_output_probe/`.

## Current validated snapshot (2026-06 re-tag)

### Catalog

- **5618** catalog items
- **5618** item-store links
- **0** invalid rows in the latest item-tag audit
- **0** high-severity semantic flags in the latest item-tag audit
- **556** items have empty `desc_vi` (accepted warning)
- Categorization rule: **store-native `product_type` first, title-token fallback**
- Semantic tagging coverage: **5618 / 5618** non-empty rows
- Color tagging coverage: **5618 / 5618** non-empty rows
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

```text
cache/
  store_registry.db          # scrape registry (store id -> adapter) — enables rescrape
  raw/<store_id>/             # raw HTTP/HTML scrape cache per store (reproducibility)
custom/
  catalog/
    catalog_metadata.parquet
    item_store_links.parquet
    scrape_manifest.json
    images/                   # 5618 item thumbnails
  graph/
    item_edges.parquet        # primary compatibility graph KB
  outfits/
    generated_outfits.parquet   # legacy/comparison only
  body/
    images/                   # (placeholder) body-condition images
reports/                     # quality audit reports (full set incl. CSV)
  tagging_quality/            # item-tag audit (CSV/MD/JSON)
  outfit_tagging_quality/     # outfit-tag audit (CSV/JSON)
stylist/                     # stylist conversation training corpus (selected JSONL/CSV)
  fine_tune/
    runs/...
    stylist_knowledge/
```

## Minimum files for graph retrieval / eval

```text
custom/catalog/catalog_metadata.parquet
custom/catalog/item_store_links.parquet
custom/catalog/images/
custom/graph/item_edges.parquet
```

`cache/store_registry.db` + `cache/raw/<store>/` are optional but recommended for
reproducible rescrape. `reports/` and `stylist/` are documentation/training
artifacts and are not required for retrieval.

## Stylist conversation corpus (`stylist/`)

Conversation data used to LoRA-fine-tune the Qwen3-VL stylist. The heavy Kaggle
run infra, checkpoints, and wheelhouses are local-only and intentionally **not**
synced here; only the actual SFT corpus is published.

### Distilled fine-tune dataset (canonical, retrieval-grounded)

```text
stylist/fine_tune/runs/stylist_grounded_v2/
  final_bundle_gptoss_2800_merged_core8800/
    train.jsonl     # 11256 examples (~14.5 MB)
    eval.jsonl      #   344 examples
    manifest.json   # task/source counts
  merged_source_gptoss_2800_core8800/
    manifest.json   # records the 2 source files merged
```

This is the final SFT bundle. It merges a retrieval-grounded GPT-OSS-teacher
distillation (`gptoss_2800_all_accepted.jsonl`, 2800 grounded dialogues) with
the knowledge core (`stylist_distilled_qwen35_under10k/train.jsonl`, 8800 rows)
into **11600 total examples** stratified to 11256 train / 344 eval. Task
breakdown (from `manifest.json`): 7200 `stylist_knowledge` + 2800
`grounded_generated` (900 tool_calling_grounded, 700 recommend_explain_grounded,
350 ask_missing_info_grounded, 300 body_fit_grounded, 250 no_result_or_relax,
150 polite_decline_anti_hallucination, 150 multi_turn_grounded) + 1600
`behavioral_synthetic` (tool_calling, ask_missing_info, recommend_explain,
multi_turn, polite_decline, body_analysis, edge_case). Every tool-call row uses
the canonical `<tool_call>...<tool_call>` / `...` wire
format locked in `src/outfitmatch/stylist/tools.py` (enum args from `vocab.py`).

### Earlier distilled corpora (kept for traceability)

- `stylist_distilled_qwen35_under10k/` — pre-ground distilled corpus (~10k knowledge rows) reused as the knowledge core above.
- `stylist_distilled_behavioral/` — behavioral / tool-call synthetic seeds.
- `kaggle_qlora_token3_t4_qwen/kaggle_dataset/` — packing set used for one Kaggle QLoRA run.
- `stylist_knowledge/finetuning_data_fashion_knowledge.csv` — raw knowledge source table.

## Reports / quality audits (`reports/`)

Two audit categories, both generated from the catalog/graph snapshot:

- `reports/tagging_quality/` — item-level tag distribution, invalid rows, outliers,
  semantic flags, plus model-comparison review markdown files for the tagging tagger
  selection (Gemma 4 12B TurboQUANT vs Qwen3-VL 8B vs Qwen3.5 9B).
- `reports/outfit_tagging_quality/` — outfit-level tag distributions by core shape /
  gender / gen method / price tier, invalid rows, semantic flags, and the summary
  counts quoted in the snapshot above.

These are present here so the dataset card is self-documenting; they are also the
artifacts referenced by `docs/EXPERIMENT_GUIDE.md` for the 2026-06 tagging review.

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
