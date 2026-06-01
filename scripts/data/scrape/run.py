"""CLI orchestrator for the VN catalog scraper.

Pipeline per store:
    1. fetch raw products (uses raw cache when available)
    2. normalize to :class:`NormalizedItem`
    3. split into batches and run per-batch quality gate
    4. promote only passing batches into parquet
    5. quarantine failing batches + update manifest for targeted re-scrape

Usage examples:
    uv run python -m scripts.data.scrape.run
    uv run python -m scripts.data.scrape.run --store yody_vn
    uv run python -m scripts.data.scrape.run --batch-size 100
    uv run python -m scripts.data.scrape.run --rescrape-failed
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .base import REPO_ROOT, new_client
from .batch_gate import (
    QUARANTINE_DIR,
    GateThresholds,
    chunk_items,
    gate_batch,
    now_iso,
    write_quarantine,
    yield_ok,
)
from .build_registry import build_registry
from .config import STORES_BY_ID, StoreConfig, active_stores
from .download_images import download_all
from .manifest import BatchRecord, failed_batches, load_manifest, record_result, save_manifest
from .normalize import (
    next_index,
    normalize_products,
    to_catalog_frame,
    to_links_frame,
    write_frames,
)
from .shopify import fetch_products
from .sitemap import fetch_products_via_html, fetch_products_via_product_json

logger = logging.getLogger("scrape")


def _select_stores(names: list[str] | None) -> list[StoreConfig]:
    if not names:
        return active_stores()
    out: list[StoreConfig] = []
    for name in names:
        store = STORES_BY_ID.get(name)
        if store is None:
            logger.error("unknown store_id %s (see config.STORES)", name)
            sys.exit(2)
        if store.platform == "skip":
            logger.warning("store %s is marked skip — no adapter", name)
            continue
        out.append(store)
    return out


def _resolve_failed_targets(
    manifest: dict[str, BatchRecord],
) -> tuple[list[StoreConfig], dict[str, set[int] | None]]:
    """Map manifest failures to store reruns.

    ``store#ALL`` wins over any chunk-specific failures for the same store.
    """
    targets = failed_batches(manifest)
    whole_store: set[str] = set()
    by_store: dict[str, set[int]] = {}
    for batch_id in targets:
        store_id, _, chunk = batch_id.partition("#")
        if store_id not in STORES_BY_ID:
            logger.warning("manifest references unknown store_id %s; skipping", store_id)
            continue
        if chunk == "ALL":
            whole_store.add(store_id)
            by_store.pop(store_id, None)
            continue
        if store_id in whole_store:
            continue
        by_store.setdefault(store_id, set()).add(int(chunk))

    store_ids = sorted(whole_store | by_store.keys())
    stores = [STORES_BY_ID[store_id] for store_id in store_ids]
    only_for = {store_id: None for store_id in whole_store}
    only_for.update({store_id: chunks for store_id, chunks in by_store.items()})
    return stores, only_for


def _write_store_quarantine(
    store_id: str,
    items: list,
    *,
    quarantine_dir: Path = QUARANTINE_DIR,
) -> Path:
    """Persist a whole-store failure under ``quarantine/<store>__ALL/``."""
    out_dir = quarantine_dir / f"{store_id}__ALL"
    out_dir.mkdir(parents=True, exist_ok=True)
    to_catalog_frame(items).to_parquet(out_dir / "catalog.parquet", index=False)
    to_links_frame(items).to_parquet(out_dir / "links.parquet", index=False)
    return out_dir


def gate_and_promote(
    store: StoreConfig,
    items: list,
    raw_count: int,
    *,
    thresholds: GateThresholds,
    download: bool,
    client,
    repo_root: Path,
    manifest: dict[str, BatchRecord],
    now: str,
    check_images: bool = True,
    quarantine_dir: Path = QUARANTINE_DIR,
) -> int:
    """Chunk -> gate -> promote or quarantine. Returns promoted item count."""
    if not yield_ok(len(items), raw_count, thresholds):
        yield_ratio = round(len(items) / raw_count, 4) if raw_count else 1.0
        manifest[f"{store.store_id}#ALL"] = BatchRecord(
            store_id=store.store_id,
            chunk_index=-1,
            status="quarantined",
            item_count=len(items),
            blocking_codes=["low_yield"],
            metrics={"yield": yield_ratio},
            updated_at=now,
            raw_count=raw_count,
        )
        if items:
            out_dir = _write_store_quarantine(store.store_id, items, quarantine_dir=quarantine_dir)
            logger.warning(
                "[%s] low yield %d/%d -> whole store quarantined at %s",
                store.store_id,
                len(items),
                raw_count,
                out_dir,
            )
        else:
            logger.warning(
                "[%s] low yield %d/%d -> whole store quarantined",
                store.store_id,
                len(items),
                raw_count,
            )
        return 0

    promoted = 0
    for idx, chunk in enumerate(chunk_items(items, thresholds.batch_size)):
        if download:
            ok_ids = download_all(chunk, client=client)
            kept = [item for item in chunk if item.item_id in ok_ids]
            dropped = len(chunk) - len(kept)
            if dropped:
                logger.warning(
                    "[%s] chunk %d dropped %d items (image fail)", store.store_id, idx, dropped
                )
            chunk = kept
        if not chunk:
            logger.warning("[%s] chunk %d empty after pre-gate filtering", store.store_id, idx)
            continue

        result = gate_batch(
            chunk,
            store_id=store.store_id,
            chunk_index=idx,
            thresholds=thresholds,
            repo_root=repo_root,
            check_images=check_images,
        )
        if result.passed:
            write_frames(chunk)
            promoted += len(chunk)
            record_result(manifest, result, status="passed", now=now)
            logger.info("[%s] chunk %d promoted (%d items)", store.store_id, idx, len(chunk))
            continue

        out_dir = write_quarantine(result, chunk, quarantine_dir=quarantine_dir)
        record_result(manifest, result, status="quarantined", now=now)
        logger.warning(
            "[%s] chunk %d quarantined (%d items): %s -> %s",
            store.store_id,
            idx,
            len(chunk),
            ",".join(result.blocking_codes),
            out_dir,
        )
    return promoted


def run_store(
    store: StoreConfig,
    *,
    use_cache: bool,
    limit: int | None,
    download: bool,
    collector: str,
    offline: bool = False,
    dry_run: bool = False,
    gate: bool = True,
    thresholds: GateThresholds = GateThresholds(),
    manifest: dict[str, BatchRecord] | None = None,
    only_chunks: set[int] | None = None,
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

        raw_count = len(raws)
        if not gate:
            if download:
                ok_ids = download_all(items, client=client)
                kept = [item for item in items if item.item_id in ok_ids]
                dropped = len(items) - len(kept)
                if dropped:
                    logger.warning("[%s] dropped %d items (image fail)", store.store_id, dropped)
                items = kept
            if not items:
                return 0
            write_frames(items)
            return len(items)

        if only_chunks is not None:
            chunks = chunk_items(items, thresholds.batch_size)
            targeted_items: list = []
            for idx in sorted(only_chunks):
                if idx < len(chunks):
                    targeted_items.extend(chunks[idx])
            items = targeted_items
            raw_count = len(items)  # skip yield gate when re-running a subset of chunks
            if not items:
                logger.warning("[%s] no targeted chunks found for re-scrape", store.store_id)
                return 0

        return gate_and_promote(
            store,
            items,
            raw_count,
            thresholds=thresholds,
            download=download,
            client=client,
            repo_root=REPO_ROOT,
            manifest=manifest if manifest is not None else {},
            now=now_iso(),
            check_images=download,
            quarantine_dir=QUARANTINE_DIR,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OutfitMatch VN catalog scraper")
    parser.add_argument(
        "--store", action="append", help="store_id; repeatable. Default: all active."
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap items per store (smoke test)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only raw cache, skip every network fetch (errors if cache missing)",
    )
    parser.add_argument("--no-images", action="store_true", help="Skip image download")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + normalize only; do not write parquet/images.",
    )
    parser.add_argument("--collector", default="scraper", help="Tag for catalog_metadata.collector")
    parser.add_argument("--batch-size", type=int, default=250, help="Items per quality-gated batch")
    parser.add_argument(
        "--min-yield",
        type=float,
        default=0.30,
        help="Min normalized/raw ratio per store",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Disable quality gate and write directly to parquet",
    )
    parser.add_argument(
        "--rescrape-failed",
        action="store_true",
        help="Only re-run store/chunks marked quality-failed in the manifest",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--skip-registry", action="store_true", help="Don't (re)seed store_registry.db"
    )
    args = parser.parse_args(argv)

    if args.rescrape_failed and args.no_gate:
        parser.error("--rescrape-failed requires the quality gate to stay enabled")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if not args.skip_registry:
        build_registry()

    thresholds = GateThresholds(batch_size=args.batch_size, min_yield=args.min_yield)
    manifest = load_manifest()

    if args.rescrape_failed:
        if not failed_batches(manifest):
            logger.info("no quality-failed batches in manifest — nothing to re-scrape")
            return 0
        stores, only_for = _resolve_failed_targets(manifest)
    else:
        stores = _select_stores(args.store)
        only_for: dict[str, set[int] | None] = {}

    total = 0
    summary: list[tuple[str, int]] = []
    for store in stores:
        count = run_store(
            store,
            use_cache=True,
            limit=args.limit,
            download=not args.no_images,
            collector=args.collector,
            offline=args.offline,
            dry_run=args.dry_run,
            gate=not args.no_gate,
            thresholds=thresholds,
            manifest=manifest,
            only_chunks=only_for.get(store.store_id),
        )
        total += count
        summary.append((store.store_id, count))

    if not args.dry_run and not args.no_gate:
        save_manifest(manifest)
        bad = failed_batches(manifest)
        if bad:
            logger.warning("quarantined batches (%d): %s", len(bad), ", ".join(bad))

    logger.info("══════ done. total items kept: %d ══════", total)
    for store_id, count in summary:
        logger.info("  %-15s %5d", store_id, count)
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
