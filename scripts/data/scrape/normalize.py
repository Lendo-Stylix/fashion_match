"""Normalize raw scraper output → catalog rows.

Two output frames mirroring docs/datasets/STORE_CATALOG_VN.md §4:

  * catalog_metadata.parquet   — one row per item (project-wide unique item_id).
  * item_store_links.parquet   — one row per (item_id, store_id) — same item
                                  scraped twice from same store ⇒ overwritten.

Item IDs use the project convention `item_custom_NNNNN` (5+ digits). When
running incrementally we resume from `max(existing_id) + 1` so re-runs don't
collide.

Why HTML strip lives here: the raw description_html comes straight from
Shopify/Haravan and we want clean Vietnamese text only — not a tag soup —
both for `desc_vi` storage and for later Gemini metadata-tagging input.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .base import CATALOG_DIR, IMAGE_DIR
from .config import StoreConfig
from .formality_map import infer_formality
from .gender_map import infer_gender
from .shopify import RawProduct
from .store_category_map import resolve_category

# columns the item_store_links parquet must expose. `source_product_id` is the
# stable per-store key used to dedupe item_ids across re-scrapes.
LINK_COLUMNS = (
    "item_id",
    "store_id",
    "source_product_id",
    "product_url",
    "price_vnd",
    "sale_price_vnd",
    "sku",
    "in_stock",
    "available_sizes",
    "sizes_in_stock",
)

logger = logging.getLogger(__name__)

CATALOG_PARQUET = CATALOG_DIR / "catalog_metadata.parquet"
LINKS_PARQUET = CATALOG_DIR / "item_store_links.parquet"

# Price sanity bounds (VND). Below this we suspect cents (Shopify Intl) or wrong unit;
# above this we suspect a typo or pricelist in USD * 1000.
PRICE_MIN_VND = 30_000
PRICE_MAX_VND = 50_000_000

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SIZE_LIKE_RE = re.compile(r"[XSMLxsml0-9.\-/ ]{1,8}")

# Longest aliases first so "xanh navy" is not truncated to plain "xanh".
_TITLE_COLOR_ALIASES: tuple[tuple[str, str], ...] = (
    ("xanh tím than", "xanh navy"),
    ("xanh tim than", "xanh navy"),
    ("xanh than", "xanh navy"),
    ("xanh navy", "xanh navy"),
    ("xanh dương", "xanh dương"),
    ("xanh duong", "xanh dương"),
    ("xanh biển", "xanh dương"),
    ("xanh bien", "xanh dương"),
    ("xanh lá", "xanh lá"),
    ("xanh la", "xanh lá"),
    ("xanh rêu", "xanh rêu"),
    ("xanh reu", "xanh rêu"),
    ("xám nhạt", "xám nhạt"),
    ("xam nhat", "xám nhạt"),
    ("xám đậm", "xám đậm"),
    ("xam dam", "xám đậm"),
    ("ghi sáng", "ghi"),
    ("ghi sang", "ghi"),
    ("ghi đậm", "ghi"),
    ("ghi dam", "ghi"),
    ("đen", "đen"),
    ("den", "đen"),
    ("trắng", "trắng"),
    ("trang", "trắng"),
    ("xám", "xám"),
    ("xam", "xám"),
    ("ghi", "ghi"),
    ("navy", "xanh navy"),
    ("beige", "be"),
    ("be", "be"),
    ("kem", "kem"),
    ("nâu", "nâu"),
    ("nau", "nâu"),
    ("đỏ", "đỏ"),
    ("do", "đỏ"),
    ("hồng", "hồng"),
    ("hong", "hồng"),
    ("tím", "tím"),
    ("tim", "tím"),
    ("vàng", "vàng"),
    ("vang", "vàng"),
    ("cam", "cam"),
    ("bạc", "bạc"),
    ("bac", "bạc"),
    ("xanh", "xanh"),
)


def _strip_html(html: str, max_len: int = 600) -> str:
    if not html:
        return ""
    text = _HTML_TAG_RE.sub(" ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_len]


def _looks_like_size(val: str) -> bool:
    v = val.strip()
    if not v:
        return False
    low = v.lower()
    if "size" in low or "kích" in low or "free" in low:
        return True
    return bool(_SIZE_LIKE_RE.fullmatch(v))


def _infer_colors_from_text(*texts: object) -> list[str]:
    """Infer coarse Vietnamese color labels from titles/tags when variants omit color."""
    haystack = " ".join(str(text or "").lower() for text in texts if str(text or "").strip())
    if not haystack:
        return []

    colors: list[str] = []
    seen: set[str] = set()
    for alias, canonical in _TITLE_COLOR_ALIASES:
        if canonical in seen:
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", haystack, re.IGNORECASE):
            seen.add(canonical)
            colors.append(canonical)
    return colors[:8]


def _infer_colors(variants: list[dict], *, text_sources: Iterable[object] = ()) -> list[str]:
    """Best-effort: pull color names from variants, then title/product text."""
    colors: list[str] = []
    seen: set[str] = set()
    for v in variants:
        for k in ("option1", "option2", "option3"):
            val = (v.get(k) or "").strip()
            if not val:
                continue
            if _looks_like_size(val):
                continue
            low = val.lower()
            if low in seen:
                continue
            seen.add(low)
            colors.append(val)

    for color in _infer_colors_from_text(*text_sources):
        low = color.lower()
        if low in seen:
            continue
        seen.add(low)
        colors.append(color)
    return colors[:8]


def _infer_sizes(variants: list[dict]) -> tuple[list[str], list[str]]:
    """Pull size labels from variant option fields.

    Returns ``(available_sizes, sizes_in_stock)``. Order of first appearance is
    preserved and labels are upper-cased so ``m``/``M`` collapse.
    """
    all_sizes: list[str] = []
    in_stock: list[str] = []
    seen: set[str] = set()
    seen_stock: set[str] = set()
    for v in variants:
        for k in ("option1", "option2", "option3"):
            val = (v.get(k) or "").strip()
            if not val or not _looks_like_size(val):
                continue
            norm = val.upper()
            if norm not in seen:
                seen.add(norm)
                all_sizes.append(norm)
            if bool(v.get("available")) and norm not in seen_stock:
                seen_stock.add(norm)
                in_stock.append(norm)
    return all_sizes, in_stock


def _existing_max_index(parquet_path: Path) -> int:
    if not parquet_path.exists():
        return 0
    try:
        df = pd.read_parquet(parquet_path, columns=["item_id"])
    except (FileNotFoundError, ValueError, KeyError) as exc:
        logger.warning("re-init: cannot read %s (%s)", parquet_path, exc)
        return 0
    if df.empty:
        return 0
    nums: list[int] = []
    for s in df["item_id"].astype(str).tolist():
        m = re.match(r"item_custom_(\d+)$", s)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


@dataclass
class NormalizedItem:
    item_id: str
    category: str
    source_product_type: str  # raw store-native taxonomy value (traceability)
    gender: str  # GENDER enum value (men|women|unisex|kid)
    formality: str  # FORMALITY enum value (athletic|casual|smart_casual|formal)
    image_path: str  # repo-relative path
    image_url: str  # remote URL — used by download_images.py
    title_vi: str
    desc_vi: str
    colors: list[str]
    collected_date: str
    collector: str
    # link row
    store_id: str
    source_product_id: str  # stable key from upstream (Shopify product id)
    product_url: str
    price_vnd: int
    sale_price_vnd: int | None
    sku: str
    in_stock: bool
    available_sizes: list[str]
    sizes_in_stock: list[str]


def _load_existing_link_map() -> dict[tuple[str, str], str]:
    """(store_id, source_product_id) → existing item_id, for stable re-scrape."""
    if not LINKS_PARQUET.exists():
        return {}
    try:
        df = pd.read_parquet(LINKS_PARQUET)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("cannot read %s (%s) — assuming empty", LINKS_PARQUET, exc)
        return {}
    if df.empty or "source_product_id" not in df.columns:
        return {}
    out: dict[tuple[str, str], str] = {}
    for _, row in df[["store_id", "source_product_id", "item_id"]].iterrows():
        spid = row["source_product_id"]
        if spid is None or (isinstance(spid, float) and pd.isna(spid)):
            continue
        out[(str(row["store_id"]), str(spid))] = str(row["item_id"])
    return out


def normalize_products(
    raws: Iterable[RawProduct],
    store: StoreConfig,
    *,
    collector: str = "scraper",
    start_index: int = 1,
    existing_link_map: dict[tuple[str, str], str] | None = None,
) -> list[NormalizedItem]:
    """Map raw products → NormalizedItem, reusing item_ids across re-scrapes.

    ``existing_link_map`` (store_id, source_product_id) → item_id is consulted
    first; matched products keep their original item_id. New products get a
    fresh `item_custom_NNNNN` starting at ``start_index`` (caller passes
    ``next_index()`` from this module).
    """
    today = dt.date.today().isoformat()
    items: list[NormalizedItem] = []
    link_map = existing_link_map if existing_link_map is not None else _load_existing_link_map()
    idx = start_index
    for raw in raws:
        if not raw.images:
            continue
        category = resolve_category(raw.title, raw.product_type, raw.tags, store.store_id)
        if category is None:
            logger.debug("[%s] uncategorized: %s | %s", store.store_id, raw.title, raw.tags)
            continue
        price = raw.min_price_vnd
        if price is None or price < PRICE_MIN_VND or price > PRICE_MAX_VND:
            logger.debug("[%s] reject price %s for %s", store.store_id, price, raw.title)
            continue
        key = (store.store_id, raw.source_product_id)
        if key in link_map:
            item_id = link_map[key]
        else:
            item_id = f"item_custom_{idx:05d}"
            idx += 1
            link_map[key] = item_id
        image_url = raw.images[0]
        available_sizes, sizes_in_stock = _infer_sizes(raw.variants)
        # extension: parse from URL path, fallback .jpg
        ext = ".jpg"
        m = re.search(r"\.(jpe?g|png|webp)(?:\?|$)", image_url, re.IGNORECASE)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
        image_rel = f"data/custom/catalog/images/{item_id}{ext}"
        items.append(
            NormalizedItem(
                item_id=item_id,
                category=category,
                source_product_type=raw.product_type or "",
                gender=infer_gender(raw.title, raw.product_type, store.store_id, category),
                formality=infer_formality(raw.title, raw.product_type, category, raw.tags),
                image_path=image_rel,
                image_url=image_url,
                title_vi=raw.title,
                desc_vi=_strip_html(raw.description_html),
                colors=_infer_colors(
                    raw.variants,
                    text_sources=(raw.title, raw.product_type, *raw.tags),
                ),
                collected_date=today,
                collector=collector,
                store_id=store.store_id,
                source_product_id=raw.source_product_id,
                product_url=raw.product_url,
                price_vnd=price,
                sale_price_vnd=raw.min_sale_price_vnd,
                sku=raw.primary_sku,
                in_stock=raw.any_in_stock,
                available_sizes=available_sizes,
                sizes_in_stock=sizes_in_stock,
            )
        )
    return items


def to_catalog_frame(items: list[NormalizedItem]) -> pd.DataFrame:
    """One catalog-metadata row per normalized item."""
    return pd.DataFrame(
        [
            {
                "item_id": it.item_id,
                "category": it.category,
                "source_product_type": it.source_product_type,
                "gender": it.gender,
                "formality": it.formality,
                "image_path": it.image_path,
                "title_vi": it.title_vi,
                "desc_vi": it.desc_vi,
                "colors": json.dumps(it.colors, ensure_ascii=False),
                "collected_date": it.collected_date,
                "collector": it.collector,
            }
            for it in items
        ],
        columns=[
            "item_id",
            "category",
            "source_product_type",
            "gender",
            "formality",
            "image_path",
            "title_vi",
            "desc_vi",
            "colors",
            "collected_date",
            "collector",
        ],
    )


def to_links_frame(items: list[NormalizedItem]) -> pd.DataFrame:
    """One store-link row per normalized item."""
    return pd.DataFrame(
        [
            {
                "item_id": it.item_id,
                "store_id": it.store_id,
                "source_product_id": it.source_product_id,
                "product_url": it.product_url,
                "price_vnd": int(it.price_vnd),
                "sale_price_vnd": (int(it.sale_price_vnd) if it.sale_price_vnd else None),
                "sku": it.sku,
                "in_stock": bool(it.in_stock),
                "available_sizes": json.dumps(it.available_sizes, ensure_ascii=False),
                "sizes_in_stock": json.dumps(it.sizes_in_stock, ensure_ascii=False),
            }
            for it in items
        ],
        columns=list(LINK_COLUMNS),
    )


def write_frames(items: list[NormalizedItem]) -> tuple[Path, Path]:
    """Append-merge normalized items into the catalog parquet files.

    De-dup strategy:
        * catalog_metadata: keep latest by item_id (allows parser fixes on re-scrape).
        * item_store_links: keep latest by (item_id, store_id).
    """
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    new_cat = to_catalog_frame(items)
    new_link = to_links_frame(items)

    if CATALOG_PARQUET.exists():
        old = pd.read_parquet(CATALOG_PARQUET)
        new_cat = pd.concat([old, new_cat], ignore_index=True).drop_duplicates(
            subset=["item_id"], keep="last"
        )
    if LINKS_PARQUET.exists():
        old = pd.read_parquet(LINKS_PARQUET)
        new_link = pd.concat([old, new_link], ignore_index=True).drop_duplicates(
            subset=["item_id", "store_id"], keep="last"
        )

    new_cat.to_parquet(CATALOG_PARQUET, index=False)
    new_link.to_parquet(LINKS_PARQUET, index=False)
    logger.info(
        "wrote %d catalog rows / %d link rows → %s, %s",
        len(new_cat),
        len(new_link),
        CATALOG_PARQUET,
        LINKS_PARQUET,
    )
    return CATALOG_PARQUET, LINKS_PARQUET


def next_index() -> int:
    """Public helper for the orchestrator."""
    return _existing_max_index(CATALOG_PARQUET) + 1


def ensure_image_dir() -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_DIR
