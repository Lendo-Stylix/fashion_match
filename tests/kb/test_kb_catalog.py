from __future__ import annotations

from pathlib import Path

import pandas as pd

from outfitmatch.kb.catalog import group_items_by_category, load_catalog_items


def _write_catalog(tmp_path: Path) -> tuple[Path, Path]:
    catalog_path = tmp_path / "catalog.parquet"
    links_path = tmp_path / "links.parquet"
    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_1.jpg",
                "title_vi": "Áo trắng",
                "desc_vi": "Cotton",
                "colors": '["Trắng"]',
                "collected_date": "2026-05-30",
                "collector": "unit",
                "formality": "formal",
            },
            {
                "item_id": "item_2",
                "category": "bottom",
                "image_path": "data/custom/catalog/images/item_2.jpg",
                "title_vi": "Quần đen",
                "desc_vi": "Denim",
                "colors": '["Đen"]',
                "collected_date": "2026-05-30",
                "collector": "unit",
                "formality": "casual",
            },
            {
                "item_id": "item_3",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_3.jpg",
                "title_vi": "Áo hết hàng",
                "desc_vi": "",
                "colors": "[]",
                "collected_date": "2026-05-30",
                "collector": "unit",
                "formality": "casual",
            },
        ]
    ).to_parquet(catalog_path, index=False)
    pd.DataFrame(
        [
            {
                "item_id": "item_1",
                "store_id": "yody_vn",
                "source_product_id": "p1",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 100000,
                "sale_price_vnd": None,
                "sku": "SKU1",
                "in_stock": True,
                "available_sizes": '["S", "M", "L"]',
                "sizes_in_stock": '["M", "L"]',
            },
            {
                "item_id": "item_2",
                "store_id": "canifa_vn",
                "source_product_id": "p2",
                "product_url": "https://canifa.com/p2",
                "price_vnd": 200000,
                "sale_price_vnd": None,
                "sku": "SKU2",
                "in_stock": True,
                "available_sizes": '["29", "30"]',
                "sizes_in_stock": "[]",
            },
            {
                "item_id": "item_3",
                "store_id": "yody_vn",
                "source_product_id": "p3",
                "product_url": "https://yody.vn/p3",
                "price_vnd": 120000,
                "sale_price_vnd": None,
                "sku": "SKU3",
                "in_stock": False,
                "available_sizes": '["M"]',
                "sizes_in_stock": "[]",
            },
        ]
    ).to_parquet(links_path, index=False)
    return catalog_path, links_path


def test_load_catalog_items_joins_store_and_metadata(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)

    items = load_catalog_items(catalog_path, links_path)

    assert [item.item_id for item in items] == ["item_1", "item_2"]
    assert items[0].category == "top"
    assert items[0].store["store_name"] == "YODY"
    assert items[0].store["title_vi"] == "Áo trắng"
    assert items[0].store["colors"] == ["Trắng"]


def test_load_catalog_items_reads_formality(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    assert items[0].formality == "formal"
    assert items[1].formality == "casual"


def test_load_catalog_items_includes_sizes(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    assert items[0].store["available_sizes"] == ["S", "M", "L"]
    assert items[0].store["sizes_in_stock"] == ["M", "L"]


def test_group_items_by_category_respects_limit_per_category(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path, in_stock_only=False)

    grouped = group_items_by_category(items, limit_per_category=1)

    assert set(grouped) == {"top", "bottom"}
    assert [item.item_id for item in grouped["top"]] == ["item_1"]
    assert [item.item_id for item in grouped["bottom"]] == ["item_2"]


def test_group_items_by_category_samples_price_range_when_capped():
    def item(item_id: str, price: int) -> object:
        return type(
            "Item",
            (),
            {"item_id": item_id, "category": "top", "store": {"price_vnd": price}},
        )()

    grouped = group_items_by_category(
        [item("cheap", 100000), item("mid", 300000), item("premium", 900000)],
        limit_per_category=2,
    )

    assert [x.item_id for x in grouped["top"]] == ["cheap", "premium"]
