"""Re-tag catalog categories in-place using store-native product_type + title.

Run after changing the categoriser to repair an existing catalog without
re-crawling. For every catalog row it:

  1. recovers the store-native ``product_type`` from the raw HTTP cache
     (offline, via the same adapters used by the live scrape);
  2. calls :func:`store_category_map.resolve_category` — store taxonomy first,
     title-token categoriser as fallback;
  3. drops rows that resolve to None (out-of-scope SKUs or unclassifiable) and
     prunes the orphaned rows from ``item_store_links.parquet``;
  4. persists the raw ``source_product_type`` column for traceability.

Idempotent: re-running yields the same catalog.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from typing import TypedDict

import pandas as pd

from .base import CATALOG_DIR, new_client
from .config import StoreConfig, active_stores
from .gender_map import infer_gender
from .shopify import RawProduct, fetch_products
from .sitemap import fetch_products_via_html, fetch_products_via_product_json
from .store_category_map import resolve_category

logger = logging.getLogger(__name__)

CATALOG_PARQUET = CATALOG_DIR / "catalog_metadata.parquet"
LINKS_PARQUET = CATALOG_DIR / "item_store_links.parquet"


class RetagReport(TypedDict):
    total: int
    unchanged: int
    changed: int
    dropped: int
    matched_raw: int
    new_category_counts: dict[str, int]
    new_gender_counts: dict[str, int]
    transitions: dict[str, int]
    dropped_sample_titles: list[str]
    pruned_links: int


def _fetch_raw(store: StoreConfig) -> list[RawProduct]:
    with new_client() as client:
        if store.platform == "shopify_like":
            return fetch_products(client, store, use_cache=True, offline=True)
        if store.platform == "sitemap_product_json":
            return fetch_products_via_product_json(client, store, use_cache=True, offline=True)
        if store.platform == "sitemap_html":
            return fetch_products_via_html(client, store, use_cache=True, offline=True)
        return []


def _build_raw_index() -> dict[tuple[str, str], RawProduct]:
    """(store_id, source_product_id) → RawProduct, from offline raw cache."""
    index: dict[tuple[str, str], RawProduct] = {}
    for store in active_stores():
        try:
            raws = _fetch_raw(store)
        except Exception as exc:  # offline cache miss / parse error — keep going
            logger.warning("[%s] raw cache unavailable (%s)", store.store_id, exc)
            continue
        for rp in raws:
            index[(store.store_id, rp.source_product_id)] = rp
        logger.info("[%s] indexed %d raw products", store.store_id, len(raws))
    return index


def retag(*, dry_run: bool = False) -> RetagReport:
    if not CATALOG_PARQUET.exists():
        raise FileNotFoundError(CATALOG_PARQUET)
    if not LINKS_PARQUET.exists():
        raise FileNotFoundError(LINKS_PARQUET)

    cat = pd.read_parquet(CATALOG_PARQUET)
    links = pd.read_parquet(LINKS_PARQUET)

    # item_id → (store_id, source_product_id) — first link wins.
    link_lookup: dict[str, tuple[str, str]] = {}
    for row in links[["item_id", "store_id", "source_product_id"]].itertuples(index=False):
        iid = str(row.item_id)
        if iid not in link_lookup:
            link_lookup[iid] = (str(row.store_id), str(row.source_product_id))

    raw_index = _build_raw_index()

    old = cat["category"].astype(str).tolist()
    titles = cat["title_vi"].fillna("").tolist()
    item_ids = cat["item_id"].astype(str).tolist()

    new: list[str | None] = []
    new_pt: list[str] = []
    new_gender: list[str] = []
    matched_raw = 0
    for iid, title in zip(item_ids, titles, strict=False):
        store_id, spid = link_lookup.get(iid, ("", ""))
        rp = raw_index.get((store_id, spid))
        if rp is not None:
            matched_raw += 1
            resolved = resolve_category(rp.title or title, rp.product_type, rp.tags, store_id)
            new.append(resolved)
            new_pt.append(rp.product_type or "")
            new_gender.append(infer_gender(rp.title or title, rp.product_type, store_id, resolved))
        else:
            resolved = resolve_category(title, "", None, store_id)
            new.append(resolved)
            new_pt.append("")
            new_gender.append(infer_gender(title, "", store_id, resolved))

    transitions: Counter[str] = Counter()
    dropped_titles: list[str] = []
    unchanged = changed = dropped = 0
    for old_c, new_c, title in zip(old, new, titles, strict=False):
        if new_c is None:
            dropped += 1
            if len(dropped_titles) < 25:
                dropped_titles.append(title)
        elif new_c == old_c:
            unchanged += 1
        else:
            changed += 1
            transitions[f"{old_c} -> {new_c}"] += 1

    cat = cat.assign(category=new, source_product_type=new_pt, gender=new_gender)
    keep = cat[cat["category"].notna()].copy()
    # Re-order so source_product_type + gender sit right after category.
    cols = list(keep.columns)
    for moved in ("source_product_type", "gender"):
        if moved in cols:
            cols.remove(moved)
    cat_pos = cols.index("category") + 1
    cols[cat_pos:cat_pos] = ["source_product_type", "gender"]
    keep = keep[cols]
    new_counts = Counter(keep["category"].tolist())
    gender_counts = Counter(keep["gender"].tolist())

    pruned_links = 0
    if not dry_run:
        keep.to_parquet(CATALOG_PARQUET, index=False)
        keep_ids = set(keep["item_id"].astype(str))
        before = len(links)
        links = links[links["item_id"].astype(str).isin(keep_ids)]
        pruned_links = before - len(links)
        links.to_parquet(LINKS_PARQUET, index=False)
        logger.info(
            "retag: %d kept (%d unchanged + %d changed), %d dropped, %d links pruned",
            len(keep),
            unchanged,
            changed,
            dropped,
            pruned_links,
        )

    return RetagReport(
        total=len(old),
        unchanged=unchanged,
        changed=changed,
        dropped=dropped,
        matched_raw=matched_raw,
        new_category_counts=dict(new_counts),
        new_gender_counts=dict(gender_counts),
        transitions=dict(transitions.most_common()),
        dropped_sample_titles=dropped_titles,
        pruned_links=pruned_links,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; don't write parquet.")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
    )
    report = retag(dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
