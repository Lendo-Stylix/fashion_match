"""Build a deterministic grounded scenario bank from real catalog items.

Phase B of the grounded stylist dataset pipeline starts from runtime-compatible
scenario metadata, not raw LLM generations. This script converts real catalog
items into small, reproducible scenario rows that later generation scripts can
expand into ChatML dialogues.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution path
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    src_root_str = str(repo_root / "src")
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.schema import ItemRecord
from outfitmatch.vocab import BODY_SHAPE, OCCASION, SKIN_TONE, STYLE, formalities_for_occasion

DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_grounded_v2/scenario_bank")
SEED_CATEGORIES = frozenset({"top", "dress"})
GROUNDED_TARGET_TASK_COUNTS: dict[str, int] = {
    "tool_calling_grounded": 900,
    "recommend_explain_grounded": 700,
    "ask_missing_info_grounded": 350,
    "no_result_or_relax_constraints": 250,
    "polite_decline_anti_hallucination": 150,
    "multi_turn_grounded": 150,
    "body_fit_grounded": 300,
}
SCENARIO_TASK_ORDER: tuple[str, ...] = tuple(GROUNDED_TARGET_TASK_COUNTS)


def _item_price(item: ItemRecord) -> int:
    return int(item.store.get("price_vnd") or 0)


def _item_snapshot(item: ItemRecord) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "title_vi": str(item.store.get("title_vi") or ""),
        "category": item.category,
        "formality": item.formality,
        "price_vnd": _item_price(item),
        "colors": [str(color) for color in item.store.get("colors", []) if str(color)],
        "product_url": str(item.store.get("product_url") or ""),
    }


def _occasion_seed_items(items: list[ItemRecord], occasion: str) -> list[ItemRecord]:
    allowed_formalities = formalities_for_occasion(occasion)
    seeds = [
        item
        for item in items
        if item.category in SEED_CATEGORIES
        and item.formality in allowed_formalities
        and bool(item.store.get("in_stock"))
        and bool(item.store.get("product_url"))
    ]
    return sorted(seeds, key=lambda item: (item.item_id, _item_price(item)))


def _scenario_payload(
    *,
    scenario_id: str,
    task_type: str,
    request: dict[str, Any],
    user_profile: dict[str, Any],
    seed_item: ItemRecord | None,
    candidate_items: list[ItemRecord],
    expected_behavior: dict[str, bool],
    target_occasion: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "task_type": task_type,
        "request": request,
        "user_profile": user_profile,
        "seed_item_id": seed_item.item_id if seed_item is not None else None,
        "seed_item": _item_snapshot(seed_item) if seed_item is not None else None,
        "candidate_item_ids": [item.item_id for item in candidate_items],
        "candidate_items": [_item_snapshot(item) for item in candidate_items],
        "expected_behavior": expected_behavior,
        "target_occasion": target_occasion,
    }


def _request_payload(
    *,
    rng: random.Random,
    occasion: str | None,
    price_max: int,
    example_index: int = 0,
) -> dict[str, Any]:
    return {
        "occasion": occasion,
        "style": STYLE[example_index % len(STYLE)],
        "body_shape": BODY_SHAPE[example_index % len(BODY_SHAPE)],
        "skin_tone": SKIN_TONE[example_index % len(SKIN_TONE)],
        "price_max": price_max + (example_index % 5) * 50_000,
        "exclude_colors": [],
    }


def _resolve_task_counts(
    *,
    max_examples_per_task: int,
    counts_by_task: dict[str, int] | None,
) -> dict[str, int]:
    if counts_by_task is None:
        if max_examples_per_task <= 0:
            return {}
        return {task_type: max_examples_per_task for task_type in SCENARIO_TASK_ORDER}

    unknown = sorted(set(counts_by_task) - set(SCENARIO_TASK_ORDER))
    if unknown:
        raise ValueError(f"Unsupported grounded task types: {', '.join(unknown)}")
    return {
        task_type: max(0, int(counts_by_task.get(task_type, 0)))
        for task_type in SCENARIO_TASK_ORDER
    }


def _build_one_scenario(
    *,
    task_type: str,
    example_index: int,
    scenario_id: str,
    rng: random.Random,
    tool_occasion: str,
    secondary_occasion: str,
    ask_seed_pool: list[ItemRecord],
    secondary_pool: list[ItemRecord],
    tool_candidates: list[ItemRecord],
) -> dict[str, Any]:
    if task_type == "tool_calling_grounded":
        tool_seed = tool_candidates[example_index % len(tool_candidates)]
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=tool_occasion,
                example_index=example_index,
                price_max=max(_item_price(tool_seed), 300_000),
            ),
            user_profile={
                "height_cm": 160 + (example_index % 10),
                "weight_kg": 52 + (example_index % 8),
            },
            seed_item=tool_seed,
            candidate_items=tool_candidates,
            expected_behavior={
                "should_call_tool": True,
                "should_ask_followup": False,
                "should_decline": False,
                "should_relax_constraints": False,
            },
        )

    if task_type == "ask_missing_info_grounded":
        ask_seed = ask_seed_pool[example_index % len(ask_seed_pool)]
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=None,
                price_max=max(_item_price(ask_seed), 300_000),
                example_index=example_index,
            ),
            user_profile={
                "height_cm": 158 + (example_index % 10),
                "weight_kg": 50 + (example_index % 8),
            },
            seed_item=ask_seed,
            candidate_items=ask_seed_pool[:3],
            expected_behavior={
                "should_call_tool": False,
                "should_ask_followup": True,
                "should_decline": False,
                "should_relax_constraints": False,
            },
            target_occasion=tool_occasion,
        )

    if task_type == "no_result_or_relax_constraints":
        no_result_seed = secondary_pool[example_index % len(secondary_pool)]
        min_price = min(_item_price(item) for item in secondary_pool)
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=secondary_occasion,
                price_max=max(0, min_price - 1),
                example_index=example_index,
            ),
            user_profile={
                "height_cm": 162 + (example_index % 10),
                "weight_kg": 54 + (example_index % 8),
            },
            seed_item=no_result_seed,
            candidate_items=[],
            expected_behavior={
                "should_call_tool": False,
                "should_ask_followup": False,
                "should_decline": False,
                "should_relax_constraints": True,
            },
        )

    if task_type == "recommend_explain_grounded":
        explain_seed = tool_candidates[example_index % len(tool_candidates)]
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=tool_occasion,
                example_index=example_index,
                price_max=max(_item_price(explain_seed), 300_000),
            ),
            user_profile={
                "height_cm": 159 + (example_index % 10),
                "weight_kg": 51 + (example_index % 8),
            },
            seed_item=explain_seed,
            candidate_items=tool_candidates,
            expected_behavior={
                "should_call_tool": False,
                "should_ask_followup": False,
                "should_decline": False,
                "should_relax_constraints": False,
            },
        )

    if task_type == "polite_decline_anti_hallucination":
        decline_seed = tool_candidates[example_index % len(tool_candidates)]
        request = _request_payload(
            rng=rng,
            occasion=tool_occasion,
            price_max=max(_item_price(decline_seed), 300_000),
            example_index=example_index,
        )
        request["requested_outfit_id"] = f"OUTFIT_FAKE_{example_index + 1:03d}"
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=request,
            user_profile={
                "height_cm": 164 + (example_index % 10),
                "weight_kg": 56 + (example_index % 8),
            },
            seed_item=decline_seed,
            candidate_items=[],
            expected_behavior={
                "should_call_tool": False,
                "should_ask_followup": False,
                "should_decline": True,
                "should_relax_constraints": False,
            },
        )

    if task_type == "multi_turn_grounded":
        multi_seed = secondary_pool[example_index % len(secondary_pool)]
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=None,
                price_max=max(_item_price(multi_seed), 300_000),
                example_index=example_index,
            ),
            user_profile={
                "height_cm": 161 + (example_index % 10),
                "weight_kg": 53 + (example_index % 8),
            },
            seed_item=multi_seed,
            candidate_items=secondary_pool[:3],
            expected_behavior={
                "should_call_tool": True,
                "should_ask_followup": True,
                "should_decline": False,
                "should_relax_constraints": False,
            },
            target_occasion=secondary_occasion,
        )

    if task_type == "body_fit_grounded":
        body_seed = tool_candidates[(example_index + 1) % len(tool_candidates)]
        return _scenario_payload(
            scenario_id=scenario_id,
            task_type=task_type,
            request=_request_payload(
                rng=rng,
                occasion=tool_occasion,
                example_index=example_index,
                price_max=max(_item_price(body_seed), 300_000),
            ),
            user_profile={
                "height_cm": 157 + (example_index % 10),
                "weight_kg": 49 + (example_index % 8),
            },
            seed_item=body_seed,
            candidate_items=tool_candidates,
            expected_behavior={
                "should_call_tool": False,
                "should_ask_followup": False,
                "should_decline": False,
                "should_relax_constraints": False,
            },
        )

    raise ValueError(f"Unsupported task_type: {task_type}")


def build_grounded_scenario_bank(
    items: list[ItemRecord],
    *,
    seed: int = 42,
    max_examples_per_task: int = 1,
    counts_by_task: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Build a deterministic grounded scenario bank from real catalog items."""
    task_counts = _resolve_task_counts(
        max_examples_per_task=max_examples_per_task,
        counts_by_task=counts_by_task,
    )
    if not task_counts:
        return []

    available: dict[str, list[ItemRecord]] = {}
    for occasion in OCCASION:
        seeds = _occasion_seed_items(items, occasion)
        if seeds:
            available[occasion] = seeds
    if not available:
        return []

    occasions = list(available)
    tool_occasion = occasions[0]
    secondary_occasion = (
        "travel"
        if "travel" in available
        else (occasions[1] if len(occasions) > 1 else occasions[0])
    )
    ask_seed_pool = available[tool_occasion]
    secondary_pool = available[secondary_occasion]
    tool_candidates = available[tool_occasion][:3]

    scenarios: list[dict[str, Any]] = []
    scenario_index = 1
    rng = random.Random(seed)
    for task_type in SCENARIO_TASK_ORDER:
        count = task_counts.get(task_type, 0)
        for example_index in range(count):
            scenarios.append(
                _build_one_scenario(
                    task_type=task_type,
                    example_index=example_index,
                    scenario_id=f"SC_{scenario_index:06d}",
                    rng=rng,
                    tool_occasion=tool_occasion,
                    secondary_occasion=secondary_occasion,
                    ask_seed_pool=ask_seed_pool,
                    secondary_pool=secondary_pool,
                    tool_candidates=tool_candidates,
                )
            )
            scenario_index += 1

    return scenarios


