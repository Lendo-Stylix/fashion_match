# Quick start — VN catalog scraper

## Prerequisites
- Project deps installed: `uv sync`
- A working network connection
- `uv` on `PATH`

## 60-second smoke test (no image downloads)

```powershell
# From repo root, in PowerShell or cmd
uv run python -m scripts.data.scrape.run --store yody_vn --limit 20 --no-images --dry-run
```

Expected output (≈30–60 s, depends on network):
```
scrape :: ───── yody_vn (sitemap_html) ─────
scripts.data.scrape.sitemap :: [yody_vn] sitemap_html yielded 20 products
scrape :: [yody_vn] dry-run: 20 normalized items, not writing parquet/images
scrape :: ══════ done. total items kept: 20 ══════
```

Because this is a dry-run, parquet/image files are not modified. To inspect
persisted output, run a real crawl (without `--dry-run`) and then read
`data/custom/catalog/catalog_metadata.parquet`.

## Full crawl, single store
```powershell
uv run python -m scripts.data.scrape.run --store yody_vn
```

Currently active adapters: `yody_vn`, `canifa_vn`, `aristino_vn`,
`huelleyrose`, `dirtycoins`, `rubies`.

## Full crawl, all active adapter-backed stores
```powershell
uv run python -m scripts.data.scrape.run
# active now: YODY, Canifa, Aristino, Huelley Rose, Dirty Coins, Rubies
```

## Re-run after a crash
Raw responses are cached under `data/cache/raw/<store_id>/`. Re-running
`scripts.data.scrape.run` will reuse them — no duplicate item_ids, no refetch.

```powershell
uv run python -m scripts.data.scrape.run     # resumes seamlessly
```

To force refetch a store, delete its cache:
```powershell
Remove-Item -Recurse data\cache\raw\yody_vn
uv run python -m scripts.data.scrape.run --store yody_vn
```

## Run the unit tests
```powershell
uv run pytest tests/data/scrape -v
```

## When you're done
- `data/cache/store_registry.db` — SQLite, queryable with any SQLite viewer.
- `data/custom/catalog/catalog_metadata.parquet` — `ItemRecord`-compatible.
- `data/custom/catalog/item_store_links.parquet` — item ↔ store mapping, including `available_sizes` and `sizes_in_stock`.
- `data/custom/catalog/images/item_custom_*.jpg|png|webp` — image files.

Next step is **Tầng 1 graph KB pipeline** (`src/outfitmatch/kb/`): load these
parquets as `ItemRecord`s (`catalog.py`), write semantic item tags with
`tagging.py` / `scripts.data.kb.tag_items`, build the sparse compatibility graph
with `graph.py` / `scripts.data.kb.build_graph`, then serve retrieval through
`src/outfitmatch/retrieval.py`. Materialized outfit generation remains only a
legacy comparison path.
