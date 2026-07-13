"""Tests for the price-outlier audit (Fix C)."""

from __future__ import annotations

import pandas as pd
import pytest

from outfitmatch.kb.price_audit import (
    DEFAULT_OUTLIER_RATIO,
    PriceAuditResult,
    flag_price_outliers,
)


def _make_links() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # YODY: median of [49000,49000,200000] = 49000 -> 0.2*median=9800.
            # y4 at 8000 < 9800 -> outlier; y3 (200k) not.
            {"item_id": "y1", "store_id": "yody_vn", "price_vnd": 49000},
            {"item_id": "y2", "store_id": "yody_vn", "price_vnd": 49000},
            {"item_id": "y3", "store_id": "yody_vn", "price_vnd": 200000},
            {"item_id": "y4", "store_id": "yody_vn", "price_vnd": 8000},
            # Rubies: median of [300000,280000,50000] = 280000 -> 0.2*median=56000.
            # r2 (50k) < 56000 -> outlier; r1 (300k) not.
            {"item_id": "r1", "store_id": "rubies_vn", "price_vnd": 300000},
            {"item_id": "r2", "store_id": "rubies_vn", "price_vnd": 50000},
            {"item_id": "r3", "store_id": "rubies_vn", "price_vnd": 280000},
        ]
    )


def test_flag_price_outliers_basic() -> None:
    links = _make_links()
    res = flag_price_outliers(links)
    assert isinstance(res, PriceAuditResult)
    assert res.total_rows == 7
    assert res.stores_checked == 2
    # y4 (30k under yody median 49k) and r2 (50k under rubies median 300k)
    assert set(res.outlier_item_ids) == {"y4", "r2"}
    assert res.store_medians["yody_vn"] == 49000.0
    assert res.store_medians["rubies_vn"] == 280000.0


def test_flag_price_outliers_ratio() -> None:
    links = _make_links()
    # with ratio 0.5: yody threshold 24.5k (y4=8k still outlier), rubies
    # threshold 140k (r2=50k still outlier)
    res = flag_price_outliers(links, ratio=0.5)
    assert set(res.outlier_item_ids) == {"y4", "r2"}


def test_flag_price_outliers_missing_columns() -> None:
    with pytest.raises(ValueError):
        flag_price_outliers(pd.DataFrame({"a": [1]}))


def test_default_ratio_constant() -> None:
    assert DEFAULT_OUTLIER_RATIO == 0.2
