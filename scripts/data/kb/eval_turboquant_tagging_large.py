"""Large same-sample TurboQuant item/outfit tagging benchmark."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.tagging import _call_openai_compatible, sanitize_tag_payload
from outfitmatch.vocab import BODY_SHAPE, SEASON
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.eval_turboquant_tagging_large")
BODY_RELEVANT_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear"})
SEASON_RELEVANT_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear"})


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    """Deterministic item/outfit benchmark sample."""

    item_ids: list[str]
    outfit_ids: list[str]
    outfit_item_ids: dict[str, list[str]]


def parse_json_list(value: object) -> list[str]:
    """Parse a parquet string/list cell into a clean string list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(parsed, list):
        return [str(v).strip() for v in parsed if str(v).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity for enum tag lists; empty-empty is a perfect match."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 3)


def _ordered(values: set[str], vocab: tuple[str, ...]) -> list[str]:
    return [value for value in vocab if value in values]


def derive_outfit_tags(
    outfit_item_ids: list[str],
    item_tags: dict[str, dict[str, list[str]]],
    item_categories: dict[str, str],
    *,
    attr: str,
) -> list[str]:
    """Derive outfit body/season tags from item tags, matching assemble_record rules."""
    vocab = BODY_SHAPE if attr == "body_shapes_fit" else SEASON
    relevant = BODY_RELEVANT_CATEGORIES if attr == "body_shapes_fit" else SEASON_RELEVANT_CATEGORIES
    dress_sets = [
        set(item_tags.get(item_id, {}).get(attr, []))
        for item_id in outfit_item_ids
        if item_categories.get(item_id) == "dress" and item_tags.get(item_id, {}).get(attr, [])
    ]
    if dress_sets:
        return _ordered(set.union(*dress_sets), vocab)
    tag_sets = [
        set(item_tags.get(item_id, {}).get(attr, []))
        for item_id in outfit_item_ids
        if item_categories.get(item_id) in relevant and item_tags.get(item_id, {}).get(attr, [])
    ]
    if not tag_sets:
        return []
    shared = set.intersection(*tag_sets)
    if shared:
        return _ordered(shared, vocab)
    return _ordered(set.union(*tag_sets), vocab)


def build_sample(
    catalog: pd.DataFrame,
    outfits: pd.DataFrame,
    *,
    item_count: int,
    outfit_count: int,
    seed: int,
) -> BenchmarkSample:
    """Build a deterministic sample: sampled outfits first, then category-balanced fill."""
    if outfit_count <= 0 or item_count <= 0:
        raise ValueError("item_count and outfit_count must be positive")
    sampled_outfits = outfits.sample(n=min(outfit_count, len(outfits)), random_state=seed)
    outfit_item_ids = {
        str(row.outfit_id): parse_json_list(row.item_ids)
        for row in sampled_outfits.itertuples(index=False)
    }
    selected: list[str] = []
    seen: set[str] = set()
    for ids in outfit_item_ids.values():
        for item_id in ids:
            if item_id not in seen:
                seen.add(item_id)
                selected.append(item_id)
    if len(selected) > item_count:
        raise ValueError(
            f"{len(outfit_item_ids)} outfits require {len(selected)} unique items, "
            f"which exceeds item_count={item_count}"
        )
    catalog = catalog.copy()
    catalog["_tagged"] = (
        catalog.get("body_shapes_fit", "").astype(str).str.len().gt(2)
        | catalog.get("season", "").astype(str).str.len().gt(2)
        | catalog.get("stylist_notes_vi", "").astype(str).str.strip().ne("")
    )
    remaining = catalog[catalog["_tagged"] & ~catalog["item_id"].astype(str).isin(seen)]
    by_category: dict[str, list[str]] = defaultdict(list)
    for row in remaining.sample(frac=1, random_state=seed).itertuples(index=False):
        by_category[str(row.category)].append(str(row.item_id))
    categories = sorted(by_category)
    cat_index = 0
    while len(selected) < item_count and categories:
        category = categories[cat_index % len(categories)]
        bucket = by_category[category]
        if bucket:
            item_id = bucket.pop()
            if item_id not in seen:
                seen.add(item_id)
                selected.append(item_id)
        categories = [cat for cat in categories if by_category[cat]]
        cat_index += 1
    if len(selected) < item_count:
        raise ValueError(f"Only selected {len(selected)} items; requested {item_count}")
    return BenchmarkSample(
        item_ids=selected,
        outfit_ids=list(outfit_item_ids),
        outfit_item_ids=outfit_item_ids,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_items(
    items: dict[str, Any],
    item_ids: list[str],
    *,
    model_id: str,
    model_label: str,
    mode: str,
    output_path: Path,
    force: bool,
) -> list[dict[str, Any]]:
    """Run or resume item-level OpenAI-compatible tagging benchmark."""
    if force and output_path.exists():
        output_path.unlink()
    done = {str(record.get("item_id")) for record in _read_jsonl(output_path)}

    for index, item_id in enumerate(item_ids, 1):
        if item_id in done:
            continue
        item = items[item_id]
        ref_body = list(getattr(item, "body_shapes_fit", []) or [])
        ref_season = list(getattr(item, "season", []) or [])
        record: dict[str, Any] = {
            "item_id": item.item_id,
            "category": item.category,
            "gender": item.gender,
            "title_vi": item.store.get("title_vi") or "",
            "provider": "llama.cpp-turboquant",
            "model": model_label,
            "mode": mode,
            "reference_body_shapes_fit": ref_body,
            "reference_season": ref_season,
            "reference_stylist_notes_vi": getattr(item, "stylist_notes_vi", ""),
        }
        start = time.perf_counter()
        try:
            raw = _call_openai_compatible(item, model=model_id)
            tagged = sanitize_tag_payload(raw)
            body = tagged.body_shapes_fit
            season = tagged.season
            note = tagged.stylist_notes_vi
            record.update(
                {
                    "valid_json": True,
                    "ok": bool(body and season and note.strip()),
                    "body_shapes_fit": body,
                    "season": season,
                    "stylist_notes_vi": note,
                    "body_jaccard_vs_current": jaccard(body, ref_body),
                    "season_jaccard_vs_current": jaccard(season, ref_season),
                }
            )
        except Exception as exc:  # pragma: no cover - live backend failure path
            record.update(
                {
                    "valid_json": False,
                    "ok": False,
                    "body_shapes_fit": [],
                    "season": [],
                    "stylist_notes_vi": "",
                    "body_jaccard_vs_current": 0.0,
                    "season_jaccard_vs_current": 0.0,
                    "errors": [{"error": str(exc), "traceback": traceback.format_exc(limit=4)}],
                }
            )
        record["latency_s"] = round(time.perf_counter() - start, 3)
        _append_jsonl(output_path, record)
        logger.info(
            "%d/%d %s ok=%s valid=%s latency=%.3fs body=%s season=%s",
            index,
            len(item_ids),
            item_id,
            record["ok"],
            record["valid_json"],
            record["latency_s"],
            record["body_shapes_fit"],
            record["season"],
        )

    return _read_jsonl(output_path)


def summarize_items(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize item-level records."""
    latencies = [float(r.get("latency_s") or 0) for r in records]
    valid = [r for r in records if r.get("valid_json")]
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({str(r.get("category")) for r in records}):
        rows = [r for r in records if str(r.get("category")) == category]
        by_category[category] = {
            "n": len(rows),
            "complete_rate": round(sum(bool(r.get("ok")) for r in rows) / len(rows), 3),
            "avg_body_jaccard": round(
                sum(float(r.get("body_jaccard_vs_current") or 0) for r in rows) / len(rows),
                3,
            ),
            "avg_season_jaccard": round(
                sum(float(r.get("season_jaccard_vs_current") or 0) for r in rows) / len(rows),
                3,
            ),
        }
    return {
        "sample_size": len(records),
        "valid_json": sum(bool(r.get("valid_json")) for r in records),
        "valid_json_rate": round(len(valid) / len(records), 3) if records else 0,
        "ok_complete": sum(bool(r.get("ok")) for r in records),
        "complete_rate": round(sum(bool(r.get("ok")) for r in records) / len(records), 3)
        if records
        else 0,
        "with_body_shape": sum(bool(r.get("body_shapes_fit")) for r in valid),
        "with_season": sum(bool(r.get("season")) for r in valid),
        "with_note": sum(bool(str(r.get("stylist_notes_vi") or "").strip()) for r in valid),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else 0,
        "p95_latency_s": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3)
        if latencies
        else 0,
        "avg_body_jaccard_vs_current_catalog_tags": round(
            sum(float(r.get("body_jaccard_vs_current") or 0) for r in valid) / len(valid), 3
        )
        if valid
        else 0,
        "avg_season_jaccard_vs_current_catalog_tags": round(
            sum(float(r.get("season_jaccard_vs_current") or 0) for r in valid) / len(valid), 3
        )
        if valid
        else 0,
        "by_category": by_category,
    }


def summarize_outfits(
    records: list[dict[str, Any]],
    sample: BenchmarkSample,
    item_categories: dict[str, str],
) -> dict[str, Any]:
    """Summarize outfit-level tags derived from benchmark item predictions."""
    pred_tags = {
        str(r["item_id"]): {
            "body_shapes_fit": list(r.get("body_shapes_fit") or []),
            "season": list(r.get("season") or []),
        }
        for r in records
        if r.get("valid_json")
    }
    ref_tags = {
        str(r["item_id"]): {
            "body_shapes_fit": list(r.get("reference_body_shapes_fit") or []),
            "season": list(r.get("reference_season") or []),
        }
        for r in records
    }
    outfit_rows = []
    relevant_for_outfit = BODY_RELEVANT_CATEGORIES | SEASON_RELEVANT_CATEGORIES
    for outfit_id in sample.outfit_ids:
        ids = sample.outfit_item_ids[outfit_id]
        required_ids = [
            item_id for item_id in ids if item_categories.get(item_id) in relevant_for_outfit
        ]
        if not all(item_id in pred_tags for item_id in required_ids):
            continue
        pred_body = derive_outfit_tags(ids, pred_tags, item_categories, attr="body_shapes_fit")
        pred_season = derive_outfit_tags(ids, pred_tags, item_categories, attr="season")
        ref_body = derive_outfit_tags(ids, ref_tags, item_categories, attr="body_shapes_fit")
        ref_season = derive_outfit_tags(ids, ref_tags, item_categories, attr="season")
        outfit_rows.append(
            {
                "outfit_id": outfit_id,
                "item_ids": ids,
                "body_shapes_fit": pred_body,
                "season": pred_season,
                "reference_body_shapes_fit": ref_body,
                "reference_season": ref_season,
                "body_jaccard_vs_current": jaccard(pred_body, ref_body),
                "season_jaccard_vs_current": jaccard(pred_season, ref_season),
                "complete": bool(pred_body and pred_season),
            }
        )
    if not outfit_rows:
        return {"sample_size": 0, "rows": []}
    return {
        "sample_size": len(outfit_rows),
        "complete": sum(bool(r["complete"]) for r in outfit_rows),
        "complete_rate": round(sum(bool(r["complete"]) for r in outfit_rows) / len(outfit_rows), 3),
        "avg_body_jaccard_vs_current_catalog_tags": round(
            sum(float(r["body_jaccard_vs_current"]) for r in outfit_rows) / len(outfit_rows),
            3,
        ),
        "avg_season_jaccard_vs_current_catalog_tags": round(
            sum(float(r["season_jaccard_vs_current"]) for r in outfit_rows) / len(outfit_rows),
            3,
        ),
        "rows": outfit_rows,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Large TurboQuant tagging benchmark")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument(
        "--outfits", type=Path, default=Path("data/custom/outfits/generated_outfits.parquet")
    )
    parser.add_argument("--item-count", type=int, default=500)
    parser.add_argument("--outfit-count", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    catalog_df = pd.read_parquet(args.catalog)
    outfits_df = pd.read_parquet(args.outfits)
    sample = build_sample(
        catalog_df,
        outfits_df,
        item_count=args.item_count,
        outfit_count=args.outfit_count,
        seed=args.seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sample_path = args.output_dir / "sample.json"
    sample_path.write_text(
        json.dumps(
            {
                "item_ids": sample.item_ids,
                "outfit_ids": sample.outfit_ids,
                "outfit_item_ids": sample.outfit_item_ids,
                "item_count": len(sample.item_ids),
                "outfit_count": len(sample.outfit_ids),
                "seed": args.seed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    items = {
        item.item_id: item
        for item in load_catalog_items(args.catalog, args.links, in_stock_only=False)
    }
    item_categories = {item_id: item.category for item_id, item in items.items()}
    output_path = args.output_dir / f"{args.mode}.jsonl"
    records = run_items(
        items,
        sample.item_ids,
        model_id=args.model_id,
        model_label=args.model_label,
        mode=args.mode,
        output_path=output_path,
        force=args.force,
    )
    item_summary = summarize_items(records)
    outfit_summary = summarize_outfits(records, sample, item_categories)
    summary = {
        "model": args.model_label,
        "mode": args.mode,
        "item_summary": item_summary,
        "outfit_summary": {k: v for k, v in outfit_summary.items() if k != "rows"},
        "sample": {
            "item_count": len(sample.item_ids),
            "outfit_count": len(sample.outfit_ids),
            "seed": args.seed,
            "sample_path": str(sample_path),
        },
        "jsonl": str(output_path),
        "reference_warning": "current catalog tags are pseudo-reference, not human gold labels",
    }
    (args.output_dir / f"{args.mode}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / f"{args.mode}_outfits.json").write_text(
        json.dumps(outfit_summary.get("rows", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("summary=%s", args.output_dir / f"{args.mode}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
