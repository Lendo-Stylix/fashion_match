"""CLI orchestrator — `python -m scripts.data.scrape.run [--store yody_vn ...] [--no-images]`.

Pipeline per store:
    1. shopify.fetch_products  → list[RawProduct]   (uses raw cache)
    2. normalize.normalize_products → list[NormalizedItem]
    3. download_images.download_all → drop items whose images failed
    4. normalize.write_frames  → append into parquet
    5. build_registry.build_registry once at end

Usage examples:
    uv run python -m scripts.data.scrape.run                    # all active stores
    uv run python -m scripts.data.scrape.run --store yody_vn     # one store
    uv run python -m scripts.data.scrape.run --limit 50          # cap items/store (smoke test)
    uv run python -m scripts.data.scrape.run --no-images         # parquet only, skip downloads
    uv run python -m scripts.data.scrape.run --offline           # use raw cache only
"""

from __future__ import annotations

import argparse
import logging
import sys

from .base import new_client
from .build_registry import build_registry
from .config import STORES_BY_ID, StoreConfig, active_stores
from .download_images import download_all
from .normalize import next_index, normalize_products, write_frames
from .shopify import fetch_products
from .sitemap import fetch_products_via_html, fetch_products_via_product_json

logger = logging.getLogger("scrape")


def _select_stores(names: list[str] | None) -> list[StoreConfig]:
    if not names:
        return active_stores()
    out: list[StoreConfig] = []
    for n in names:
        s = STORES_BY_ID.get(n)
        if s is None:
            logger.error("unknown store_id %s (see config.STORES)", n)
            sys.exit(2)
        if s.platform == "skip":
            logger.warning("store %s is marked skip — no adapter", n)
            continue
        out.append(s)
    return out


def run_store(
    store: StoreConfig,
    *,
    use_cache: bool,
    limit: int | None,
    download: bool,
    collector: str,
    offline: bool = False,
    dry_run: bool = False,
) -> int:
    logger.info("───── %s (%s) ─────", store.store_id, store.platform)
    with new_client() as client:
        if store.platform == "shopify_like":
            raws = fetch_products(
                client, store, use_cache=use_cache, offline=offline, product_limit=limit
            )
        elif store.platform == "sitemap_product_json":
            raws = fetch_products_via_product_json(
                client, store, use_cache=use_cache, offline=offline, product_limit=limit
            )
        elif store.platform == "sitemap_html":
            raws = fetch_products_via_html(
                client, store, use_cache=use_cache, offline=offline, product_limit=limit
            )
        else:
            logger.warning("[%s] unsupported platform=%s", store.store_id, store.platform)
            return 0
        items = normalize_products(raws, store, collector=collector, start_index=next_index())
        if not items:
            logger.warning("[%s] zero items after normalize", store.store_id)
            return 0

        if dry_run:
            logger.info(
                "[%s] dry-run: %d normalized items, not writing parquet/images",
                store.store_id,
                len(items),
            )
            return len(items)

        if download:
            ok_ids = download_all(items, client=client)
            kept = [it for it in items if it.item_id in ok_ids]
            dropped = len(items) - len(kept)
            if dropped:
                logger.warning("[%s] dropped %d items (image fail)", store.store_id, dropped)
            items = kept
        if not items:
            return 0
        write_frames(items)
        return len(items)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OutfitMatch VN catalog scraper")
    p.add_argument("--store", action="append", help="store_id; repeatable. Default: all active.")
    p.add_argument("--limit", type=int, default=None, help="Cap items per store (smoke test)")
    p.add_argument(
        "--offline",
        action="store_true",
        help="Use only raw cache, skip every network fetch (errors if cache missing)",
    )
    p.add_argument("--no-images", action="store_true", help="Skip image download")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + normalize only; do not write parquet/images",
    )
    p.add_argument("--collector", default="scraper", help="Tag for catalog_metadata.collector")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--skip-registry", action="store_true", help="Don't (re)seed store_registry.db")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if not args.skip_registry:
        build_registry()

    stores = _select_stores(args.store)
    total = 0
    summary: list[tuple[str, int]] = []
    for s in stores:
        n = run_store(
            s,
            use_cache=True,  # raw cache is always consulted first; see fetch_json
            limit=args.limit,
            download=not args.no_images,
            collector=args.collector,
            offline=args.offline,
            dry_run=args.dry_run,
        )
        total += n
        summary.append((s.store_id, n))
    logger.info("══════ done. total items kept: %d ══════", total)
    for sid, n in summary:
        logger.info("  %-15s %5d", sid, n)
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
