import scripts.data.scrape.normalize as normalize
from scripts.data.scrape.config import StoreConfig
from scripts.data.scrape.normalize import (
    normalize_products,
    to_catalog_frame,
    to_links_frame,
    write_frames,
)
from scripts.data.scrape.shopify import RawProduct


def _store():
    return StoreConfig(
        store_id="test_vn",
        store_name="Test",
        website="https://test.vn",
        platform="shopify_like",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("casual",),
    )


def _raw(**overrides) -> RawProduct:
    base = dict(
        source_store_id="test_vn",
        source_product_id="1",
        handle="ao-thun-test",
        title="Áo thun cotton basic",
        vendor="Test",
        product_type="Áo thun",
        tags=["áo", "thun"],
        description_html="<p>Mô tả <strong>chi tiết</strong> sản phẩm.</p>",
        images=["https://cdn.test.vn/img/a.jpg?v=1"],
        variants=[
            {
                "sku": "T-001-WHT-M",
                "price": "299000",
                "available": True,
                "option1": "Trắng",
                "option2": "M",
            },
            {
                "sku": "T-001-NVY-L",
                "price": "299000",
                "available": False,
                "option1": "Navy",
                "option2": "L",
            },
        ],
        product_url="https://test.vn/products/ao-thun-test",
    )
    base.update(overrides)
    return RawProduct(**base)


def test_happy_path():
    items = normalize_products(
        [_raw()], _store(), collector="unit", start_index=1, existing_link_map={}
    )
    assert len(items) == 1
    it = items[0]
    assert it.item_id == "item_custom_00001"
    assert it.source_product_id == "1"
    assert it.category == "top"
    assert it.image_path == "data/custom/catalog/images/item_custom_00001.jpg"
    assert it.title_vi == "Áo thun cotton basic"
    assert "chi tiết" in it.desc_vi
    assert "<" not in it.desc_vi  # html stripped
    assert sorted(it.colors) == ["Navy", "Trắng"]  # sizes filtered
    assert it.price_vnd == 299000
    assert it.sale_price_vnd is None
    assert it.sku == "T-001-WHT-M"
    assert it.in_stock is True  # any variant available


def test_infers_color_from_title_when_variant_options_only_contain_sizes():
    raw = _raw(
        title="Đầm đen dáng suông",
        product_type="Đầm",
        variants=[{"sku": "S", "price": "299000", "available": True, "option1": "S"}],
    )

    items = normalize_products([raw], _store(), start_index=1, existing_link_map={})

    assert items[0].colors == ["đen"]


def test_drops_when_no_image():
    items = normalize_products([_raw(images=[])], _store(), start_index=1, existing_link_map={})
    assert items == []


def test_drops_when_uncategorized():
    items = normalize_products(
        [_raw(title="Combo gift box", product_type="Combo", tags=["combo"])],
        _store(),
        start_index=1,
        existing_link_map={},
    )
    assert items == []


def test_price_guard():
    cheap = _raw(variants=[{"sku": "x", "price": "1000", "available": True}])
    expensive = _raw(variants=[{"sku": "y", "price": "999999999", "available": True}])
    items = normalize_products([cheap, expensive], _store(), start_index=1, existing_link_map={})
    assert items == []


def test_sale_price_detected():
    raw = _raw(
        variants=[
            {
                "sku": "S",
                "price": "199000",
                "compare_at_price": "299000",
                "available": True,
                "option1": "Đỏ",
            },
        ]
    )
    items = normalize_products([raw], _store(), start_index=7, existing_link_map={})
    assert items[0].item_id == "item_custom_00007"
    assert items[0].price_vnd == 199000
    assert items[0].sale_price_vnd == 199000


def test_webp_extension_preserved():
    raw = _raw(images=["https://cdn.test.vn/x.webp"])
    items = normalize_products([raw], _store(), start_index=1, existing_link_map={})
    assert items[0].image_path.endswith(".webp")


def test_rescrape_reuses_item_id():
    """Bug guard: same (store_id, source_product_id) must keep the same item_id
    across re-scrapes — otherwise re-running the scraper duplicates the catalog."""
    existing = {("test_vn", "1"): "item_custom_00042"}
    items = normalize_products([_raw()], _store(), start_index=100, existing_link_map=existing)
    assert len(items) == 1
    assert items[0].item_id == "item_custom_00042"
    # second pass with the freshly-populated map — still reuses
    items2 = normalize_products([_raw()], _store(), start_index=100, existing_link_map=existing)
    assert items2[0].item_id == "item_custom_00042"


def test_new_products_get_fresh_ids_after_existing_map():
    """Mixed batch: one product is known, the other is new — IDs allocated correctly."""
    existing = {("test_vn", "1"): "item_custom_00010"}
    new_raw = _raw(source_product_id="2", handle="ao-2", title="Áo thun mode 2")
    items = normalize_products(
        [_raw(), new_raw], _store(), start_index=50, existing_link_map=dict(existing)
    )
    assert [i.item_id for i in items] == ["item_custom_00010", "item_custom_00050"]


def test_extracts_sizes_from_variants():
    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    it = items[0]
    assert it.available_sizes == ["M", "L"]
    assert it.sizes_in_stock == ["M"]


def test_free_size_is_captured():
    raw = _raw(
        variants=[
            {
                "sku": "F",
                "price": "299000",
                "available": True,
                "option1": "Free size",
            }
        ]
    )
    items = normalize_products([raw], _store(), start_index=1, existing_link_map={})
    assert items[0].available_sizes == ["FREE SIZE"]


def test_to_frames_have_expected_columns():
    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    cat = to_catalog_frame(items)
    links = to_links_frame(items)

    assert {"item_id", "category", "gender", "formality", "colors"} <= set(cat.columns)
    assert {"item_id", "store_id", "price_vnd", "available_sizes", "sizes_in_stock"} <= set(
        links.columns
    )
    assert len(cat) == 1
    assert len(links) == 1


def test_write_frames_includes_size_columns(tmp_path, monkeypatch):
    import json

    import pandas as pd

    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    items = normalize_products([_raw()], _store(), existing_link_map={})
    write_frames(items)

    links = pd.read_parquet(tmp_path / "item_store_links.parquet")
    assert "available_sizes" in links.columns
    assert "sizes_in_stock" in links.columns
    assert json.loads(links.loc[0, "available_sizes"]) == ["M", "L"]
    assert json.loads(links.loc[0, "sizes_in_stock"]) == ["M"]


def test_write_frames_updates_existing_catalog_row(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    original = normalize_products([_raw(title="Áo thun cũ")], _store(), existing_link_map={})
    write_frames(original)
    updated = normalize_products(
        [_raw(title="Áo thun mới")],
        _store(),
        existing_link_map={("test_vn", "1"): "item_custom_00001"},
    )
    write_frames(updated)

    import pandas as pd

    catalog = pd.read_parquet(tmp_path / "catalog_metadata.parquet")
    assert catalog.shape[0] == 1
    assert catalog.loc[0, "title_vi"] == "Áo thun mới"


def test_infers_formality():
    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    assert items[0].formality == "casual"  # "Áo thun cotton basic" → casual


def test_formality_written_to_catalog(tmp_path, monkeypatch):
    import pandas as pd

    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    write_frames(normalize_products([_raw()], _store(), existing_link_map={}))
    cat = pd.read_parquet(tmp_path / "catalog_metadata.parquet")
    assert "formality" in cat.columns
    assert cat.loc[0, "formality"] == "casual"
