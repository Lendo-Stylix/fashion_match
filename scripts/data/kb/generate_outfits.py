"""Generate outfit combinations from the validated VN catalog.

Example:
    uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from outfitmatch.kb.build_outfits import (
    DEFAULT_PRICE_TIER_TARGETS,
    build_outfit_records,
    write_outfits,
)
from outfitmatch.kb.catalog import group_items_by_category, load_catalog_items
from outfitmatch.kb.evaluation import evaluate_outfit_frame, summarize_outfit_report
from scripts.data.scrape.base import CATALOG_DIR, REPO_ROOT
from scripts.data.scrape.quality import check_catalog, summarize_catalog

logger = logging.getLogger("kb.generate_outfits")

DEFAULT_OUTPUT = REPO_ROOT / "data" / "custom" / "outfits" / "generated_outfits.parquet"


def _parse_price_targets(raw: str) -> dict[str, float]:
    targets: dict[str, float] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        tier, _, value = part.partition("=")
        if not tier or not value:
            raise argparse.ArgumentTypeError("expected format budget=0.2,mid=0.5,premium=0.3")
        targets[tier.strip()] = float(value)
    return targets


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for deterministic outfit combination generation."""
    parser = argparse.ArgumentParser(description="Generate OutfitMatch KB outfit combinations")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n-outfits", type=int, default=1000)
    parser.add_argument("--fitb-ratio", type=float, default=0.70)
    parser.add_argument("--limit-per-category", type=int, default=60)
    parser.add_argument("--score-threshold", type=float, default=0.0)
    parser.add_argument(
        "--price-tier-targets",
        type=_parse_price_targets,
        default=DEFAULT_PRICE_TIER_TARGETS,
        help="Target outfit price mix, e.g. budget=0.2,mid=0.5,premium=0.3.",
    )
    parser.add_argument("--no-price-balance", action="store_true")
    parser.add_argument("--skip-quality-check", action="store_true")
    parser.add_argument(
        "--include-kid",
        action="store_true",
        help="Include kids' wear (default: adult-only — men/women/unisex).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if not args.skip_quality_check:
        report = check_catalog(args.catalog, args.links, repo_root=REPO_ROOT)
        logger.info("catalog quality:\n%s", summarize_catalog(report))
        if not report.ok:
            logger.error("catalog has quality errors; aborting")
            return 1

    # Adult-only KB by default: kids' items must not mix into adult outfits.
    genders = None if args.include_kid else {"men", "women", "unisex"}
    items = load_catalog_items(args.catalog, args.links, genders=genders)
    items_by_category = group_items_by_category(items, limit_per_category=args.limit_per_category)
    logger.info("loaded %d in-stock items (genders=%s)", len(items), genders or "all")
    logger.info("category caps: %s", {k: len(v) for k, v in sorted(items_by_category.items())})

    price_targets = None if args.no_price_balance else args.price_tier_targets
    logger.info("price-tier targets: %s", price_targets or "disabled")
    outfits = build_outfit_records(
        items_by_category,
        n_outfits=args.n_outfits,
        fitb_ratio=args.fitb_ratio,
        score_threshold=args.score_threshold,
        price_tier_targets=price_targets,
    )
    if not outfits:
        logger.error("no outfits generated; check category coverage")
        return 1
    write_outfits(outfits, args.output)
    logger.info("wrote %d outfits → %s", len(outfits), args.output)
    item_gender = {item.item_id: item.gender for item in items}
    item_formality = {item.item_id: item.formality for item in items}
    outfit_report = evaluate_outfit_frame(
        pd.read_parquet(args.output),
        price_tier_targets=args.price_tier_targets,
        item_gender=item_gender,
        item_formality=item_formality,
    )
    logger.info("outfit build report:\n%s", summarize_outfit_report(outfit_report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
