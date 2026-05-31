"""Re-tag catalog categories in-place using the current categorize() logic.

Run after fixing the category mapper to repair existing catalog rows without
re-crawling. Re-classifies from `title_vi` (titles are the most reliable
signal — Vietnamese fashion titles always lead with the category noun) and
drops rows that no longer map to a valid category. Orphan rows in
`item_store_links.parquet` are pruned to keep the two tables join-clean.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from typing import TypedDict

import pandas as pd

from .base import CATALOG_DIR
from .category_map import categorize

logger = logging.getLogger(__name__)

CATALOG_PARQUET = CATALOG_DIR / "catalog_metadata.parquet"
LINKS_PARQUET = CATALOG_DIR / "item_store_links.parquet"


class RetagReport(TypedDict):
    total: int
    unchanged: int
    changed: int
    dropped: int
    new_category_counts: dict[str, int]
    transitions: dict[str, int]
    dropped_sample_titles: list[str]
    pruned_links: int


def _recategorize(title: str) -> str | None:
    return categorize(title or "")


def retag(*, dry_run: bool = False) -> RetagReport:
    """Re-apply categorize() to every catalog row and rewrite parquet files."""
    if not CATALOG_PARQUET.exists():
        raise FileNotFoundError(CATALOG_PARQUET)

    cat = pd.read_parquet(CATALOG_PARQUET)
    old = cat["category"].astype(str).tolist()
    titles = cat["title_vi"].fillna("").tolist()
    new = [_recategorize(t) for t in titles]

    transitions: Counter[str] = Counter()
    dropped_titles: list[str] = []
    unchanged = changed = dropped = 0
    for old_c, new_c, title in zip(old, new, titles, strict=False):
        if new_c is None:
            dropped += 1
            if len(dropped_titles) < 25:
                dropped_titles.append(title)
            continue
        if new_c == old_c:
            unchanged += 1
        else:
            changed += 1
            transitions[f"{old_c} -> {new_c}"] += 1

    cat = cat.assign(category=new)
    keep = cat[cat["category"].notna()].copy()
    new_counts = Counter(keep["category"].tolist())

    pruned_links = 0
    if not dry_run:
        keep.to_parquet(CATALOG_PARQUET, index=False)
        if LINKS_PARQUET.exists():
            links = pd.read_parquet(LINKS_PARQUET)
            keep_ids = set(keep["item_id"].astype(str))
            before = len(links)
            links = links[links["item_id"].astype(str).isin(keep_ids)]
            pruned_links = before - len(links)
            links.to_parquet(LINKS_PARQUET, index=False)
        logger.info(
            "retag: %d kept (%d unchanged + %d changed), %d dropped, %d link rows pruned",
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
        new_category_counts=dict(new_counts),
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
