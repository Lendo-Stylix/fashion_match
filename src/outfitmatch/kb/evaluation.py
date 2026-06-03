"""Evaluate generated outfit KB quality and price-tier bias."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd

from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, PRICE_TIER, formality_span_ok


@dataclass(frozen=True)
class OutfitBuildReport:
    """Aggregate quality report for a generated outfit dataframe."""

    total_outfits: int
    price_tier_counts: dict[str, int]
    price_tier_shares: dict[str, float]
    gen_method_counts: dict[str, int]
    gender_counts: dict[str, int]
    mixed_gender_count: int
    formality_clash_count: int
    unique_combo_count: int
    invalid_rule_count: int
    distinct_item_count: int
    item_reuse_max: int
    item_reuse_p95: int
    dress_outfit_count: int
    dress_outfit_share: float
    store_slot_counts: dict[str, int]
    store_slot_shares: dict[str, float]
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


def _count_mixed_gender(frame: pd.DataFrame, item_gender: dict[str, str]) -> int:
    """Number of outfits whose items mix incompatible genders (men+women+kid).

    ``unisex`` items pair with anything, so an outfit is mixed only when its
    non-unisex item genders disagree.
    """
    if "item_ids" not in frame:
        return 0
    mixed = 0
    for raw in frame["item_ids"]:
        genders = {item_gender.get(iid, "unisex") for iid in _loads_list(raw)}
        if len(genders - {"unisex"}) > 1:
            mixed += 1
    return mixed


def _count_formality_clash(frame: pd.DataFrame, item_formality: dict[str, str]) -> int:
    """Outfits whose core garments span more than one formality band.

    Uses the parallel ``item_ids`` / ``categories`` JSON columns; only
    FORMALITY_RELEVANT_CATEGORIES participate. Unknown items default to ``casual``.
    """
    if "item_ids" not in frame or "categories" not in frame:
        return 0
    clashes = 0
    for raw_ids, raw_cats in zip(frame["item_ids"], frame["categories"], strict=False):
        ids = _loads_list(raw_ids)
        cats = _loads_list(raw_cats)
        formalities = [
            item_formality.get(iid, "casual")
            for iid, cat in zip(ids, cats, strict=False)
            if cat in FORMALITY_RELEVANT_CATEGORIES
        ]
        if not formality_span_ok(formalities):
            clashes += 1
    return clashes


def _item_usage(frame: pd.DataFrame) -> Counter[str]:
    usage: Counter[str] = Counter()
    if "item_ids" not in frame:
        return usage
    for raw in frame["item_ids"]:
        usage.update(_loads_list(raw))
    return usage


def _percentile_int(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round(max(0.0, min(1.0, q)) * (len(ordered) - 1))
    return int(ordered[index])


def _count_dress_outfits(frame: pd.DataFrame) -> int:
    if "categories" not in frame:
        return 0
    return sum(1 for raw in frame["categories"] if "dress" in _loads_list(raw))


def _store_slot_counts(frame: pd.DataFrame, item_store: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    if "item_ids" not in frame:
        return counts
    for raw in frame["item_ids"]:
        for item_id in _loads_list(raw):
            store_id = item_store.get(item_id)
            if store_id:
                counts[store_id] += 1
    return counts


def evaluate_outfit_frame(
    frame: pd.DataFrame,
    *,
    price_tier_targets: dict[str, float],
    item_gender: dict[str, str] | None = None,
    item_formality: dict[str, str] | None = None,
    item_store: dict[str, str] | None = None,
) -> OutfitBuildReport:
    """Compute deterministic quality and bias metrics for generated outfit rows.

    ``item_gender`` (item_id → GENDER) enables the mixed-gender integrity check;
    when omitted the count is 0.
    """
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
    usage = _item_usage(frame)
    reuse_values = list(usage.values())
    dress_count = _count_dress_outfits(frame)
    stores = _store_slot_counts(frame, item_store or {})
    store_total = sum(stores.values())
    return OutfitBuildReport(
        total_outfits=total,
        price_tier_counts=price_counts,
        price_tier_shares={tier: round(price_shares[tier], 4) for tier in PRICE_TIER},
        gen_method_counts={str(k): int(v) for k, v in frame["gen_method"].value_counts().items()},
        gender_counts=(
            {str(k): int(v) for k, v in frame["gender"].value_counts().items()}
            if "gender" in frame
            else {}
        ),
        mixed_gender_count=_count_mixed_gender(frame, item_gender or {}),
        formality_clash_count=_count_formality_clash(frame, item_formality or {}),
        unique_combo_count=int(frame["item_ids"].nunique()) if "item_ids" in frame else 0,
        invalid_rule_count=int((~frame["categories"].map(_is_valid_rule)).sum()),
        distinct_item_count=len(usage),
        item_reuse_max=max(reuse_values, default=0),
        item_reuse_p95=_percentile_int(reuse_values, 0.95),
        dress_outfit_count=dress_count,
        dress_outfit_share=round(dress_count / total, 4) if total else 0.0,
        store_slot_counts=dict(stores),
        store_slot_shares={
            store: round(count / store_total, 4) for store, count in sorted(stores.items())
        },
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
            f"genders: {json.dumps(report.gender_counts, ensure_ascii=False)}",
            f"mixed_gender_outfits: {report.mixed_gender_count}",
            f"formality_clash_outfits: {report.formality_clash_count}",
            f"unique_combos: {report.unique_combo_count}",
            f"invalid_rules: {report.invalid_rule_count}",
            f"distinct_items: {report.distinct_item_count}",
            f"item_reuse_max: {report.item_reuse_max}",
            f"item_reuse_p95: {report.item_reuse_p95}",
            f"dress_outfits: {report.dress_outfit_count} ({report.dress_outfit_share:.4f})",
            f"store_slot_shares: {json.dumps(report.store_slot_shares, ensure_ascii=False)}",
            f"score_min: {report.score_min:.3f}",
            f"score_mean: {report.score_mean:.3f}",
            f"score_max: {report.score_max:.3f}",
            f"max_price_tier_deviation: {report.max_price_tier_deviation:.4f}",
        ]
    )
