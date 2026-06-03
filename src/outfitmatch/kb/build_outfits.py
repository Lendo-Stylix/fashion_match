"""Build outfit records from grouped catalog items.

DEPRECATED (graph KB): retrieval now uses graph traversal (`kb/graph.py`,
`kb/traversal.py`, `retrieval.py`). This materialized-outfit builder stays
temporary for legacy comparison and will be removed in a separate cleanup after
the graph pipeline is stable end-to-end.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from outfitmatch.kb.embedding import extract_item_embeddings
from outfitmatch.kb.generation import generate_fitb_beam, generate_random_scored
from outfitmatch.kb.schema import ItemRecord, OutfitRecord
from outfitmatch.kb.scoring import HeuristicOutfitScorer, rescore_outfits
from outfitmatch.vocab import PRICE_TIER

DEFAULT_PRICE_TIER_TARGETS: dict[str, float] = {"budget": 0.20, "mid": 0.50, "premium": 0.30}
DEFAULT_GENDER_TARGETS: dict[str, float] = {"women": 0.55, "men": 0.45}
DEFAULT_STORE_SLOT_TARGETS: dict[str, float] = {
    "yody_vn": 0.45,
    "aristino_vn": 0.22,
    "rubies": 0.16,
    "canifa_vn": 0.07,
    "dirtycoins": 0.05,
    "huelleyrose": 0.03,
}


@dataclass(frozen=True)
class OutfitDiversityConfig:
    """Soft/hard constraints used when selecting materialized outfit candidates.

    Price-tier and generation-method quotas remain exact; these constraints reduce
    repeated hero items and steer the final KB toward healthier gender, dress, and
    store coverage without allowing invalid gender/formality/category combos.
    """

    max_item_reuse: int | None = 45
    target_gender_shares: dict[str, float] = field(
        default_factory=lambda: DEFAULT_GENDER_TARGETS.copy()
    )
    target_dress_share: float = 0.10
    max_dress_share: float | None = 0.18
    max_gender_shares: dict[str, float] = field(
        default_factory=lambda: {"women": 0.62, "men": 0.62}
    )
    target_store_slot_shares: dict[str, float] = field(
        default_factory=lambda: DEFAULT_STORE_SLOT_TARGETS.copy()
    )
    max_store_slot_shares: dict[str, float] = field(
        default_factory=lambda: {"yody_vn": 0.60, "rubies": 0.25, "aristino_vn": 0.35}
    )
    expected_slots_per_outfit: float = 3.35
    max_scan_per_pick: int = 12_000


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


def _store_ids(outfit: OutfitRecord) -> list[str]:
    return [str(item.store.get("store_id") or "") for item in outfit.items]


def _has_dress(outfit: OutfitRecord) -> bool:
    return any(item.category == "dress" for item in outfit.items)


def _normalised_targets(targets: dict[str, float]) -> dict[str, float]:
    positive = {key: max(0.0, float(value)) for key, value in targets.items()}
    total = sum(positive.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in positive.items()}


def _target_bonus(value: str, counts: Counter[str], targets: dict[str, float], total: int) -> float:
    if not targets:
        return 0.0
    target = targets.get(value, 0.0)
    current = counts[value] / total if total else 0.0
    return max(0.0, target - current)


def _selection_schedule(group_counts: dict[tuple[str, str], int]) -> list[tuple[str, str]]:
    remaining = Counter({group: count for group, count in group_counts.items() if count > 0})
    schedule: list[tuple[str, str]] = []
    while remaining:
        for group, _ in sorted(remaining.items(), key=lambda item: (-item[1], item[0])):
            schedule.append(group)
            remaining[group] -= 1
            if remaining[group] <= 0:
                del remaining[group]
    return schedule


def _within_share_cap(current: int, added: int, cap: float, denominator: int) -> bool:
    return (current + added) <= int(cap * denominator + 0.999999)


def _passes_diversity_caps(
    outfit: OutfitRecord,
    *,
    expected_outfits: int,
    expected_slots: int,
    gender_counts: Counter[str],
    store_counts: Counter[str],
    item_use: Counter[str],
    dress_count: int,
    config: OutfitDiversityConfig,
) -> bool:
    if (diversity_max := config.max_item_reuse) and any(
        item_use[item.item_id] >= diversity_max for item in outfit.items
    ):
        return False
    if (
        config.max_dress_share is not None
        and _has_dress(outfit)
        and not _within_share_cap(dress_count, 1, config.max_dress_share, expected_outfits)
    ):
        return False
    gender_cap = config.max_gender_shares.get(outfit.gender)
    if gender_cap is not None and not _within_share_cap(
        gender_counts[outfit.gender], 1, gender_cap, expected_outfits
    ):
        return False
    store_additions = Counter(_store_ids(outfit))
    for store_id, added in store_additions.items():
        store_cap = config.max_store_slot_shares.get(store_id)
        if store_cap is not None and not _within_share_cap(
            store_counts[store_id], added, store_cap, expected_slots
        ):
            return False
    return True


def _candidate_utility(
    outfit: OutfitRecord,
    *,
    selected_count: int,
    selected_slots: int,
    gender_counts: Counter[str],
    store_counts: Counter[str],
    item_use: Counter[str],
    dress_count: int,
    config: OutfitDiversityConfig,
) -> float:
    gender_targets = _normalised_targets(config.target_gender_shares)
    store_targets = _normalised_targets(config.target_store_slot_shares)
    utility = outfit.compatibility_score
    utility += 0.30 * _target_bonus(outfit.gender, gender_counts, gender_targets, selected_count)

    current_dress_share = dress_count / selected_count if selected_count else 0.0
    if _has_dress(outfit):
        utility += 0.25 * max(0.0, config.target_dress_share - current_dress_share)
    elif current_dress_share < config.target_dress_share:
        utility -= 0.08 * (config.target_dress_share - current_dress_share)

    store_bonus = 0.0
    store_penalty = 0.0
    for store_id in _store_ids(outfit):
        current = store_counts[store_id] / selected_slots if selected_slots else 0.0
        target = store_targets.get(store_id, 0.0)
        store_bonus += max(0.0, target - current)
        store_penalty += max(0.0, current - target)
    slots = max(1, len(outfit.items))
    utility += 0.22 * (store_bonus / slots)
    utility -= 0.28 * (store_penalty / slots)
    utility -= 0.015 * sum(item_use[item.item_id] for item in outfit.items)
    return utility


def _select_method_price_diverse(
    candidates: list[OutfitRecord],
    *,
    fitb_count: int,
    random_count: int,
    price_tier_targets: dict[str, float],
    diversity_config: OutfitDiversityConfig,
) -> list[OutfitRecord]:
    method_tiers = _method_tier_counts(
        fitb_count=fitb_count, random_count=random_count, price_tier_targets=price_tier_targets
    )
    group_counts = {
        (method, tier): count
        for method, tiers in method_tiers.items()
        for tier, count in tiers.items()
        if count > 0
    }
    by_group: dict[tuple[str, str], list[OutfitRecord]] = defaultdict(list)
    for outfit in candidates:
        by_group[(outfit.gen_method, outfit.price_tier)].append(outfit)
    for group in list(by_group):
        by_group[group].sort(
            key=lambda outfit: (
                outfit.compatibility_score,
                -outfit.price_total_vnd,
                outfit.outfit_id,
            ),
            reverse=True,
        )

    selected: list[OutfitRecord] = []
    seen: set[tuple[str, ...]] = set()
    item_use: Counter[str] = Counter()
    gender_counts: Counter[str] = Counter()
    store_counts: Counter[str] = Counter()
    dress_count = 0
    selected_slots = 0
    expected = fitb_count + random_count
    expected_slots = max(1, round(expected * diversity_config.expected_slots_per_outfit))

    for group in _selection_schedule(group_counts):
        pool = by_group.get(group, [])
        best: OutfitRecord | None = None
        best_utility = float("-inf")
        scanned = 0
        for outfit in pool:
            key = _combo_key(outfit)
            if key in seen:
                continue
            if not _passes_diversity_caps(
                outfit,
                expected_outfits=expected,
                expected_slots=expected_slots,
                gender_counts=gender_counts,
                store_counts=store_counts,
                item_use=item_use,
                dress_count=dress_count,
                config=diversity_config,
            ):
                continue
            utility = _candidate_utility(
                outfit,
                selected_count=len(selected),
                selected_slots=selected_slots,
                gender_counts=gender_counts,
                store_counts=store_counts,
                item_use=item_use,
                dress_count=dress_count,
                config=diversity_config,
            )
            if utility > best_utility:
                best = outfit
                best_utility = utility
            scanned += 1
            if scanned >= diversity_config.max_scan_per_pick:
                break
        if best is None:
            # Quotas are exact, but item reuse should remain hard whenever possible.
            # Relax only the aggregate share caps (gender/store/dress) for this pick.
            for outfit in pool:
                key = _combo_key(outfit)
                if key in seen:
                    continue
                if diversity_config.max_item_reuse is not None and any(
                    item_use[item.item_id] >= diversity_config.max_item_reuse
                    for item in outfit.items
                ):
                    continue
                best = outfit
                break
        if best is None:
            # Last-resort fallback: keep generation from under-filling when a tiny
            # group is exhausted, then surface the violation in the quality report.
            for outfit in pool:
                key = _combo_key(outfit)
                if key not in seen:
                    best = outfit
                    break
        if best is None:
            continue
        selected.append(best)
        seen.add(_combo_key(best))
        gender_counts[best.gender] += 1
        if _has_dress(best):
            dress_count += 1
        for item in best.items:
            item_use[item.item_id] += 1
            store_counts[str(item.store.get("store_id") or "")] += 1
        selected_slots += len(best.items)

    if len(selected) < expected:
        seen.update(_combo_key(outfit) for outfit in selected)
        selected.extend(
            _select_price_balanced(
                candidates,
                n_outfits=expected - len(selected),
                price_tier_targets=price_tier_targets,
                excluded_keys=seen,
            )
        )
    return selected[:expected]


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
    diversity_config: OutfitDiversityConfig | None = None,
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
    if diversity_config is not None:
        selected = _select_method_price_diverse(
            rescored,
            fitb_count=fitb_count,
            random_count=random_count,
            price_tier_targets=price_tier_targets,
            diversity_config=diversity_config,
        )
    else:
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
                "gender": outfit.gender,
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
            "gender",
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
