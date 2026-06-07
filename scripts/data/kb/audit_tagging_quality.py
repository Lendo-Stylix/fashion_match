"""Audit semantic tagging quality for the catalog metadata parquet.

Read-only report generator for graph-KB item semantic tags:
- body_shapes_fit
- season
- stylist_notes_vi
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

from outfitmatch.vocab import BODY_SHAPE_SET, SEASON_SET, validate_enum_values
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.audit_tagging_quality")

_FALLBACK_NOTES_VI_BY_CATEGORY = {
    "accessory": "Phụ kiện tạo điểm nhấn và hoàn thiện tổng thể outfit.",
    "bag": "Phụ kiện túi giúp hoàn thiện outfit và tăng tính ứng dụng.",
    "shoes": "Giày dép trung tính, dễ phối để hoàn thiện outfit.",
}

_BACKEND_ERROR_MARKERS = (
    "winerror",
    "traceback",
    "http",
    "quota",
    "connection refused",
    "could not connect",
    "error while tagging",
    "runtimeerror",
)

_WINTER_KEYWORDS = (
    "áo khoác dạ",
    "áo phao",
    "phao",
    "măng tô",
    "vải dạ",
    "puffer",
    "coat",
    "len cổ lọ",
)

_SUMMER_KEYWORDS = (
    "sandal",
    "dép",
    "áo ba lỗ",
    "tank top",
    "short",
    "shorts",
    "chống nắng",
)

_GARMENT_NOTE_MISMATCH = {
    "bag": ("áo", "quần", "váy", "đầm", "giày"),
    "accessory": ("áo", "quần", "váy", "đầm"),
    "shoes": ("áo", "quần", "váy", "đầm", "túi"),
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit catalog semantic tagging quality")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--out-dir", type=Path, default=Path("data/reports/tagging_quality"))
    parser.add_argument("--sample-per-category", type=int, default=5)
    parser.add_argument("--generic-note-repeat-threshold", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _parse_tag_list(value: object) -> tuple[list[str], str | None]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()], None
    if value is None:
        return [], None
    if isinstance(value, float) and math.isnan(value):
        return [], None

    text = str(value).strip()
    if not text or text == "[]" or text.lower() == "nan":
        return [], None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [], "invalid_json_list"

    if not isinstance(parsed, list):
        return [], "invalid_json_list"

    return [str(v).strip() for v in parsed if str(v).strip()], None


def _clean_note(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _contains_backend_error(note: str) -> bool:
    lower = note.lower()
    return any(marker in lower for marker in _BACKEND_ERROR_MARKERS)


def _is_fallback_note(category: str, note: str) -> bool:
    return note == _FALLBACK_NOTES_VI_BY_CATEGORY.get(category, "")


def _normalize_catalog(
    catalog_df: pd.DataFrame,
    *,
    links_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = catalog_df.copy()
    if links_df is not None and "store_id" in links_df.columns and "store_id" not in df.columns:
        df = df.merge(links_df[["item_id", "store_id"]], on="item_id", how="left")
    if "store_id" not in df.columns:
        df["store_id"] = "unknown"

    invalid_rows: list[dict[str, object]] = []
    normalized_rows: list[dict[str, object]] = []

    for row in df.to_dict(orient="records"):
        body_values, body_error = _parse_tag_list(row.get("body_shapes_fit"))
        season_values, season_error = _parse_tag_list(row.get("season"))
        valid_body, invalid_body = validate_enum_values(body_values, BODY_SHAPE_SET)
        valid_season, invalid_season = validate_enum_values(season_values, SEASON_SET)
        note = _clean_note(row.get("stylist_notes_vi"))

        if body_error is not None:
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "body_shapes_fit",
                "reason": body_error,
                "evidence": row.get("body_shapes_fit", ""),
            })
        if season_error is not None:
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "season",
                "reason": season_error,
                "evidence": row.get("season", ""),
            })
        for invalid_value in invalid_body:
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "body_shapes_fit",
                "reason": "invalid_body_shape",
                "evidence": invalid_value,
            })
        for invalid_value in invalid_season:
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "season",
                "reason": "invalid_season",
                "evidence": invalid_value,
            })
        if not note:
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "stylist_notes_vi",
                "reason": "empty_note",
                "evidence": "",
            })
        elif _contains_backend_error(note):
            invalid_rows.append({
                "item_id": row.get("item_id", ""),
                "field": "stylist_notes_vi",
                "reason": "backend_error_leak",
                "evidence": note,
            })

        normalized_rows.append({
            **row,
            "store_id": row.get("store_id", "unknown") or "unknown",
            "body_shapes_fit_list": valid_body,
            "season_list": valid_season,
            "stylist_notes_vi": note,
            "body_shapes_count": len(valid_body),
            "season_count": len(valid_season),
            "note_len": len(note),
            "is_fallback_note": _is_fallback_note(str(row.get("category", "")), note),
            "has_backend_error_leak": _contains_backend_error(note),
        })

    return pd.DataFrame(normalized_rows), pd.DataFrame(invalid_rows)


def _series_top_tag(series: pd.Series) -> str:
    exploded = series.explode().dropna()
    exploded = exploded[exploded.astype(str).str.strip() != ""]
    if exploded.empty:
        return ""
    return str(exploded.value_counts().index[0])


def _group_distribution(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in df.columns:
        grouped_df = df.assign(**{group_col: "unknown"})
    else:
        grouped_df = df.copy()
        grouped_df[group_col] = grouped_df[group_col].fillna("unknown").astype(str)

    rows: list[dict[str, Any]] = []
    for group_value, group in grouped_df.groupby(group_col, dropna=False):
        rows.append({
            group_col: group_value,
            "total": int(len(group)),
            "empty_body_ratio": float((group["body_shapes_count"] == 0).mean()),
            "empty_season_ratio": float((group["season_count"] == 0).mean()),
            "empty_note_ratio": float((group["stylist_notes_vi"] == "").mean()),
            "fallback_note_ratio": float(group["is_fallback_note"].mean()),
            "note_len_p50": float(group["note_len"].quantile(0.5)),
            "note_len_p90": float(group["note_len"].quantile(0.9)),
            "note_len_max": int(group["note_len"].max()),
            "top_body_shape": _series_top_tag(group["body_shapes_fit_list"]),
            "top_season": _series_top_tag(group["season_list"]),
        })

    return pd.DataFrame(rows).sort_values(["total", group_col], ascending=[False, True])



def _build_outliers(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in df.to_dict(orient="records"):
        if row["body_shapes_count"] > 3:
            rows.append(
                {
                    "item_id": row["item_id"],
                    "outlier_type": "many_body_shapes",
                    "evidence": ", ".join(row["body_shapes_fit_list"]),
                }
            )
        if row["season_count"] > 3:
            rows.append(
                {
                    "item_id": row["item_id"],
                    "outlier_type": "many_seasons",
                    "evidence": ", ".join(row["season_list"]),
                }
            )
        if row["note_len"] > 140:
            rows.append(
                {
                    "item_id": row["item_id"],
                    "outlier_type": "long_note",
                    "evidence": row["stylist_notes_vi"],
                }
            )
    return pd.DataFrame(rows)


def _build_semantic_flags(
    df: pd.DataFrame,
    *,
    generic_note_repeat_threshold: int = 10,
) -> pd.DataFrame:
    note_counts = df["stylist_notes_vi"].value_counts()
    rows: list[dict[str, object]] = []

    for row in df.to_dict(orient="records"):
        title = str(row.get("title_vi", "") or "").lower()
        note = str(row.get("stylist_notes_vi", "") or "")
        note_lower = note.lower()
        category = str(row.get("category", "") or "")
        seasons = list(row.get("season_list", []))

        item_id = row["item_id"]
        store_id = row.get("store_id", "unknown")
        title_vi = row.get("title_vi", "")

        def flag(
            rule_id: str,
            severity: str,
            evidence: str,
            *,
            item_id: str = item_id,
            category: str = category,
            store_id: str = store_id,
            title_vi: str = title_vi,
        ) -> None:
            rows.append(
                {
                    "item_id": item_id,
                    "category": category,
                    "store_id": store_id,
                    "title_vi": title_vi,
                    "rule_id": rule_id,
                    "severity": severity,
                    "evidence": evidence,
                }
            )

        if category in {"accessory", "bag", "shoes"} and row["body_shapes_count"] > 0:
            flag(f"{category}_has_body_shape", "medium", ", ".join(row["body_shapes_fit_list"]))

        title_text = title
        if any(keyword in title_text for keyword in _WINTER_KEYWORDS) and seasons == ["summer"]:
            flag("winter_outerwear_summer_only", "high", str(row.get("season_list", [])))

        if any(keyword in title_text for keyword in _SUMMER_KEYWORDS) and seasons == ["winter"]:
            flag("summer_item_winter_only", "high", str(row.get("season_list", [])))

        if row["is_fallback_note"]:
            flag("fallback_note_review", "low", note)

        if (
            note
            and note_counts.get(note, 0) >= generic_note_repeat_threshold
            and not row["is_fallback_note"]
        ):
            flag("repeated_generic_note", "medium", f"repeat_count={int(note_counts[note])}")

        mismatch_markers = _GARMENT_NOTE_MISMATCH.get(category, ())
        if mismatch_markers and any(
            note_lower.startswith(f"{marker} ") for marker in mismatch_markers
        ):
            flag("note_category_mismatch", "high", note)

    return pd.DataFrame(rows)


def _manual_review_sample(
    df: pd.DataFrame,
    flags_df: pd.DataFrame,
    *,
    per_category: int,
    random_state: int = 42,
) -> pd.DataFrame:
    flag_map = (
        flags_df.groupby("item_id")["rule_id"]
        .agg(lambda values: "; ".join(sorted(set(values))))
        .to_dict()
        if not flags_df.empty
        else {}
    )

    selected_ids: list[str] = []
    if not flags_df.empty:
        selected_ids.extend(
            flags_df.loc[flags_df["severity"] == "high", "item_id"].astype(str).tolist()
        )
        selected_ids.extend(
            flags_df.loc[flags_df["rule_id"] == "fallback_note_review", "item_id"]
            .astype(str)
            .tolist()
        )

    selected_ids = list(dict.fromkeys(selected_ids))
    remaining = df.loc[~df["item_id"].astype(str).isin(selected_ids)].copy()

    sampled_frames: list[pd.DataFrame] = []
    if selected_ids:
        sampled_frames.append(df.loc[df["item_id"].astype(str).isin(selected_ids)].copy())
    for _, group in remaining.groupby("category", dropna=False):
        sampled_frames.append(
            group.sample(n=min(per_category, len(group)), random_state=random_state)
        )

    if sampled_frames:
        sample = pd.concat(sampled_frames, ignore_index=True).drop_duplicates(subset=["item_id"])
    else:
        sample = df.head(0).copy()

    return (
        pd.DataFrame(
            {
                "item_id": sample["item_id"],
                "category": sample["category"],
                "store_id": sample["store_id"],
                "title_vi": sample["title_vi"],
                "desc_vi": sample["desc_vi"],
                "image_path": sample["image_path"],
                "body_shapes_fit": sample["body_shapes_fit_list"].apply(
                    lambda values: json.dumps(values, ensure_ascii=False)
                ),
                "season": sample["season_list"].apply(
                    lambda values: json.dumps(values, ensure_ascii=False)
                ),
                "stylist_notes_vi": sample["stylist_notes_vi"],
                "flags": sample["item_id"].map(flag_map).fillna(""),
                "review_status": "",
                "review_notes": "",
            }
        )
        .sort_values(["category", "item_id"])
        .reset_index(drop=True)
    )


def _tagged_nonempty_count(df: pd.DataFrame) -> int:
    mask = (
        (df["body_shapes_count"] > 0)
        | (df["season_count"] > 0)
        | (df["stylist_notes_vi"].astype(str).str.strip() != "")
    )
    return int(mask.sum())


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    catalog_df = pd.read_parquet(args.catalog)
    links_df = pd.read_parquet(args.links) if args.links.exists() else None
    normalized, invalid_rows = _normalize_catalog(catalog_df, links_df=links_df)
    flags_df = _build_semantic_flags(
        normalized,
        generic_note_repeat_threshold=args.generic_note_repeat_threshold,
    )
    outliers_df = _build_outliers(normalized)
    manual_sample_df = _manual_review_sample(
        normalized,
        flags_df,
        per_category=args.sample_per_category,
    )

    distributions = {
        "distribution_by_category.csv": _group_distribution(normalized, "category"),
        "distribution_by_store.csv": _group_distribution(normalized, "store_id"),
        "distribution_by_gender.csv": _group_distribution(normalized, "gender"),
        "distribution_by_formality.csv": _group_distribution(normalized, "formality"),
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
    fallback_note_count = int(normalized["is_fallback_note"].sum())
    tagged_nonempty = _tagged_nonempty_count(normalized)

    summary = {
        "total_items": int(len(normalized)),
        "tagged_nonempty": tagged_nonempty,
        "pending_empty": int(len(normalized) - tagged_nonempty),
        "invalid_row_count": int(len(invalid_rows)),
        "invalid_reason_counts": invalid_reason_counts,
        "fallback_note_count": fallback_note_count,
        "fallback_note_ratio": (
            float(fallback_note_count / len(normalized)) if len(normalized) else 0.0
        ),
        "semantic_flag_count": int(len(flags_df)),
        "high_severity_flag_count": high_severity_flags,
        "outlier_count": int(len(outliers_df)),
        "manual_review_sample_count": int(len(manual_sample_df)),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("wrote tagging quality audit to %s", out_dir)
    logger.info("summary: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
