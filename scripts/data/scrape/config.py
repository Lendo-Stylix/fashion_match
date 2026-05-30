"""Store registry: brand → platform/style/tier metadata used by the scraper.

`platform` controls which adapter is dispatched in run.py:
  - "shopify_like"         → scripts.data.scrape.shopify (/products.json feeds).
  - "sitemap_product_json" → sitemap URLs + per-product `.json`.
  - "sitemap_html"         → sitemap URLs + product HTML OpenGraph/price fallback.
  - "skip"                 → not scraped yet (manual / unsupported platform).

`price_tier`, `style_tags`, `target_gender` mirror the SQLite seed in
docs/datasets/STORE_CATALOG_VN.md §3 — values MUST be valid `vocab.py` enums.

Add a new store by appending a row here AND in build_registry.py if you want
it in the SQLite registry as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoreConfig:
    store_id: str                  # snake_case, used as folder + FK
    store_name: str
    website: str                   # base URL, no trailing slash
    platform: str                  # shopify_like | sitemap_product_json | sitemap_html | skip
    store_type: str                # chain_brand | local_boutique | ecommerce_only | etc.
    price_tier: str                # PRICE_TIER enum
    target_gender: str             # women | men | unisex
    style_tags: tuple[str, ...]    # subset of STYLE enum
    max_pages: int = 40            # pagination cap (250 items/page)
    notes: str = ""
    extra_paths: tuple[str, ...] = field(default_factory=tuple)
    # optional per-collection product feeds (handle, not URL)
    collections: tuple[str, ...] = field(default_factory=tuple)


# ── Mainstream chain brands (link_web.txt — confirmed e-commerce) ─────────────
STORES: tuple[StoreConfig, ...] = (
    StoreConfig(
        store_id="yody_vn",
        store_name="YODY",
        website="https://yody.vn",
        platform="sitemap_html",
        store_type="chain_brand",
        price_tier="budget",
        target_gender="unisex",
        style_tags=("casual", "sporty"),
        max_pages=2,
        notes="Custom site: sitemap has product URL/image/title; page embeds variants/prices.",
    ),
    StoreConfig(
        store_id="canifa_vn",
        store_name="Canifa",
        website="https://canifa.com",
        platform="sitemap_html",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("casual", "minimalist"),
        max_pages=1,
        notes="Magento/Nuxt: sitemap + OG metadata + inline price fallback.",
    ),
    StoreConfig(
        store_id="coolmate_me",
        store_name="Coolmate",
        website="https://www.coolmate.me",
        platform="skip",
        store_type="ecommerce_only",
        price_tier="budget",
        target_gender="unisex",
        style_tags=("sporty", "casual"),
        notes="Custom Next.js; no sitemap/products.json discovered — needs browser/API adapter.",
    ),
    StoreConfig(
        store_id="ivymoda_vn",
        store_name="IVY moda",
        website="https://ivymoda.com",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("elegant", "feminine"),
        notes="Custom sitemap/product pages; needs site-specific HTML/API adapter.",
    ),
    StoreConfig(
        store_id="routine_vn",
        store_name="Routine",
        website="https://routine.vn",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("casual", "minimalist"),
        notes="Cloudflare/custom Next.js; no public product JSON.",
    ),
    StoreConfig(
        store_id="gumac_vn",
        store_name="GUMAC",
        website="https://gumac.vn",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes="Custom SPA; sitemap mostly category pages; needs rendered/API adapter.",
    ),
    StoreConfig(
        store_id="aristino_vn",
        store_name="Aristino",
        website="https://aristino.com",
        platform="sitemap_product_json",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="men",
        style_tags=("elegant",),
        max_pages=2,
        notes="Haravan hidden feed: sitemap product URLs support `/products/<handle>.json`.",
    ),
    StoreConfig(
        store_id="juno_vn",
        store_name="JUNO",
        website="https://juno.vn",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes="Phụ kiện nữ; custom Next.js, no sitemap/products.json — needs browser/API adapter.",
    ),
    StoreConfig(
        store_id="vascara_vn",
        store_name="Vascara",
        website="https://vascara.com",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes=(
            "Phụ kiện nữ; sitemap category-heavy, product extraction needs site-specific adapter."
        ),
    ),
    StoreConfig(
        store_id="elise_vn",
        store_name="Elise",
        website="https://elise.vn",
        platform="skip",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes="Custom platform, no products.json — manual collection",
    ),
    # ── Boutique / streetwear / TikTok-hot brands (link_web.txt §2) ───────
    StoreConfig(
        store_id="fanciclub",
        store_name="Fancì Club",
        website="https://fanciclub.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="women",
        style_tags=("elegant", "feminine"),
        notes="Custom Next.js; no sitemap/products.json — needs browser/API adapter.",
    ),
    StoreConfig(
        store_id="lsoul",
        store_name="LSOUL",
        website="https://lsoul.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes="Magento-like sitemap but product pages need site-specific parser/API.",
    ),
    StoreConfig(
        store_id="beuter",
        store_name="Beuter",
        website="https://beuterdesign.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="unisex",
        style_tags=("streetwear", "minimalist"),
        notes="Sitemap points to thebeuter.com; no product JSON — needs HTML parser.",
    ),
    StoreConfig(
        store_id="kilomet109",
        store_name="Kilomet 109",
        website="https://www.kilomet109.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="women",
        style_tags=("vintage", "elegant"),
        notes="Squarespace — manual collection",
    ),
    StoreConfig(
        store_id="aeie",
        store_name="AEIE Studio",
        website="https://aeiestudios.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="unisex",
        style_tags=("minimalist", "vintage"),
        notes="WordPress/WooCommerce-style site; needs dedicated adapter.",
    ),
    StoreConfig(
        store_id="huelleyrose",
        store_name="Huelley Rose",
        website="https://huelleyrose.com",
        platform="shopify_like",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="women",
        style_tags=("vintage", "elegant"),
    ),
    StoreConfig(
        store_id="dirtycoins",
        store_name="Dirty Coins",
        website="https://dirtycoins.vn",
        platform="shopify_like",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("streetwear",),
    ),
    StoreConfig(
        store_id="hades_studio",
        store_name="Hades Studio",
        website="https://hades.studio",
        platform="skip",
        store_type="local_boutique",
        price_tier="premium",
        target_gender="unisex",
        style_tags=("streetwear",),
        notes="Products endpoint returns 401; likely bot/auth-protected.",
    ),
    StoreConfig(
        store_id="levents",
        store_name="Levents",
        website="https://levents.vn",
        platform="skip",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("streetwear", "casual"),
        notes=(
            "Products endpoint returns 406; sitemap not public — "
            "needs dedicated API/browser adapter."
        ),
    ),
    StoreConfig(
        store_id="rubies",
        store_name="Rubies",
        website="https://www.rubies.vn",
        platform="shopify_like",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "korean"),
    ),
    StoreConfig(
        store_id="dearjose",
        store_name="Dear José",
        website="https://dearjose.com",
        platform="skip",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="women",
        style_tags=("feminine", "elegant"),
        notes="Custom Next.js; no sitemap/products.json — needs browser/API adapter.",
    ),
)

STORES_BY_ID: dict[str, StoreConfig] = {s.store_id: s for s in STORES}


def active_stores() -> list[StoreConfig]:
    """Stores that have a working adapter (skip placeholders excluded)."""
    return [s for s in STORES if s.platform != "skip"]
