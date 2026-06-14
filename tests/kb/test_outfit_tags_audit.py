from __future__ import annotations

import json

from scripts.data.kb import audit_outfit_tags as audit

from outfitmatch.kb.schema import ItemRecord, OutfitRecord


def _item(
    item_id: str,
    category: str,
    *,
    gender: str = "women",
    formality: str = "smart_casual",
    body_shapes_fit: list[str] | None = None,
    season: list[str] | None = None,
    colors: list[str] | None = None,
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"images/{item_id}.jpg",
        item_embedding=[0.1, 0.2],
        gender=gender,
        formality=formality,
        body_shapes_fit=body_shapes_fit or [],
        season=season or [],
        stylist_notes_vi="",
        store={
            "store_id": "yody",
            "store_name": "Yody",
            "product_url": "https://example.com/item",
            "price_vnd": 200_000,
            "in_stock": True,
            "colors": colors or ["đen"],
        },
    )


def _outfit(
    outfit_id: str,
    items: list[ItemRecord],
    *,
    occasion: list[str] | None = None,
    style: list[str] | None = None,
    body_shapes_fit: list[str] | None = None,
    season: list[str] | None = None,
    gender: str = "women",
    price_tier: str = "mid",
    schema_version: str = "3.1",
) -> OutfitRecord:
    return OutfitRecord(
        outfit_id=outfit_id,
        schema_version=schema_version,
        items=items,
        outfit_embedding=[0.1, 0.2],
        compatibility_score=0.85,
        occasion=occasion or ["office"],
        style=style or ["casual"],
        body_shapes_fit=body_shapes_fit or [],
        season=season or ["summer"],
        color_palette=["đen"],
        price_total_vnd=600_000,
        price_tier=price_tier,
        has_vn_store=True,
        stylist_explanation_vi="",
        gen_method="graph_traversal",
        gender=gender,
    )


def test_normalize_outfits_allows_shoeless_core_but_rejects_invalid_core_shape():
    shoeless_valid = _outfit(
        "OF_00001",
        [
            _item("t1", "top", body_shapes_fit=["pear"], season=["summer"]),
            _item("b1", "bottom", body_shapes_fit=["pear"], season=["summer"]),
        ],
        body_shapes_fit=["pear"],
        season=["summer"],
    )
    invalid = _outfit(
        "OF_00002",
        [
            _item("t2", "top", body_shapes_fit=["rectangle"], season=["summer"]),
            _item("b2", "bag", season=["summer"]),
        ],
        occasion=["beach"],
        style=["avant_garde"],
        body_shapes_fit=["triangle"],
        season=["monsoon"],
        gender="robot",
        price_tier="luxury",
        schema_version="2.0",
    )

    normalized, invalid_rows = audit._normalize_outfits([shoeless_valid, invalid])

    assert len(normalized) == 2
    core_shape = normalized.loc[normalized["outfit_id"] == "OF_00001", "core_shape"].iloc[0]
    assert core_shape == "top+bottom"
    reasons = set(invalid_rows["reason"])
    assert {
        "invalid_schema_version",
        "invalid_occasion",
        "invalid_style",
        "invalid_body_shape",
        "invalid_season",
        "invalid_gender",
        "invalid_price_tier",
        "missing_core_categories",
    } <= reasons


def test_build_semantic_flags_catches_mixed_gender_tag_leakage_and_missing_shoes():
    flagged = _outfit(
        "OF_00003",
        [
            _item(
                "t3",
                "top",
                gender="women",
                formality="casual",
                body_shapes_fit=["rectangle"],
                season=["summer"],
            ),
            _item(
                "b3",
                "bottom",
                gender="men",
                formality="casual",
                body_shapes_fit=["rectangle"],
                season=["summer"],
            ),
        ],
        occasion=["wedding"],
        body_shapes_fit=["pear"],
        season=["winter"],
        gender="women",
    )

    normalized, _ = audit._normalize_outfits([flagged])
    flags = audit._build_semantic_flags(normalized)

    assert set(flags["rule_id"]) >= {
        "mixed_gender_items",
        "occasion_formality_mismatch",
        "body_shape_not_in_main_garments",
        "season_not_in_main_garments",
        "outfit_gender_mismatch",
        "missing_recommended_shoes",
    }
    missing_shoes = flags.loc[flags["rule_id"] == "missing_recommended_shoes"]
    assert set(missing_shoes["severity"]) == {"low"}


def test_main_writes_outfit_audit_reports_with_completion_summary(monkeypatch, tmp_path):
    outfit = _outfit(
        "OF_00001",
        [
            _item("t1", "top", body_shapes_fit=["pear"], season=["summer"]),
            _item("b1", "bottom", body_shapes_fit=["pear"], season=["summer"]),
        ],
        body_shapes_fit=["pear"],
        season=["summer"],
    )

    monkeypatch.setattr(audit, "_collect_outfits", lambda **kwargs: [outfit])

    out_dir = tmp_path / "report"
    exit_code = audit.main(["--out-dir", str(out_dir), "--seeds", "5"])

    assert exit_code == 0
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["total_outfits"] == 1
    assert summary["invalid_row_count"] == 0
    assert summary["shoeless_valid_core_count"] == 1
    assert summary["complete_outfit_count"] == 0
    assert summary["completion_rate"] == 0.0
    assert (out_dir / "semantic_flags.csv").exists()
    assert (out_dir / "distribution_by_core_shape.csv").exists()
    assert (out_dir / "manual_review_sample.csv").exists()
