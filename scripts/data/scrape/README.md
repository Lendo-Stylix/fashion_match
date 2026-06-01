# VN Catalog Scraper

Offline pipeline that fills `data/custom/catalog/` and `data/cache/store_registry.db`
according to `docs/datasets/STORE_CATALOG_VN.md`.

## What it produces

| Path | Content |
|---|---|
| `data/cache/store_registry.db` | SQLite — `stores` table seeded from `scripts/data/scrape/config.py` |
| `data/cache/raw/<store_id>/products_page_NN.json` | Raw `/products.json` responses (replayable) |
| `data/custom/catalog/catalog_metadata.parquet` | One row per item (`ItemRecord`-compatible) |
| `data/custom/catalog/item_store_links.parquet` | item ↔ store mapping with price/SKU/stock + available_sizes |
| `data/custom/catalog/images/item_custom_NNNNN.jpg` | Primary product image, local copy |

Schema is the contract published in `docs/datasets/STORE_CATALOG_VN.md` §4. All
enum-typed fields (`category`, `price_tier`, `style_tags`) flow through
`src/outfitmatch/vocab.py` — no stray values can leak into the KB.

## Supported platforms

* **Shopify `/products.json`** (`scripts/data/scrape/shopify.py`) — Huelley Rose,
  Dirty Coins, Rubies.
* **Sitemap + per-product JSON** (`scripts/data/scrape/sitemap.py`) — Aristino
  (`/sitemap_products_*.xml` → `/products/<handle>.json`).
* **Sitemap + HTML fallback** (`scripts/data/scrape/sitemap.py`) — YODY, Canifa
  (product URLs from sitemap, title/image from sitemap/OG meta, price from
  embedded variant JSON or display-price regex).
* **Skipped (no adapter yet)** — Coolmate, IVY moda, Routine, GUMAC, JUNO,
  Vascara, Elise, Fancì Club, LSOUL, Beuter, Kilomet 109, AEIE, Hades,
  Levents, Dear José. These are custom/Cloudflare/Next.js/WooCommerce-like
  sites with no public `/products.json`; collect manually or add a dedicated
  API/browser adapter later.

## Usage

```bash
# One-off: seed the SQLite registry only
uv run python -m scripts.data.scrape.build_registry

# Smoke test (50 items per store, no image downloads, all active stores)
uv run python -m scripts.data.scrape.run --limit 50 --no-images --dry-run

# Single store, full crawl
uv run python -m scripts.data.scrape.run --store yody_vn

# Resume after a crash — raw cache reused, parquet appended idempotently
uv run python -m scripts.data.scrape.run
```

Flags:

| Flag | Effect |
|---|---|
| `--store ID` | Restrict to one store (repeatable). Default: all active. |
| `--limit N` | Cap items per store after fetch — useful for smoke tests. |
| `--no-images` | Skip image download (use with `--dry-run`, or rows will point at missing local files). |
| `--dry-run` | Fetch + normalize only; do not write parquet/images. |
| `--offline` | Reserved for future use; currently raw cache is always consulted first. |
| `--collector NAME` | Set the `collector` field written into `catalog_metadata.parquet`. |
| `--batch-size N` | Items per quality-gated batch. Default: 250. |
| `--min-yield R` | Minimum normalized/raw ratio before quarantining a whole store. |
| `--no-gate` | Disable the batch quality gate and write directly to parquet. |
| `--rescrape-failed` | Re-run only store/chunks marked quality-failed in `scrape_manifest.json`. |
| `--skip-registry` | Don't re-seed `store_registry.db`. |
| `-v` / `--verbose` | DEBUG-level logging. |

## Batched scrape with quality gate

Each store is split into `--batch-size` chunks. Every chunk passes the in-memory
quality gate (`quality.check_frames`) **before** it is merged into the main
catalog parquet.

- passing batch -> promoted into `catalog_metadata.parquet` / `item_store_links.parquet`
- quality-failed batch -> written into `data/custom/catalog/quarantine/<store>__<chunk>/`
- all outcomes -> tracked in `data/custom/catalog/scrape_manifest.json`

```bash
# scrape with gate enabled (default)
uv run python -m scripts.data.scrape.run --batch-size 250

# retry only quality-failed batches from the manifest
uv run python -m scripts.data.scrape.run --rescrape-failed

# legacy direct-write mode
uv run python -m scripts.data.scrape.run --no-gate
```

A batch is quarantined when the gate finds **data-quality problems** (invalid
category, missing title, bad colors JSON, missing image, broken join, invalid
store/url/price, etc.) or when a store's normalize/raw yield falls below
`--min-yield`.

## How items are categorised

