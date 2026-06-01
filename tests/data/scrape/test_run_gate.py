import scripts.data.scrape.normalize as normalize
from scripts.data.scrape.batch_gate import GateThresholds
from scripts.data.scrape.config import StoreConfig
from scripts.data.scrape.manifest import BatchRecord
from scripts.data.scrape.run import _resolve_failed_targets, gate_and_promote


def _store() -> StoreConfig:
    return StoreConfig(
        store_id="dirtycoins",
        store_name="Dirty Coins",
        website="https://dirtycoins.vn",
        platform="shopify_like",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("streetwear",),
    )


def _item(item_id: str, *, category: str = "top") -> normalize.NormalizedItem:
    return normalize.NormalizedItem(
        item_id=item_id,
        category=category,
        source_product_type="",
        gender="unisex",
        formality="casual",
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        image_url="https://cdn/x.jpg",
        title_vi="Áo thun",
        desc_vi="cotton",
        colors=["đen"],
        collected_date="2026-06-01",
        collector="unit",
        store_id="dirtycoins",
        source_product_id=item_id,
        product_url=f"https://dirtycoins.vn/p/{item_id}",
        price_vnd=199000,
        sale_price_vnd=None,
        sku="SKU",
        in_stock=True,
        available_sizes=["M"],
        sizes_in_stock=["M"],
    )


def test_gate_and_promote_routes_good_and_bad_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    import pandas as pd

    good = _item("item_custom_00001")
    bad = _item("item_custom_00002", category="not_a_cat")
    records: dict = {}
    promoted = gate_and_promote(
        _store(),
        [good, bad],
        raw_count=2,
        thresholds=GateThresholds(batch_size=1),
        download=False,
        client=None,
        repo_root=tmp_path,
        manifest=records,
        now="2026-06-01T00:00:00",
        check_images=False,
        quarantine_dir=tmp_path / "quarantine",
    )

    assert promoted == 1
    catalog = pd.read_parquet(tmp_path / "catalog_metadata.parquet")
    assert catalog["item_id"].tolist() == ["item_custom_00001"]
    assert records["dirtycoins#000"].status == "passed"
    assert records["dirtycoins#001"].status == "quarantined"
    assert (tmp_path / "quarantine" / "dirtycoins__001" / "catalog.parquet").exists()


def test_resolve_failed_targets_prioritizes_store_all():
    manifest = {
        "dirtycoins#ALL": BatchRecord(
            store_id="dirtycoins",
            chunk_index=-1,
            status="quarantined",
            item_count=3,
            blocking_codes=["low_yield"],
            metrics={"yield": 0.1},
            updated_at="2026-06-01T00:00:00",
            raw_count=30,
        ),
        "dirtycoins#002": BatchRecord(
            store_id="dirtycoins",
            chunk_index=2,
            status="quarantined",
            item_count=1,
            blocking_codes=["invalid_category"],
            metrics={},
            updated_at="2026-06-01T00:00:00",
        ),
    }

    stores, only_for = _resolve_failed_targets(manifest)

    assert [store.store_id for store in stores] == ["dirtycoins"]
    assert only_for == {"dirtycoins": None}


def test_gate_and_promote_quarantines_whole_store_on_low_yield(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    records: dict = {}
    promoted = gate_and_promote(
        _store(),
        [_item("item_custom_00001")],
        raw_count=100,
        thresholds=GateThresholds(batch_size=250, min_yield=0.30),
        download=False,
        client=None,
        repo_root=tmp_path,
        manifest=records,
        now="2026-06-01T00:00:00",
        check_images=False,
        quarantine_dir=tmp_path / "quarantine",
    )

    assert promoted == 0
    assert not (tmp_path / "catalog_metadata.parquet").exists()
    assert records["dirtycoins#ALL"].status == "quarantined"
    assert "low_yield" in records["dirtycoins#ALL"].blocking_codes
    assert (tmp_path / "quarantine" / "dirtycoins__ALL" / "catalog.parquet").exists()
