# VN Catalog Scraper

Offline pipeline that fills `data/custom/catalog/` and `data/cache/store_registry.db`
according to `docs/datasets/STORE_CATALOG_VN.md`.

## What it produces

| Path | Content |
|---|---|
| `data/cache/store_registry.db` | SQLite — `stores` table seeded from `scripts/data/scrape/config.py` |
| `data/cache/raw/<store_id>/products_page_NN.json` | Raw `/products.json` responses (replayable) |
| `data/custom/catalog/catalog_metadata.parquet` | One row per item (`ItemRecord`-compatible) |
| `data/custom/catalog/item_store_links.parquet` | item ↔ store mapping with price/SKU/stock |
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
| `--skip-registry` | Don't re-seed `store_registry.db`. |
| `-v` / `--verbose` | DEBUG-level logging. |

## How items are categorised

`scripts/data/scrape/category_map.py` runs a Vietnamese + English keyword heuristic
over `title + product_type + tags`. Order matters: `dress` is matched before
`top` (so "đầm" doesn't end up as a t-shirt), `outerwear` before `top`, etc.
Returns one of `top | bottom | dress | outerwear | shoes | bag | accessory`
(see `vocab.ITEM_CATEGORY`) or **drops the item** when no group hits.

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
tests/data/scrape/test_normalize.py      # raw → NormalizedItem mapping + price guards
```

Run: `uv run pytest tests/data/scrape -v`.
