from pathlib import Path

import pandas as pd
from scripts.data.scrape.quality import QualityIssue, check_catalog, summarize_catalog


def _write_catalog(tmp_path: Path) -> tuple[Path, Path]:
    image = tmp_path / "data" / "custom" / "catalog" / "images" / "item_custom_00001.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"fake image")
    cat = tmp_path / "catalog_metadata.parquet"
    links = tmp_path / "item_store_links.parquet"
    pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
                "title_vi": "Áo thun basic",
                "desc_vi": "Áo cotton",
                "colors": '["Đen"]',
                "collected_date": "2026-05-30",
                "collector": "unit",
            }
        ]
    ).to_parquet(cat, index=False)
    pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "store_id": "yody_vn",
                "source_product_id": "ao-thun-basic",
                "product_url": "https://yody.vn/product/ao-thun-basic",
                "price_vnd": 199000,
                "sale_price_vnd": None,
                "sku": "SKU1",
                "in_stock": True,
            }
        ]
    ).to_parquet(links, index=False)
    return cat, links


def test_check_catalog_accepts_valid_minimal_catalog(tmp_path):
    cat, links = _write_catalog(tmp_path)

    report = check_catalog(cat, links, repo_root=tmp_path)

    assert report.total_items == 1
    assert report.total_links == 1
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.store_counts == {"yody_vn": 1}
    assert report.category_counts == {"top": 1}


def test_check_catalog_reports_schema_join_image_and_price_errors(tmp_path):
    cat = tmp_path / "catalog_metadata.parquet"
    links = tmp_path / "item_store_links.parquet"
    pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "category": "not_a_category",
                "image_path": "data/custom/catalog/images/missing.jpg",
                "title_vi": "",
                "desc_vi": "",
                "colors": "not-json",
                "collected_date": "2026-05-30",
                "collector": "unit",
            },
            {
                "item_id": "item_custom_00001",
                "category": "top",
                "image_path": "data/custom/catalog/images/missing2.jpg",
                "title_vi": "Áo",
                "desc_vi": "",
                "colors": "[]",
                "collected_date": "2026-05-30",
                "collector": "unit",
            },
        ]
    ).to_parquet(cat, index=False)
    pd.DataFrame(
        [
            {
                "item_id": "item_custom_99999",
                "store_id": "bad_store",
                "source_product_id": "x",
                "product_url": "notaurl",
                "price_vnd": 1000,
                "sale_price_vnd": 2000,
                "sku": "",
                "in_stock": True,
            }
        ]
    ).to_parquet(links, index=False)

    report = check_catalog(cat, links, repo_root=tmp_path)
    codes = {issue.code for issue in report.issues}

    assert report.error_count > 0
    assert {
        "duplicate_item_id",
        "invalid_category",
        "missing_title",
        "invalid_colors_json",
        "missing_image_file",
        "catalog_without_link",
        "link_without_catalog",
        "invalid_store_id",
        "invalid_product_url",
        "invalid_price",
        "sale_price_above_price",
    } <= codes


def test_summarize_catalog_is_stable_and_human_readable():
    report = QualityIssue(level="error", code="x", message="broken", count=2)

    text = summarize_catalog([report])

    assert "ERROR x: broken (count=2)" in text
