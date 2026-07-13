"""Price-outlier audit for the VN store catalog links (Fix C).

The demo diagnosis (`docs/reports/inference_demo_diagnostic.md`) showed that a
narrow ``price_max`` combined with cheap-sale outliers (e.g. YODY items at 49,000
VND, which are legit variant-min/sale prices but far below a store's norm) made
retrieval return only those outliers. Graph items carry no ``original_price_vnd``
column (only ``price_vnd`` + optional ``sale_price_vnd``), so this audit flags
items priced below a per-store fraction of that store's median as *outliers*.

Outliers are NOT deleted — they are real products. The audit only surfaces them
so downstream code (retrieval guard, dashboard) can decide how to weight them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Items priced below this fraction of their store's median price are flagged.
DEFAULT_OUTLIER_RATIO = 0.2


@dataclass
class PriceAuditResult:
    """Summary of a price-outlier audit run."""

    total_rows: int
    outlier_rows: int
    stores_checked: int
    store_medians: dict[str, float]
    outlier_item_ids: list[str]
    ratio: float

    @property
    def outlier_fraction(self) -> float:
        return self.outlier_rows / self.total_rows if self.total_rows else 0.0


def flag_price_outliers(
    links: pd.DataFrame,
    ratio: float = DEFAULT_OUTLIER_RATIO,
) -> PriceAuditResult:
    """Flag catalog-link rows priced far below their store's median.

    Args:
        links: item_store_links dataframe with at least ``store_id`` and
            ``price_vnd`` columns.
        ratio: an item is an outlier if ``price_vnd < ratio * store_median``.

    Returns:
        PriceAuditResult with the flagged item ids and per-store medians.
    """
    if "store_id" not in links.columns or "price_vnd" not in links.columns:
        raise ValueError("links must contain 'store_id' and 'price_vnd' columns")

    df = links.copy()
    df["price_vnd"] = pd.to_numeric(df["price_vnd"], errors="coerce")
    store_medians = df.groupby("store_id")["price_vnd"].median().to_dict()

    def _is_outlier(row: pd.Series) -> bool:
        price = row["price_vnd"]
        median = store_medians.get(row["store_id"])
        if pd.isna(price) or median is None or pd.isna(median):
            return False
        return price < ratio * median

    mask = df.apply(_is_outlier, axis=1)
    outliers = df[mask]
    return PriceAuditResult(
        total_rows=len(df),
        outlier_rows=int(mask.sum()),
        stores_checked=len(store_medians),
        store_medians={k: float(v) for k, v in store_medians.items()},
        outlier_item_ids=outliers["item_id"].tolist(),
        ratio=ratio,
    )


def audit_prices(path: str, ratio: float = DEFAULT_OUTLIER_RATIO) -> PriceAuditResult:
    """Load ``item_store_links.parquet`` from ``path`` and run the audit."""
    links = pd.read_parquet(path)
    return flag_price_outliers(links, ratio=ratio)
