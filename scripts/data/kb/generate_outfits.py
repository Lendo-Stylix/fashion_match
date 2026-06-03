"""Generate outfit combinations from the validated VN catalog.

DEPRECATED (graph KB): retrieval now uses graph traversal (`kb/graph.py`,
`kb/traversal.py`, `retrieval.py`). This materialized-outfit path stays
temporary for legacy comparison and will be removed in a separate cleanup after
the graph pipeline is stable end-to-end.

Example:
    uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 90
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, replace
from pathlib import Path

from outfitmatch.kb.build_outfits import (
    DEFAULT_PRICE_TIER_TARGETS,
    OutfitDiversityConfig,
    build_outfit_records,
    outfits_to_frame,
    write_outfits,
)
from outfitmatch.kb.catalog import group_items_by_category, load_catalog_items
from outfitmatch.kb.evaluation import (
    OutfitBuildReport,
    evaluate_outfit_frame,
    summarize_outfit_report,
)
from scripts.data.scrape.base import CATALOG_DIR, REPO_ROOT
from scripts.data.scrape.quality import check_catalog, summarize_catalog

logger = logging.getLogger("kb.generate_outfits")

DEFAULT_OUTPUT = REPO_ROOT / "data" / "custom" / "outfits" / "generated_outfits.parquet"


def _parse_float_targets(raw: str) -> dict[str, float]:
    targets: dict[str, float] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        tier, _, value = part.partition("=")
        if not tier or not value:
            raise argparse.ArgumentTypeError("expected format key=0.2,other=0.5")
        targets[tier.strip()] = float(value)
    return targets


def _parse_price_targets(raw: str) -> dict[str, float]:
    return _parse_float_targets(raw)


def _expected_counts(n: int, targets: dict[str, float]) -> dict[str, int]:
    positive = {key: max(0.0, float(value)) for key, value in targets.items()}
    total = sum(positive.values()) or 1.0
    raw = {key: n * value / total for key, value in positive.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remainder = n - sum(counts.values())
    ranked = sorted(raw, key=lambda key: (raw[key] - counts[key], raw[key]), reverse=True)
    for key in ranked[:remainder]:
        counts[key] += 1
    return counts


def _quality_failures(
    report: OutfitBuildReport,
    *,
    n_outfits: int,
    fitb_ratio: float,
    price_targets: dict[str, float],
    min_distinct_items: int,
    max_item_reuse: int,
    max_item_reuse_p95: int,
    min_dress_share: float,
    max_dress_share: float,
    max_gender_share: float,
    max_yody_share: float,
    min_score_mean: float,
) -> list[str]:
    failures: list[str] = []
    if report.total_outfits != n_outfits:
        failures.append(f"total_outfits {report.total_outfits} != {n_outfits}")
    if report.price_tier_counts != _expected_counts(n_outfits, price_targets):
        failures.append(f"price_tier_counts {report.price_tier_counts} != target")
    expected_fitb = max(0, min(n_outfits, round(n_outfits * fitb_ratio)))
    expected_methods = {"fitb_beam": expected_fitb, "random_scored": n_outfits - expected_fitb}
    if report.gen_method_counts != expected_methods:
        failures.append(f"gen_method_counts {report.gen_method_counts} != {expected_methods}")
    if report.unique_combo_count != n_outfits:
        failures.append(f"unique_combo_count {report.unique_combo_count} != {n_outfits}")
    if report.invalid_rule_count:
        failures.append(f"invalid_rule_count {report.invalid_rule_count} != 0")
    if report.mixed_gender_count:
        failures.append(f"mixed_gender_count {report.mixed_gender_count} != 0")
    if report.formality_clash_count:
        failures.append(f"formality_clash_count {report.formality_clash_count} != 0")
    if report.distinct_item_count < min_distinct_items:
        failures.append(f"distinct_item_count {report.distinct_item_count} < {min_distinct_items}")
    if report.item_reuse_max > max_item_reuse:
        failures.append(f"item_reuse_max {report.item_reuse_max} > {max_item_reuse}")
    if report.item_reuse_p95 > max_item_reuse_p95:
        failures.append(f"item_reuse_p95 {report.item_reuse_p95} > {max_item_reuse_p95}")
    if not min_dress_share <= report.dress_outfit_share <= max_dress_share:
        failures.append(
            f"dress_outfit_share {report.dress_outfit_share:.4f} not in "
            f"[{min_dress_share:.4f}, {max_dress_share:.4f}]"
        )
    gender_total = sum(report.gender_counts.values()) or 1
    gender_share_max = max(
        (count / gender_total for count in report.gender_counts.values()), default=0.0
    )
    if gender_share_max > max_gender_share:
        failures.append(f"max_gender_share {gender_share_max:.4f} > {max_gender_share:.4f}")
    yody_share = report.store_slot_shares.get("yody_vn", 0.0)
    if yody_share > max_yody_share:
        failures.append(f"yody_vn share {yody_share:.4f} > {max_yody_share:.4f}")
    if report.score_mean < min_score_mean:
        failures.append(f"score_mean {report.score_mean:.4f} < {min_score_mean:.4f}")
    return failures


def _quality_score(report: OutfitBuildReport) -> float:
    gender_total = sum(report.gender_counts.values()) or 1
    women_share = report.gender_counts.get("women", 0) / gender_total
    yody_share = report.store_slot_shares.get("yody_vn", 0.0)
    return (
        report.score_mean
        + report.distinct_item_count / 1000
        + max(0.0, 80 - report.item_reuse_p95) / 80
        + max(0.0, 120 - report.item_reuse_max) / 120
        + max(0.0, 1 - abs(report.dress_outfit_share - 0.12))
        + max(0.0, 1 - abs(women_share - 0.55))
        + max(0.0, 1 - yody_share)
    )


def _report_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}_quality_report.jsonl")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for deterministic outfit combination generation."""
    parser = argparse.ArgumentParser(description="Generate OutfitMatch KB outfit combinations")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n-outfits", type=int, default=1000)
    parser.add_argument("--fitb-ratio", type=float, default=0.70)
    parser.add_argument("--limit-per-category", type=int, default=90)
    parser.add_argument("--score-threshold", type=float, default=0.0)
    parser.add_argument(
        "--price-tier-targets",
        type=_parse_price_targets,
        default=DEFAULT_PRICE_TIER_TARGETS,
        help="Target outfit price mix, e.g. budget=0.2,mid=0.5,premium=0.3.",
    )
    parser.add_argument("--no-price-balance", action="store_true")
    parser.add_argument("--no-diversity", action="store_true")
    parser.add_argument("--quality-loop-attempts", type=int, default=2)
    parser.add_argument("--diversity-max-item-reuse", type=int, default=45)
    parser.add_argument("--diversity-target-dress-share", type=float, default=0.12)
    parser.add_argument("--diversity-max-dress-share", type=float, default=0.18)
    parser.add_argument(
        "--diversity-target-gender",
        type=_parse_float_targets,
        default={"women": 0.55, "men": 0.45},
    )
    parser.add_argument(
        "--diversity-max-gender",
        type=_parse_float_targets,
        default={"women": 0.62, "men": 0.62},
    )
    parser.add_argument(
        "--diversity-target-store",
        type=_parse_float_targets,
        default={
            "yody_vn": 0.45,
            "aristino_vn": 0.22,
            "rubies": 0.16,
            "canifa_vn": 0.07,
            "dirtycoins": 0.05,
            "huelleyrose": 0.03,
        },
    )
    parser.add_argument(
        "--diversity-max-store",
        type=_parse_float_targets,
        default={"yody_vn": 0.60, "rubies": 0.25, "aristino_vn": 0.35},
    )
    parser.add_argument("--diversity-max-scan-per-pick", type=int, default=12_000)
    parser.add_argument("--min-distinct-items", type=int, default=350)
    parser.add_argument("--max-quality-item-reuse", type=int, default=80)
    parser.add_argument("--max-quality-item-reuse-p95", type=int, default=35)
    parser.add_argument("--min-quality-dress-share", type=float, default=0.08)
    parser.add_argument("--max-quality-dress-share", type=float, default=0.20)
    parser.add_argument("--max-quality-gender-share", type=float, default=0.64)
    parser.add_argument("--max-quality-yody-share", type=float, default=0.61)
    parser.add_argument("--min-quality-score-mean", type=float, default=0.70)
    parser.add_argument("--quality-report", type=Path, default=None)
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
    item_gender = {item.item_id: item.gender for item in items}
    item_formality = {item.item_id: item.formality for item in items}
    item_store = {item.item_id: str(item.store.get("store_id") or "") for item in items}
    quality_report_path = args.quality_report or _report_path(args.output)
    quality_report_path.parent.mkdir(parents=True, exist_ok=True)
    quality_report_path.write_text("", encoding="utf-8")

    base_diversity = None
    if not args.no_diversity and price_targets is not None:
        base_diversity = OutfitDiversityConfig(
            max_item_reuse=args.diversity_max_item_reuse,
            target_gender_shares=args.diversity_target_gender,
            target_dress_share=args.diversity_target_dress_share,
            max_dress_share=args.diversity_max_dress_share,
            max_gender_shares=args.diversity_max_gender,
            target_store_slot_shares=args.diversity_target_store,
            max_store_slot_shares=args.diversity_max_store,
            max_scan_per_pick=args.diversity_max_scan_per_pick,
        )
    attempts = max(1, args.quality_loop_attempts)
    best_score = float("-inf")
    best_outfits = None
    best_report = None
    best_failures: list[str] = []

    for attempt in range(1, attempts + 1):
        diversity = base_diversity
        if base_diversity is not None and attempt > 1:
            # Later attempts relax aggregate caps first, preserving exact price/method quotas.
            diversity = replace(
                base_diversity,
                max_item_reuse=args.diversity_max_item_reuse + 10 * (attempt - 1),
                max_dress_share=min(0.25, args.diversity_max_dress_share + 0.02 * (attempt - 1)),
                max_gender_shares={
                    key: min(0.70, value + 0.02 * (attempt - 1))
                    for key, value in args.diversity_max_gender.items()
                },
                max_store_slot_shares={
                    key: min(0.70, value + 0.02 * (attempt - 1))
                    for key, value in args.diversity_max_store.items()
                },
            )
        logger.info("generation attempt %d/%d diversity=%s", attempt, attempts, diversity)
        outfits = build_outfit_records(
            items_by_category,
            n_outfits=args.n_outfits,
            fitb_ratio=args.fitb_ratio,
            score_threshold=args.score_threshold,
            price_tier_targets=price_targets,
            diversity_config=diversity,
        )
        if not outfits:
            logger.error("attempt %d generated no outfits; check category coverage", attempt)
            continue
        frame = outfits_to_frame(outfits)
        report = evaluate_outfit_frame(
            frame,
            price_tier_targets=args.price_tier_targets,
            item_gender=item_gender,
            item_formality=item_formality,
            item_store=item_store,
        )
        failures = _quality_failures(
            report,
            n_outfits=args.n_outfits,
            fitb_ratio=args.fitb_ratio,
            price_targets=args.price_tier_targets,
            min_distinct_items=args.min_distinct_items,
            max_item_reuse=args.max_quality_item_reuse,
            max_item_reuse_p95=args.max_quality_item_reuse_p95,
            min_dress_share=args.min_quality_dress_share,
            max_dress_share=args.max_quality_dress_share,
            max_gender_share=args.max_quality_gender_share,
            max_yody_share=args.max_quality_yody_share,
            min_score_mean=args.min_quality_score_mean,
        )
        score = _quality_score(report)
        with quality_report_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "attempt": attempt,
                        "passed": not failures,
                        "score": round(score, 6),
                        "failures": failures,
                        "diversity_config": asdict(diversity) if diversity else None,
                        **asdict(report),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
        logger.info("attempt %d report:\n%s", attempt, summarize_outfit_report(report))
        if failures:
            logger.warning("attempt %d quality failures: %s", attempt, failures)
        if score > best_score:
            best_score = score
            best_outfits = outfits
            best_report = report
            best_failures = failures
        if not failures:
            best_outfits = outfits
            best_report = report
            best_failures = []
            break

    if best_outfits is None or best_report is None:
        logger.error("no outfits generated; check category coverage")
        return 1
    write_outfits(best_outfits, args.output)
    logger.info("wrote %d outfits → %s", len(best_outfits), args.output)
    logger.info("quality report attempts → %s", quality_report_path)
    logger.info("selected outfit build report:\n%s", summarize_outfit_report(best_report))
    if best_failures:
        logger.error("selected KB still fails quality gate: %s", best_failures)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
