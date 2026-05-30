"""Evaluate generated outfit KB quality and price-tier bias."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from outfitmatch.vocab import PRICE_TIER


@dataclass(frozen=True)
class OutfitBuildReport:
    """Aggregate quality report for a generated outfit dataframe."""

    total_outfits: int
    price_tier_counts: dict[str, int]
    price_tier_shares: dict[str, float]
    gen_method_counts: dict[str, int]
    unique_combo_count: int
    invalid_rule_count: int
    score_min: float
    score_mean: float
    score_max: float
    max_price_tier_deviation: float


def _loads_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(v) for v in raw]
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v) for v in parsed]


def _is_valid_rule(raw_categories: Any) -> bool:
    categories = set(_loads_list(raw_categories))
    return {"top", "bottom", "shoes"} <= categories or {"dress", "shoes"} <= categories


def evaluate_outfit_frame(
    frame: pd.DataFrame, *, price_tier_targets: dict[str, float]
) -> OutfitBuildReport:
    """Compute deterministic quality and bias metrics for generated outfit rows."""
    total = len(frame)
    price_counts = {tier: int((frame["price_tier"] == tier).sum()) for tier in PRICE_TIER}
    price_shares = {tier: (price_counts[tier] / total if total else 0.0) for tier in PRICE_TIER}
    target_total = sum(max(0.0, float(v)) for v in price_tier_targets.values()) or 1.0
    normalized_targets = {
        tier: max(0.0, float(price_tier_targets.get(tier, 0.0))) / target_total
        for tier in PRICE_TIER
    }
    deviations = {tier: abs(price_shares[tier] - normalized_targets[tier]) for tier in PRICE_TIER}
    scores = (
        frame["compatibility_score"] if "compatibility_score" in frame else pd.Series(dtype=float)
    )
    return OutfitBuildReport(
        total_outfits=total,
        price_tier_counts=price_counts,
        price_tier_shares={tier: round(price_shares[tier], 4) for tier in PRICE_TIER},
        gen_method_counts={str(k): int(v) for k, v in frame["gen_method"].value_counts().items()},
        unique_combo_count=int(frame["item_ids"].nunique()) if "item_ids" in frame else 0,
        invalid_rule_count=int((~frame["categories"].map(_is_valid_rule)).sum()),
        score_min=float(scores.min()) if not scores.empty else 0.0,
        score_mean=float(scores.mean()) if not scores.empty else 0.0,
        score_max=float(scores.max()) if not scores.empty else 0.0,
        max_price_tier_deviation=round(max(deviations.values(), default=0.0), 4),
    )


def summarize_outfit_report(report: OutfitBuildReport) -> str:
    """Return a stable human-readable generated-KB summary."""
    return "\n".join(
        [
            f"outfits: {report.total_outfits}",
            f"price_tiers: {json.dumps(report.price_tier_counts, ensure_ascii=False)}",
            f"price_shares: {json.dumps(report.price_tier_shares, ensure_ascii=False)}",
            f"gen_methods: {json.dumps(report.gen_method_counts, ensure_ascii=False)}",
            f"unique_combos: {report.unique_combo_count}",
            f"invalid_rules: {report.invalid_rule_count}",
            f"score_min: {report.score_min:.3f}",
            f"score_mean: {report.score_mean:.3f}",
            f"score_max: {report.score_max:.3f}",
            f"max_price_tier_deviation: {report.max_price_tier_deviation:.4f}",
        ]
    )
