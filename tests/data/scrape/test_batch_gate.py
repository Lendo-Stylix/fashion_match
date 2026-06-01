from pathlib import Path

from scripts.data.scrape.batch_gate import (
    GateThresholds,
    chunk_items,
    gate_batch,
    write_quarantine,
    yield_ok,
)
from scripts.data.scrape.normalize import NormalizedItem


def _item(
    tmp_path: Path,
    item_id: str,
    *,
    category: str = "top",
    price: int = 199000,
) -> NormalizedItem:
    img_rel = f"data/custom/catalog/images/{item_id}.jpg"
    img_abs = tmp_path / img_rel
    img_abs.parent.mkdir(parents=True, exist_ok=True)
    img_abs.write_bytes(b"x")
    return NormalizedItem(
        item_id=item_id,
        category=category,
        source_product_type="",
        gender="unisex",
        formality="casual",
        image_path=img_rel,
        image_url="https://cdn/x.jpg",
        title_vi="Áo thun",
        desc_vi="cotton",
        colors=["đen"],
        collected_date="2026-06-01",
        collector="unit",
        store_id="dirtycoins",
        source_product_id=item_id,
        product_url=f"https://dirtycoins.vn/p/{item_id}",
        price_vnd=price,
        sale_price_vnd=None,
        sku="SKU",
        in_stock=True,
        available_sizes=["M"],
        sizes_in_stock=["M"],
    )


def test_chunk_items_splits_by_size():
    xs = list(range(7))
    assert chunk_items(xs, 3) == [[0, 1, 2], [3, 4, 5], [6]]
    assert chunk_items(xs, 0) == [xs]


def test_yield_ok():
    thresholds = GateThresholds(min_yield=0.30)
    assert yield_ok(40, 100, thresholds) is True
    assert yield_ok(10, 100, thresholds) is False
    assert yield_ok(0, 0, thresholds) is True


def test_gate_batch_passes_clean_chunk(tmp_path):
    items = [_item(tmp_path, "item_custom_00001"), _item(tmp_path, "item_custom_00002")]
    result = gate_batch(items, store_id="dirtycoins", chunk_index=0, repo_root=tmp_path)
    assert result.passed is True
    assert result.blocking_codes == []
    assert result.item_count == 2
    assert result.batch_id == "dirtycoins#000"


def test_gate_batch_quarantines_invalid_category(tmp_path):
    items = [
        _item(tmp_path, "item_custom_00001"),
        _item(tmp_path, "item_custom_00002", category="not_a_cat"),
    ]
    result = gate_batch(items, store_id="dirtycoins", chunk_index=1, repo_root=tmp_path)
    assert result.passed is False
    assert "invalid_category" in result.blocking_codes


def test_write_quarantine_persists_chunk(tmp_path):
    import pandas as pd

    items = [_item(tmp_path, "item_custom_00001", category="not_a_cat")]
    result = gate_batch(items, store_id="dirtycoins", chunk_index=2, repo_root=tmp_path)
    out_dir = write_quarantine(result, items, quarantine_dir=tmp_path / "quarantine")
    assert (out_dir / "catalog.parquet").exists()
    assert (out_dir / "links.parquet").exists()
    assert len(pd.read_parquet(out_dir / "catalog.parquet")) == 1