def summarize_scenario_bank(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic summary stats for a grounded scenario bank."""
    task_counts = Counter(str(scenario["task_type"]) for scenario in scenarios)
    occasion_counts = Counter(
        str(occasion)
        for scenario in scenarios
        if (occasion := scenario.get("request", {}).get("occasion")) is not None
    )
    return {
        "total_scenarios": len(scenarios),
        "task_counts": dict(sorted(task_counts.items())),
        "occasion_counts": dict(sorted(occasion_counts.items())),
    }


def write_scenario_bank(output_dir: Path, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Write scenario JSONL plus summary manifest to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = output_dir / "scenario_bank.jsonl"
    with scenario_path.open("w", encoding="utf-8") as handle:
        for scenario in scenarios:
            handle.write(json.dumps(scenario, ensure_ascii=False) + "\n")
    manifest = summarize_scenario_bank(scenarios)
    manifest_path = output_dir / "scenario_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "scenario_bank": str(scenario_path),
        "manifest": str(manifest_path),
        **manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_path", type=Path)
    parser.add_argument("links_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-examples-per-task", type=int, default=1)
    parser.add_argument(
        "--target-profile",
        choices=["grounded_v1"],
        default=None,
        help="Use the plan-aligned 2800-row grounded task mix.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = load_catalog_items(args.catalog_path, args.links_path)
    counts_by_task = GROUNDED_TARGET_TASK_COUNTS if args.target_profile == "grounded_v1" else None
    scenarios = build_grounded_scenario_bank(
        items,
        seed=args.seed,
        max_examples_per_task=args.max_examples_per_task,
        counts_by_task=counts_by_task,
    )
    result = write_scenario_bank(args.output_dir, scenarios)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
