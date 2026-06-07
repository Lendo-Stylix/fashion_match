"""Audit deterministic outfit-level tags derived from graph traversal.

Read-only report generator for OutfitRecord metadata:
- occasion
- style
- body_shapes_fit
- season
- gender
- completion quality (shoeless core-valid vs complete-with-shoes)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from outfitmatch.kb.assemble_record import to_outfit_record
from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.generation import _combo_gender
from outfitmatch.kb.graph_store import EDGES_PARQUET, load_graph
from outfitmatch.kb.schema import OutfitRecord
from outfitmatch.kb.traversal import AssemblyConfig, assemble_outfits
from outfitmatch.vocab import (
    BODY_SHAPE_SET,
    FORMALITY_RANK,
    FORMALITY_RELEVANT_CATEGORIES,
    GENDER_SET,
    OCCASION_SET,
    PRICE_TIER_SET,
    SEASON_SET,
    STYLE_SET,
    occasions_for_formality,
    validate_enum_values,
)
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.audit_outfit_tags")

_MAIN_GARMENT_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear"})
_ALLOWED_OUTFIT_CATEGORIES = frozenset(
    {"top", "bottom", "dress", "shoes", "outerwear", "bag", "accessory"}
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit outfit-level metadata quality")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--edges", type=Path, default=EDGES_PARQUET)
    parser.add_argument("--out-dir", type=Path, default=Path("data/reports/outfit_tagging_quality"))
    parser.add_argument(
        "--seeds",
        type=int,
        default=300,
        help="Max anchor seeds to sweep (0 = no cap / full sweep).",
    )
    parser.add_argument("--occasion", type=str, default="", help="Optional occasion seed filter")
    parser.add_argument("--beam", type=int, default=3)
    parser.add_argument("--max-optional", type=int, default=3)
    parser.add_argument("--max-outfits", type=int, default=1000)
    parser.add_argument("--sample-per-shape", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _seed_ids(items: list[Any], *, occasion: str | None, limit: int) -> list[str]:
    if occasion and occasion not in OCCASION_SET:
        raise ValueError(f"unknown occasion={occasion}")

    target_formalities: set[str] | None = None
    if occasion:
        target_formalities = {
            band for band in FORMALITY_RANK if occasion in set(occasions_for_formality(band))
        }

    seed_ids: list[str] = []
    for item in items:
        if item.category not in {"top", "dress"}:
            continue
        if target_formalities is not None and item.formality not in target_formalities:
            continue
        seed_ids.append(item.item_id)
        if limit and len(seed_ids) >= limit:
            break
    return seed_ids


def _collect_outfits(
    *,
    catalog: Path,
    links: Path,
    edges: Path,
    seeds: int,
    occasion: str,
    beam: int,
    max_optional: int,
    max_outfits: int,
) -> list[OutfitRecord]:
    items = load_catalog_items(catalog, links, genders={"men", "women", "unisex"})
    graph = load_graph(edges, items=items)
    seed_ids = _seed_ids(items, occasion=occasion or None, limit=seeds)
    assembled = assemble_outfits(
        graph,
        seed_ids,
        config=AssemblyConfig(beam=beam, max_optional=max_optional),
    )
    if max_outfits > 0:
        assembled = assembled[:max_outfits]
    return [
        to_outfit_record(outfit.items, outfit.score, index=index)
        for index, outfit in enumerate(assembled, start=1)
    ]


def _core_shape(categories: list[str]) -> str:
    values = set(categories)
    if not values.issubset(_ALLOWED_OUTFIT_CATEGORIES):
        return "invalid"
    has_dress = "dress" in values
    has_top = "top" in values
    has_bottom = "bottom" in values
    has_shoes = "shoes" in values
    if has_dress and not has_top and not has_bottom:
        return "dress+shoes" if has_shoes else "dress"
    if has_top and has_bottom and not has_dress:
        return "top+bottom+shoes" if has_shoes else "top+bottom"
    return "invalid"


def _series_top_tag(series: pd.Series) -> str:
    exploded = series.explode().dropna()
    exploded = exploded[exploded.astype(str).str.strip() != ""]
    if exploded.empty:
        return ""
    return str(exploded.value_counts().index[0])


def _normalize_outfits(outfits: list[OutfitRecord]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    invalid_rows: list[dict[str, object]] = []

    for outfit in outfits:
        categories = [str(item.category) for item in outfit.items]
        item_ids = [str(item.item_id) for item in outfit.items]
        core_shape = _core_shape(categories)
        has_shoes = "shoes" in set(categories)
        is_complete = core_shape in {"dress+shoes", "top+bottom+shoes"}

        valid_occasion, invalid_occasion = validate_enum_values(outfit.occasion, OCCASION_SET)
        valid_style, invalid_style = validate_enum_values(outfit.style, STYLE_SET)
        valid_body, invalid_body = validate_enum_values(outfit.body_shapes_fit, BODY_SHAPE_SET)
        valid_season, invalid_season = validate_enum_values(outfit.season, SEASON_SET)

        if outfit.schema_version != "3.1":
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "schema_version",
                    "reason": "invalid_schema_version",
                    "evidence": outfit.schema_version,
                }
            )
        if core_shape == "invalid":
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "items",
                    "reason": "missing_core_categories",
                    "evidence": json.dumps(categories, ensure_ascii=False),
                }
            )
        if outfit.gender not in GENDER_SET:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "gender",
                    "reason": "invalid_gender",
                    "evidence": outfit.gender,
                }
            )
        if outfit.price_tier not in PRICE_TIER_SET:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "price_tier",
                    "reason": "invalid_price_tier",
                    "evidence": outfit.price_tier,
                }
            )
        for invalid_value in invalid_occasion:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "occasion",
                    "reason": "invalid_occasion",
                    "evidence": invalid_value,
                }
            )
        for invalid_value in invalid_style:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "style",
                    "reason": "invalid_style",
                    "evidence": invalid_value,
                }
            )
        for invalid_value in invalid_body:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "body_shapes_fit",
                    "reason": "invalid_body_shape",
                    "evidence": invalid_value,
                }
            )
        for invalid_value in invalid_season:
            invalid_rows.append(
                {
                    "outfit_id": outfit.outfit_id,
                    "field": "season",
                    "reason": "invalid_season",
                    "evidence": invalid_value,
                }
            )

        main_items = [item for item in outfit.items if item.category in _MAIN_GARMENT_CATEGORIES]
        main_body_union = sorted(
            {
   
                str(tag)
                for item in main_items
                for tag in item.body_shapes_fit
                if str(tag)
            }
        )
        main_season_union = sorted(
            {str(tag) for item in main_items for tag in item.season if str(tag)}
        )
        item_genders = sorted({str(item.gender) for item in outfit.items if str(item.gender)})
        expected_gender = _combo_gender(outfit.items) or "unisex"

        formality_bands = [
            str(item.formality)
            for item in outfit.items
            if item.category in FORMALITY_RELEVANT_CATEGORIES and str(item.formality)
        ]
        if formality_bands:
            top_formality = max(formality_bands, key=lambda band: FORMALITY_RANK.get(band, 0))
            allowed_occasions = sorted(occasions_for_formality(top_formality))
        else:
            top_formality = ""
            allowed_occasions = []

        rows.append(
            {
                "outfit_id": outfit.outfit_id,
                "schema_version": outfit.schema_version,
                "item_ids": item_ids,
                "categories": categories,
                "core_shape": core_shape,
                "has_shoes": has_shoes,
                "is_complete": is_complete,
                "n_items": len(outfit.items),
                "compatibility_score": float(outfit.compatibility_score),
                "occasion_list": valid_occasion,
                "style_list": valid_style,
                "body_shapes_fit_list": valid_body,
                "season_list": valid_season,
                "color_palette": [str(color) for color in outfit.color_palette if str(color)],
                "gender": outfit.gender,
                "expected_gender": expected_gender,
                "item_genders": item_genders,
                "price_total_vnd": int(outfit.price_total_vnd),
                "price_tier": outfit.price_tier,
                "has_vn_store": bool(outfit.has_vn_store),
                "gen_method": outfit.gen_method,
                "top_formality": top_formality,
                "allowed_occasions": allowed_occasions,
                "main_body_shape_union": main_body_union,
                "main_season_union": main_season_union,
                "occasion_count": len(valid_occasion),
                "style_count": len(valid_style),
                "body_shapes_count": len(valid_body),
                "season_count": len(valid_season),
                "color_count": len(outfit.color_palette),
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(invalid_rows)


def _group_distribution(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    grouped_df = df.copy()
    if group_col not in grouped_df.columns:
        grouped_df[group_col] = "unknown"
    grouped_df[group_col] = grouped_df[group_col].fillna("unknown").astype(str)

    rows: list[dict[str, Any]] = []
    for group_value, group in grouped_df.groupby(group_col, dropna=False):
        rows.append(
            {
                group_col: group_value,
                "total": int(len(group)),
                "avg_items": float(group["n_items"].mean()),
                "avg_score": float(group["compatibility_score"].mean()),
                "avg_body_shapes": float(group["body_shapes_count"].mean()),
                "avg_seasons": float(group["season_count"].mean()),
                "top_occasion": _series_top_tag(group["occasion_list"]),
                "top_style": _series_top_tag(group["style_list"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["total", group_col], ascending=[False, True])


def _build_outliers(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in df.to_dict(orient="records"):
        if row["n_items"] > 6:
            rows.append(
                {
                    "outfit_id": row["outfit_id"],
                    "outlier_type": "too_many_items",
                    "evidence": str(row["n_items"]),
                }
            )
        if row["occasion_count"] > 5:
            rows.append(
                {
                    "outfit_id": row["outfit_id"],
                    "outlier_type": "many_occasions",
                    "evidence": ", ".join(row["occasion_list"]),
                }
            )
        if row["style_count"] > 4:
            rows.append(
                {
                    "outfit_id": row["outfit_id"],
                    "outlier_type": "many_styles",
                    "evidence": ", ".join(row["style_list"]),
                }
            )
        if row["body_shapes_count"] > 3:
            rows.append(
                {
                    "outfit_id": row["outfit_id"],
                    "outlier_type": "many_body_shapes",
                    "evidence": ", ".join(row["body_shapes_fit_list"]),
                }
            )
        if row["season_count"] > 3:
            rows.append(
                {
                    "outfit_id": row["outfit_id"],
                    "outlier_type": "many_seasons",
                    "evidence": ", ".join(row["season_list"]),
                }
            )
    return pd.DataFrame(rows)


def _build_semantic_flags(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add_flag(
        outfit_id: str,
        core_shape: str,
        gender: str,
        rule_id: str,
        severity: str,
        evidence: str,
    ) -> None:
        rows.append(
            {
                "outfit_id": outfit_id,
                "core_shape": core_shape,
                "gender": gender,
                "rule_id": rule_id,
                "severity": severity,
                "evidence": evidence,
            }
        )

    for row in df.to_dict(orient="records"):
        outfit_id = str(row.get("outfit_id", ""))
        core_shape = str(row.get("core_shape", ""))
        gender = str(row.get("gender", ""))

        item_genders = set(row.get("item_genders", []))
        non_unisex = {value for value in item_genders if value != "unisex"}
        if len(non_unisex) > 1:
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "mixed_gender_items",
                "high",
                ", ".join(sorted(non_unisex)),
            )

        if row.get("gender") != row.get("expected_gender"):
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "outfit_gender_mismatch",
                "high",
                f"outfit={row.get('gender')} expected={row.get('expected_gender')}",
            )

        occasions = set(row.get("occasion_list", []))
        allowed_occasions = set(row.get("allowed_occasions", []))
        if occasions and not occasions.issubset(allowed_occasions):
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "occasion_formality_mismatch",
                "high",
                json.dumps(sorted(occasions - allowed_occasions), ensure_ascii=False),
            )

        body_shapes = set(row.get("body_shapes_fit_list", []))
        main_body = set(row.get("main_body_shape_union", []))
        if body_shapes and not body_shapes.issubset(main_body):
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "body_shape_not_in_main_garments",
                "high",
                json.dumps(sorted(body_shapes - main_body), ensure_ascii=False),
            )

        seasons = set(row.get("season_list", []))
        main_seasons = set(row.get("main_season_union", []))
        if seasons and not seasons.issubset(main_seasons):
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "season_not_in_main_garments",
                "high",
                json.dumps(sorted(seasons - main_seasons), ensure_ascii=False),
            )

        if row.get("core_shape") == "invalid":
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "invalid_item_combo",
                "high",
                json.dumps(row.get("categories", []), ensure_ascii=False),
            )
        elif not bool(row.get("has_shoes")):
            add_flag(
                outfit_id,
                core_shape,
                gender,
                "missing_recommended_shoes",
                "low",
                json.dumps(row.get("categories", []), ensure_ascii=False),
            )

    return pd.DataFrame(rows)


def _manual_review_sample(
    df: pd.DataFrame,
    flags_df: pd.DataFrame,
    *,
    per_shape: int,
    random_state: int = 42,
) -> pd.DataFrame:
    flag_map = (
        flags_df.groupby("outfit_id")["rule_id"]
        .agg(lambda values: "; ".join(sorted(set(values))))
        .to_dict()
        if not flags_df.empty
        else {}
    )

    selected_ids: list[str] = []
    if not flags_df.empty:
        selected_ids.extend(
            flags_df.loc[flags_df["severity"] == "high", "outfit_id"].astype(str).tolist()
        )
    selected_ids = list(dict.fromkeys(selected_ids))

    sampled_frames: list[pd.DataFrame] = []
    if selected_ids:
        sampled_frames.append(df.loc[df["outfit_id"].astype(str).isin(selected_ids)].copy())

    remaining = df.loc[~df["outfit_id"].astype(str).isin(selected_ids)].copy()
    for _, group in remaining.groupby("core_shape", dropna=False):
        sampled_frames.append(group.sample(n=min(per_shape, len(group)), random_state=random_state))

    if sampled_frames:
        sample = pd.concat(sampled_frames, ignore_index=True).drop_duplicates(subset=["outfit_id"])
    else:
        sample = df.head(0).copy()

    def dump_json(values: object) -> str:
        return json.dumps(values, ensure_ascii=False)
    return (
        pd.DataFrame(
            {
                "outfit_id": sample["outfit_id"],
                "core_shape": sample["core_shape"],
                "item_ids": sample["item_ids"].apply(dump_json),
                "categories": sample["categories"].apply(dump_json),
                "occasion": sample["occasion_list"].apply(dump_json),
                "style": sample["style_list"].apply(dump_json),
                "body_shapes_fit": sample["body_shapes_fit_list"].apply(dump_json),
                "season": sample["season_list"].apply(dump_json),
                "gender": sample["gender"],
                "expected_gender": sample["expected_gender"],
                "compatibility_score": sample["compatibility_score"],
                "flags": sample["outfit_id"].map(flag_map).fillna(""),
                "review_status": "",
                "review_notes": "",
            }
        )
        .sort_values(["core_shape", "outfit_id"])
        .reset_index(drop=True)
    )


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    outfits = _collect_outfits(
        catalog=args.catalog,
        links=args.links,
        edges=args.edges,
        seeds=args.seeds,
        occasion=args.occasion,
        beam=args.beam,
        max_optional=args.max_optional,
        max_outfits=args.max_outfits,
    )
    normalized, invalid_rows = _normalize_outfits(outfits)
    flags_df = _build_semantic_flags(normalized)
    outliers_df = _build_outliers(normalized)
    manual_sample_df = _manual_review_sample(
        normalized,
        flags_df,
        per_shape=args.sample_per_shape,
    )

    distributions = {
        "distribution_by_core_shape.csv": _group_distribution(normalized, "core_shape"),
        "distribution_by_gender.csv": _group_distribution(normalized, "gender"),
        "distribution_by_gen_method.csv": _group_distribution(normalized, "gen_method"),
        "distribution_by_price_tier.csv": _group_distribution(normalized, "price_tier"),
    }

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(invalid_rows, out_dir / "invalid_rows.csv")
    for filename, report_df in distributions.items():
        _write_csv(report_df, out_dir / filename)
    _write_csv(outliers_df, out_dir / "outliers.csv")
    _write_csv(flags_df, out_dir / "semantic_flags.csv")
    _write_csv(manual_sample_df, out_dir / "manual_review_sample.csv")

    invalid_reason_counts = (
        invalid_rows["reason"].value_counts().sort_index().to_dict()
        if not invalid_rows.empty
        else {}
    )
    high_severity_flags = int((flags_df["severity"] == "high").sum()) if not flags_df.empty else 0
    core_shape_counts = (
        normalized["core_shape"].value_counts().sort_index().to_dict()
        if not normalized.empty
        else {}
    )
    valid_core_outfit_count = (
        int((normalized["core_shape"] != "invalid").sum()) if not normalized.empty else 0
    )
    complete_outfit_count = int(normalized["is_complete"].sum()) if not normalized.empty else 0
    shoeless_valid_core_count = max(valid_core_outfit_count - complete_outfit_count, 0)
    completion_rate = (
        round(complete_outfit_count / valid_core_outfit_count, 6)
        if valid_core_outfit_count
        else 0.0
    )

    summary = {
        "total_outfits": int(len(normalized)),
        "valid_core_outfit_count": valid_core_outfit_count,
        "complete_outfit_count": complete_outfit_count,
        "shoeless_valid_core_count": shoeless_valid_core_count,
        "completion_rate": completion_rate,
        "invalid_row_count": int(len(invalid_rows)),
        "invalid_reason_counts": invalid_reason_counts,
        "semantic_flag_count": int(len(flags_df)),
        "high_severity_flag_count": high_severity_flags,
        "outlier_count": int(len(outliers_df)),
        "manual_review_sample_count": int(len(manual_sample_df)),
        "core_shape_counts": core_shape_counts,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("wrote outfit tagging quality audit to %s", out_dir)
    logger.info("summary: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
