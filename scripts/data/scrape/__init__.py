"""Catalog scraper for VN fashion stores.

Pipeline:
    1. config.py        — registry of stores + platform classification
    2. base.py          — HTTP client (retry, throttle, raw cache)
    3. shopify.py       — generic Shopify/Haravan /products.json adapter
    4. category_map.py  — heuristic: title/tags → ITEM_CATEGORY enum
    5. normalize.py     — raw JSON → catalog_metadata + item_store_links rows
    6. download_images.py — download item images to data/custom/catalog/images/
    7. build_registry.py — seed data/cache/store_registry.db (SQLite)
    8. run.py           — CLI orchestrator (python -m scripts.data.scrape.run …)

All output paths follow docs/datasets/STORE_CATALOG_VN.md.
"""
