"""Load scraped catalog parquet rows into KB ``ItemRecord`` objects."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from scripts.data.scrape.config import STORES_BY_ID

from outfitmatch.kb.schema import ItemRecord
from outfitmatch.vocab import GENDER_SET, ITEM_CATEGORY_SET


def _parse_colors(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(v) for v in raw if str(v)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v) for v in parsed if str(v)]


def load_catalog_items(
    catalog_path: Path,
    links_path: Path,
    *,
    in_stock_only: bool = True,
    genders: set[str] | None = None,
) -> list[ItemRecord]:
    """Join scraper catalog/link parquet files into sorted ``ItemRecord`` objects.

    The raw catalog keeps product metadata and store links in separate files. Tầng 1
    generation operates on ``ItemRecord`` only, so this function adds useful raw
    fields (title, description, colors, SKU) into ``ItemRecord.store`` while keeping
    the canonical schema unchanged.

    ``genders`` (optional) restricts the returned items to those wearer genders
    (e.g. ``{"men", "women", "unisex"}`` to exclude kids' wear).
    """
    catalog = pd.read_parquet(catalog_path)
    links = pd.read_parquet(links_path)
    merged = catalog.merge(links, on="item_id", how="inner").sort_values("item_id")
    if in_stock_only:
        merged = merged[merged["in_stock"].fillna(False).astype(bool)]

    out: list[ItemRecord] = []
    for row in merged.to_dict(orient="records"):
        category = str(row.get("category") or "")
        if category not in ITEM_CATEGORY_SET:
            continue
        gender = str(row.get("gender") or "unisex")
        if gender not in GENDER_SET:
            gender = "unisex"
        if genders is not None and gender not in genders:
            continue
        store_id = str(row.get("store_id") or "")
        store = STORES_BY_ID.get(store_id)
        out.append(
            ItemRecord(
                item_id=str(row["item_id"]),
                category=category,
                image_path=str(row.get("image_path") or ""),
                item_embedding=[],
                gender=gender,
                store={
                    "store_id": store_id,
                    "store_name": store.store_name if store else store_id,
                    "product_url": str(row.get("product_url") or ""),
                    "price_vnd": int(row.get("price_vnd") or 0),
                    "sale_price_vnd": row.get("sale_price_vnd"),
                    "sku": str(row.get("sku") or ""),
                    "in_stock": bool(row.get("in_stock")),
                    "title_vi": str(row.get("title_vi") or ""),
                    "desc_vi": str(row.get("desc_vi") or ""),
                    "colors": _parse_colors(row.get("colors")),
                    "available_sizes": _parse_colors(row.get("available_sizes")),
                    "sizes_in_stock": _parse_colors(row.get("sizes_in_stock")),
                },
            )
        )
    return out


def _item_price(item: ItemRecord) -> int:
    return int(item.store.get("price_vnd") or 0)


def _representative_slice[ItemT: ItemRecord](items: list[ItemT], limit: int | None) -> list[ItemT]:
    ordered = sorted(items, key=lambda item: (_item_price(item), item.item_id))
    if limit is None or limit <= 0 or len(ordered) <= limit:
        return ordered
    if limit == 1:
        return [ordered[0]]
    indexes = {round(i * (len(ordered) - 1) / (limit - 1)) for i in range(limit)}
    selected = [ordered[i] for i in sorted(indexes)]
    return sorted(selected, key=lambda item: item.item_id)


def group_items_by_category(
    items: list[ItemRecord], *, limit_per_category: int | None = None
) -> dict[str, list[ItemRecord]]:
    """Group items by category and sample each category across its price range.

    The representative slice avoids accidentally taking only early-scraped stores when
    a category has thousands of rows.
    """
    grouped: dict[str, list[ItemRecord]] = defaultdict(list)
    for item in sorted(items, key=lambda x: x.item_id):
        grouped[item.category].append(item)
    return {
        category: _representative_slice(category_items, limit_per_category)
        for category, category_items in grouped.items()
    }
