from __future__ import annotations

import json

import pandas as pd
from scripts.data.kb import audit_tagging_quality as audit


def test_parse_tag_list_handles_json_string_and_invalid_payload():
    values, error = audit._parse_tag_list('["pear", "rectangle"]')
    assert values == ["pear", "rectangle"]
    assert error is None

    values, error = audit._parse_tag_list("not-json")
    assert values == []
    assert error == "invalid_json_list"


def test_normalize_catalog_flags_invalid_enum_empty_note_and_error_leak():
    catalog = pd.DataFrame(
        [
            {
                "item_id": "item_ok",
                "category": "top",
                "gender": "women",
                "formality": "casual",
                "title_vi": "Áo thun basic",
                "desc_vi": "Dễ mặc",
                "image_path": "a.jpg",
                "body_shapes_fit": '["pear"]',
                "season": '["summer"]',
                "stylist_notes_vi": "Áo cơ bản dễ phối.",
            },
            {
                "item_id": "item_bad",
                "category": "top",
                "gender": "women",
                "formality": "casual",
                "title_vi": "Áo thun lỗi",
                "desc_vi": "Dễ mặc",
                "image_path": "b.jpg",
                "body_shapes_fit": '["alien"]',
                "season": "not-json",
                "stylist_notes_vi": "WinError 10061 while tagging",
            },
            {
                "item_id": "item_empty_note",
                "category": "bag",
                "gender": "women",
                "formality": "casual",
                "title_vi": "Túi đeo vai",
                "desc_vi": "Nhỏ gọn",
                "image_path": "c.jpg",
                "body_shapes_fit": "[]",
                "season": '["summer"]',
                "stylist_notes_vi": "",
            },
        ]
    )

    normalized, invalid_rows = audit._normalize_catalog(catalog, links_df=None)

    assert normalized.loc[normalized.item_id == "item_ok", "body_shapes_count"].item() == 1
    reasons = set(invalid_rows["reason"])
    assert "invalid_body_shape" in reasons
    assert "invalid_json_list" in reasons
    assert "backend_error_leak" in reasons
    assert "empty_note" in reasons


def test_build_semantic_flags_catches_expected_rules():
    normalized = pd.DataFrame(
        [
            {
                "item_id": "item_accessory_body",
                "category": "accessory",
                "gender": "women",
                "formality": "casual",
                "store_id": "store_a",
                "title_vi": "Dây nịt nữ",
                "desc_vi": "Nhỏ gọn",
                "image_path": "a.jpg",
                "body_shapes_fit_list": ["pear"],
                "season_list": [],
                "stylist_notes_vi": "Phụ kiện tạo điểm nhấn và hoàn thiện tổng thể outfit.",
                "is_fallback_note": True,
                "body_shapes_count": 1,
                "season_count": 0,
                "note_len": 58,
            },
            {
                "item_id": "item_winter_summer",
                "category": "outerwear",
                "gender": "women",
                "formality": "casual",
                "store_id": "store_a",
                "title_vi": "Áo khoác dạ dáng dài",
                "desc_vi": "Ấm áp",
                "image_path": "b.jpg",
                "body_shapes_fit_list": [],
                "season_list": ["summer"],
                "stylist_notes_vi": "Áo khoác thanh lịch cho ngày lạnh.",
                "is_fallback_note": False,
                "body_shapes_count": 0,
                "season_count": 1,
                "note_len": 34,
            },
        ]
    )

    flags = audit._build_semantic_flags(normalized)

    assert set(flags["rule_id"]) >= {
        "accessory_has_body_shape",
        "winter_outerwear_summer_only",
        "fallback_note_review",
    }


def test_build_semantic_flags_avoids_broad_keyword_false_positives():
    normalized = pd.DataFrame(
        [
            {
                "item_id": "item_uv_jacket",
                "category": "outerwear",
                "gender": "women",
                "formality": "casual",
                "store_id": "store_a",
                "title_vi": "Áo khoác chống nắng nữ",
                "desc_vi": "Thoáng mát cho mùa hè",
                "image_path": "a.jpg",
                "body_shapes_fit_list": [],
                "season_list": ["summer"],
                "stylist_notes_vi": "Áo khoác chống nắng mỏng nhẹ cho ngày nắng.",
                "is_fallback_note": False,
                "body_shapes_count": 0,
                "season_count": 1,
                "note_len": 44,
            },
            {
                "item_id": "item_winter_dress",
                "category": "dress",
                "gender": "women",
                "formality": "casual",
                "store_id": "store_a",
                "title_vi": "Đầm Đông Nữ Tay Dài Cổ Vuông",
                "desc_vi": "Dễ phối với giày sandal, túi xách",
                "image_path": "b.jpg",
                "body_shapes_fit_list": [],
                "season_list": ["winter"],
                "stylist_notes_vi": "Đầm tay dài phù hợp thời tiết lạnh.",
                "is_fallback_note": False,
                "body_shapes_count": 0,
                "season_count": 1,
                "note_len": 35,
            },
        ]
    )

    flags = audit._build_semantic_flags(normalized)
    rule_ids = set(flags["rule_id"]) if not flags.empty else set()

    assert "winter_outerwear_summer_only" not in rule_ids
    assert "summer_item_winter_only" not in rule_ids


def test_main_writes_report_files(tmp_path):
    catalog = tmp_path / "catalog.parquet"
    links = tmp_path / "links.parquet"
    out_dir = tmp_path / "reports"

    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "category": "top",
                "gender": "women",
                "formality": "casual",
                "title_vi": "Áo thun basic",
                "desc_vi": "Dễ mặc",
                "image_path": "a.jpg",
                "body_shapes_fit": '["pear"]',
                "season": '["summer"]',
                "stylist_notes_vi": "Áo cơ bản dễ phối.",
            },
            {
                "item_id": "item_2",
                "category": "accessory",
                "gender": "women",
                "formality": "casual",
                "title_vi": "Thắt lưng nữ",
                "desc_vi": "Nhỏ gọn",
                "image_path": "b.jpg",
                "body_shapes_fit": "[]",
                "season": "[]",
                "stylist_notes_vi": "Phụ kiện tạo điểm nhấn và hoàn thiện tổng thể outfit.",
            },
        ]
    ).to_parquet(catalog, index=False)
    pd.DataFrame(
        [
            {"item_id": "item_1", "store_id": "store_a"},
            {"item_id": "item_2", "store_id": "store_b"},
        ]
    ).to_parquet(links, index=False)

    exit_code = audit.main(
        [
            "--catalog",
            str(catalog),
            "--links",
            str(links),
            "--out-dir",
            str(out_dir),
            "--sample-per-category",
            "1",
        ]
    )

    assert exit_code == 0
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "invalid_rows.csv").exists()
    assert (out_dir / "distribution_by_category.csv").exists()
    assert (out_dir / "distribution_by_store.csv").exists()
    assert (out_dir / "distribution_by_gender.csv").exists()
    assert (out_dir / "distribution_by_formality.csv").exists()
    assert (out_dir / "outliers.csv").exists()
    assert (out_dir / "semantic_flags.csv").exists()
    assert (out_dir / "manual_review_sample.csv").exists()

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["total_items"] == 2
    assert summary["tagged_nonempty"] == 2
