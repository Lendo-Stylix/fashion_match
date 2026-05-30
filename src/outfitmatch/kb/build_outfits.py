"""Build outfit records from grouped catalog items."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from outfitmatch.kb.embedding import extract_item_embeddings
from outfitmatch.kb.generation import generate_fitb_beam, generate_random_scored
from outfitmatch.kb.schema import ItemRecord, OutfitRecord
from outfitmatch.kb.scoring import HeuristicOutfitScorer, rescore_outfits
from outfitmatch.vocab import PRICE_TIER

DEFAULT_PRICE_TIER_TARGETS: dict[str, float] = {"budget": 0.20, "mid": 0.50, "premium": 0.30}


def _renumber(outfits: list[OutfitRecord]) -> list[OutfitRecord]:
    for i, outfit in enumerate(outfits, start=1):
        outfit.outfit_id = f"OF_{i:05d}"
    return outfits


def _ensure_item_embeddings(
    items_by_category: dict[str, list[ItemRecord]], scorer: HeuristicOutfitScorer
) -> None:
    for items in items_by_category.values():
        missing = [item for item in items if not item.item_embedding]
        extract_item_embeddings(missing, scorer)


def _desired_tier_counts(n_outfits: int, targets: dict[str, float]) -> dict[str, int]:
    positive = {tier: max(0.0, float(targets.get(tier, 0.0))) for tier in PRICE_TIER}
    total = sum(positive.values())
    if total <= 0:
        positive = DEFAULT_PRICE_TIER_TARGETS.copy()
        total = sum(positive.values())
    raw = {tier: n_outfits * ratio / total for tier, ratio in positive.items()}
    counts = {tier: int(value) for tier, value in raw.items()}
    remainder = n_outfits - sum(counts.values())
    ranked = sorted(
        PRICE_TIER, key=lambda tier: (raw[tier] - counts[tier], raw[tier]), reverse=True
    )
    for tier in ranked[:remainder]:
        counts[tier] += 1
    return counts


def _combo_key(outfit: OutfitRecord) -> tuple[str, ...]:
    return tuple(item.item_id for item in outfit.items)


def _select_price_balanced(
    candidates: list[OutfitRecord],
    *,
    n_outfits: int,
    price_tier_targets: dict[str, float],
    excluded_keys: set[tuple[str, ...]] | None = None,
) -> list[OutfitRecord]:
    desired = _desired_tier_counts(n_outfits, price_tier_targets)
    by_tier: dict[str, list[OutfitRecord]] = defaultdict(list)
    ranked = sorted(
        candidates,
        key=lambda outfit: (outfit.compatibility_score, -outfit.price_total_vnd, outfit.outfit_id),
        reverse=True,
    )
    for outfit in ranked:
        by_tier[outfit.price_tier].append(outfit)

    selected: list[OutfitRecord] = []
    seen: set[tuple[str, ...]] = set(excluded_keys or set())
    for tier in PRICE_TIER:
        for outfit in by_tier[tier]:
            key = _combo_key(outfit)
            if key in seen:
                continue
            selected.append(outfit)
            seen.add(key)
            if len([x for x in selected if x.price_tier == tier]) >= desired[tier]:
                break

    if len(selected) < n_outfits:
        for outfit in ranked:
            key = _combo_key(outfit)
            if key in seen:
                continue
            selected.append(outfit)
            seen.add(key)
            if len(selected) >= n_outfits:
                break

    if len(selected) < n_outfits:
        selected.extend(ranked[: n_outfits - len(selected)])
    return selected[:n_outfits]


def _method_tier_counts(
    *, fitb_count: int, random_count: int, price_tier_targets: dict[str, float]
) -> dict[str, dict[str, int]]:
    total = fitb_count + random_count
    desired = _desired_tier_counts(total, price_tier_targets)
    fitb = {tier: round(count * fitb_count / total) for tier, count in desired.items()}
    while sum(fitb.values()) != fitb_count:
        delta = fitb_count - sum(fitb.values())
        tier = (
            max(PRICE_TIER, key=lambda x: desired[x] - fitb[x])
            if delta > 0
            else max(fitb, key=lambda x: fitb[x])
        )
        fitb[tier] += 1 if delta > 0 else -1
    random_counts = {tier: desired[tier] - fitb[tier] for tier in PRICE_TIER}
    return {"fitb_beam": fitb, "random_scored": random_counts}


def _select_price_counts(
    candidates: list[OutfitRecord],
    *,
    tier_counts: dict[str, int],
    excluded_keys: set[tuple[str, ...]],
) -> list[OutfitRecord]:
    targets = {tier: max(0, count) for tier, count in tier_counts.items()}
    n_outfits = sum(targets.values())
    if n_outfits <= 0:
        return []
    if n_outfits == 0:
        return []
    ratios = {tier: float(count) for tier, count in targets.items()}
    selected = _select_price_balanced(
        candidates,
        n_outfits=n_outfits,
        price_tier_targets=ratios,
        excluded_keys=excluded_keys,
    )
    return selected


def _select_method_price_balanced(
    candidates: list[OutfitRecord],
    *,
    fitb_count: int,
    random_count: int,
    price_tier_targets: dict[str, float],
) -> list[OutfitRecord]:
    selected: list[OutfitRecord] = []
    seen: set[tuple[str, ...]] = set()
    method_tiers = _method_tier_counts(
        fitb_count=fitb_count, random_count=random_count, price_tier_targets=price_tier_targets
    )
    for method, tier_counts in method_tiers.items():
        method_candidates = [outfit for outfit in candidates if outfit.gen_method == method]
        part = _select_price_counts(method_candidates, tier_counts=tier_counts, excluded_keys=seen)
        selected.extend(part)
        seen.update(_combo_key(outfit) for outfit in part)
    if len(selected) < fitb_count + random_count:
        selected.extend(
            _select_price_balanced(
                candidates,
                n_outfits=fitb_count + random_count - len(selected),
                price_tier_targets=price_tier_targets,
                excluded_keys=seen,
            )
        )
    return selected


def build_outfit_records(
    items_by_category: dict[str, list[ItemRecord]],
    *,
    n_outfits: int,
    fitb_ratio: float = 0.70,
    score_threshold: float = 0.0,
    scorer: HeuristicOutfitScorer | None = None,
    price_tier_targets: dict[str, float] | None = None,
) -> list[OutfitRecord]:
    """Generate a mixed FITB/random outfit set and re-score all records.

    The default scorer is a deterministic baseline. Pass an OutfitTransformer-labse
    scorer adapter later without changing generation orchestration.
    """
    if n_outfits <= 0:
        return []
    scorer = scorer or HeuristicOutfitScorer()
    _ensure_item_embeddings(items_by_category, scorer)

    fitb_count = max(0, min(n_outfits, round(n_outfits * fitb_ratio)))
    random_count = max(0, n_outfits - fitb_count)
    if price_tier_targets is None:
        outfits = generate_fitb_beam(
            items_by_category,
            scorer,
            n_outfits=fitb_count,
            beam_size=3,
            top_k=max(5, fitb_count),
        )
        outfits.extend(generate_random_scored(items_by_category, scorer, n_candidates=random_count))
        rescored = rescore_outfits(outfits, scorer, score_threshold=score_threshold)
        rescored.sort(
            key=lambda outfit: (outfit.compatibility_score, outfit.outfit_id), reverse=True
        )
        return _renumber(rescored[:n_outfits])

    pool_size = max(n_outfits, n_outfits * 120)
    outfits = generate_fitb_beam(
        items_by_category,
        scorer,
        n_outfits=max(fitb_count, pool_size),
        beam_size=3,
        top_k=max(5, pool_size),
    )
    outfits.extend(
        generate_random_scored(items_by_category, scorer, n_candidates=max(random_count, pool_size))
    )
    rescored = rescore_outfits(outfits, scorer, score_threshold=score_threshold)
    selected = _select_method_price_balanced(
        rescored,
        fitb_count=fitb_count,
        random_count=random_count,
        price_tier_targets=price_tier_targets,
    )
    return _renumber(selected)


def outfits_to_frame(outfits: list[OutfitRecord]) -> pd.DataFrame:
    """Convert outfit records to a compact Parquet-friendly dataframe."""
    rows = []
    for outfit in outfits:
        rows.append(
            {
                "outfit_id": outfit.outfit_id,
                "schema_version": outfit.schema_version,
                "item_ids": json.dumps([item.item_id for item in outfit.items]),
                "categories": json.dumps([item.category for item in outfit.items]),
                "compatibility_score": outfit.compatibility_score,
                "price_total_vnd": outfit.price_total_vnd,
                "price_tier": outfit.price_tier,
                "has_vn_store": outfit.has_vn_store,
                "gen_method": outfit.gen_method,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "outfit_id",
            "schema_version",
            "item_ids",
            "categories",
            "compatibility_score",
            "price_total_vnd",
            "price_tier",
            "has_vn_store",
            "gen_method",
        ],
    )


def write_outfits(outfits: list[OutfitRecord], output_path: Path) -> None:
    """Write generated outfits to Parquet."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    outfits_to_frame(outfits).to_parquet(output_path, index=False)