Category comes from **two cooperating signals** (see
`scripts/data/scrape/store_category_map.py::resolve_category`):

1. **Store-native `product_type`** (authoritative) — each store ships its own
   taxonomy, mapped to our enum via `store_category_map.py`. This is more
   reliable than the title and is the only thing that can:
   - separate `váy` (skirt → **bottom**) from `đầm` (dress) — e.g. rubies SKU
     codes `VQ`/`VD`/`VN` are skirts, `DD`/`DN` are dresses;
   - **drop out-of-scope SKUs**: underwear (`Quần Briefs`, `INNERWEAR`, `bra`),
     phone cases, perfume, gift vouchers, keychains, 2-piece sets
     (`Bộ Suits`, `clothing set`).
2. **Title-token categoriser** (`category_map.py::categorize`) — fallback when
   the store gives no `product_type` (YODY, Canifa). Token-based, not substring
   (so "Capri"≠cap, "Baggy"≠bag, "Phối Túi"≠bag). It also drops underwear
   titles (`Quần lót`, `briefs`, `boxer`) the store didn't tag.

Resolution returns one of `top | bottom | dress | outerwear | shoes | bag |
accessory` (see `vocab.ITEM_CATEGORY`) or **drops the item**.

The raw store value is persisted in the `source_product_type` column of
`catalog_metadata.parquet` for traceability.

## Wearer gender

`scripts/data/scrape/gender_map.py::infer_gender` tags each item `men | women |
unisex | kid` so outfit generation never pairs a men's top with a women's skirt.
Signals (decreasing reliability): explicit title token (`nam`/`nữ`/`bé trai`/
`unisex`/`men`/`women`/`kid`) → single-gender brand default (aristino=men,
rubies/huelleyrose=women, dirtycoins=unisex) → category prior (`dress`→women).
`unisex` is the safe fallback and combines with both. Stored in the `gender`
column; outfit generation defaults to adult-only (`men/women/unisex`).

## Item sizes

`normalize.py` also extracts variant size labels into `item_store_links.parquet`:

- `available_sizes`: every size label seen across variants, upper-cased
- `sizes_in_stock`: subset where `variant.available == True`

These fields stay at the item/store-link layer; generated outfits remain
size-agnostic templates. Runtime personalization (`src/outfitmatch/quiz/sizing.py`)
uses them to suggest sizes for alpha-size categories only.

### Re-tagging an existing catalog

If either mapper changes, re-tag in place — no re-crawl needed. The tool reads
store `product_type` back from the **offline raw HTTP cache**:

```bash
uv run python -m scripts.data.scrape.retag_catalog --dry-run
uv run python -m scripts.data.scrape.retag_catalog
```

It re-classifies every row (store tag first, title fallback), drops rows that
no longer map to a valid category, and prunes orphan rows from
`item_store_links.parquet`. Idempotent.

Style + occasion + body-fit tagging is **not** done here — that's the Gemini
Flash tagging step in `src/outfitmatch/kb/tagging.py` (Sprint 3–4). This
scraper only produces clean items with valid `category` and a working image.

## Polite-scraping policy

* Single-connection client, 1–3 s random sleep between page fetches, 0.3–0.8 s
  between image downloads.
* Exponential backoff (cap = 4 attempts) on 429 / 5xx.
* All raw JSON cached under `data/cache/raw/` — re-running with the cache
  intact never hits the origin again.
* Max 40 pages × 250 items per store by default (`StoreConfig.max_pages`).

## Adding a new store

1. Append a `StoreConfig` row to `scripts/data/scrape/config.py`.
2. Pick the narrowest working adapter:
   * `platform="shopify_like"` for public `/products.json` feeds.
   * `platform="sitemap_product_json"` when sitemap product URLs support
     `<product-url>.json`.
   * `platform="sitemap_html"` when sitemap product pages expose OG metadata
     and inline/displayed prices.
3. Otherwise set `platform="skip"` and add a follow-up to write a dedicated
   adapter (mirror `shopify.py`'s `RawProduct` interface).
4. `uv run python -m scripts.data.scrape.build_registry` to refresh the SQLite seed.

## Tests

```
tests/data/scrape/test_category_map.py   # keyword heuristic
tests/data/scrape/test_normalize.py      # raw → NormalizedItem mapping + frame builders
tests/data/scrape/test_quality.py        # parquet + in-memory data-quality checks
tests/data/scrape/test_batch_gate.py     # chunking / gate / quarantine
tests/data/scrape/test_manifest.py      # manifest round-trip + failed-batch query
tests/data/scrape/test_run_gate.py      # gate-and-promote orchestration
```

Run: `uv run pytest tests/data/scrape -v`.
