"""Generic Shopify / Haravan `/products.json` adapter.

Both platforms (Shopify proper and the VN-popular Haravan) expose the same
public JSON envelope:

    GET {website}/products.json?page=N&limit=250
    → {"products": [{
        "id": int, "title": str, "handle": str, "vendor": str,
        "product_type": str, "tags": list[str] | str,
        "variants": [{"id": int, "sku": str, "price": "299000",
                      "available": bool, "option1": str, ...}],
        "images":   [{"src": str, "position": int, "id": int}],
        ... }]}

Empty `products` array → end of pagination.

This module returns *normalized raw records* (still raw, not the project
schema) — see normalize.py for the schema-mapping layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .base import fetch_json
from .config import StoreConfig

logger = logging.getLogger(__name__)


@dataclass
class RawProduct:
    """One product, platform-agnostic shape consumed by normalize.py."""

    source_store_id: str
    source_product_id: str
    handle: str  # slug used in canonical URL
    title: str
    vendor: str
    product_type: str
    tags: list[str]
    description_html: str
    images: list[str]
    variants: list[dict[str, Any]] = field(default_factory=list)
    product_url: str = ""

    @property
    def min_price_vnd(self) -> int | None:
        prices: list[int] = []
        for v in self.variants:
            price = _to_int_price(v.get("price"))
            if price is not None and price > 0:
                prices.append(price)
        return min(prices) if prices else None

    @property
    def min_sale_price_vnd(self) -> int | None:
        prices = []
        for v in self.variants:
            cmp_at = _to_int_price(v.get("compare_at_price"))
            price = _to_int_price(v.get("price"))
            if cmp_at and price and price < cmp_at:
                prices.append(price)
        return min(prices) if prices else None

    @property
    def any_in_stock(self) -> bool:
        return any(bool(v.get("available")) for v in self.variants) if self.variants else True

    @property
    def primary_sku(self) -> str:
        for v in self.variants:
            sku = (v.get("sku") or "").strip()
            if sku:
                return sku
        return ""


def _to_int_price(raw: Any) -> int | None:
    """Coerce Shopify/Haravan price ('299000' or '299000.00' or 299000) → int VND.

    Returns None when invalid or absurd (likely USD-cents, see Shopify).
    """
    if raw is None:
        return None
    try:
        f = float(str(raw).replace(",", ""))
    except ValueError:
        return None
    n = int(round(f))
    if n <= 0:
        return None
    # Shopify International often returns cents; if a "price" < 100k we treat as suspect
    # but allow it (some boutique items genuinely < 100k? unlikely for clothing). Caller
    # can re-validate in normalize.py.
    return n


def fetch_products(
    client: httpx.Client,
    store: StoreConfig,
    *,
    use_cache: bool = True,
    page_size: int = 250,
    offline: bool = False,
    product_limit: int | None = None,
) -> list[RawProduct]:
    """Paginate a Shopify/Haravan-style products feed.

    Tries endpoint variants in order until one yields products:
        1. /products.json                       (vanilla Shopify)
        2. /collections/all/products.json       (Haravan + Shopify with disabled root feed)

    Both platforms accept ``?page=N&limit=250``. The first endpoint that
    returns >=1 product on page 1 wins; we then paginate it to the end.
    """
    endpoints = (
        ("root", "/products.json"),
        ("collections", "/collections/all/products.json"),
    )
    for tag, path in endpoints:
        out = _crawl_endpoint(
            client,
            store,
            path,
            endpoint_tag=tag,
            use_cache=use_cache,
            page_size=page_size,
            offline=offline,
            product_limit=product_limit,
        )
        if out:
            logger.info("[%s] endpoint=%s yielded %d products", store.store_id, tag, len(out))
            return out
        logger.info("[%s] endpoint=%s empty, trying next", store.store_id, tag)
    logger.warning("[%s] no products endpoint worked", store.store_id)
    return []


def _crawl_endpoint(
    client: httpx.Client,
    store: StoreConfig,
    path: str,
    *,
    endpoint_tag: str,
    use_cache: bool,
    page_size: int,
    offline: bool,
    product_limit: int | None,
) -> list[RawProduct]:
    out: list[RawProduct] = []
    seen_ids: set[str] = set()
    for page in range(1, store.max_pages + 1):
        key = f"{endpoint_tag}_products_page_{page:02d}"
        url = f"{store.website}{path}?page={page}&limit={page_size}"
        result = fetch_json(
            client,
            url,
            store_id=store.store_id,
            cache_key=key,
            use_cache=use_cache,
            offline=offline,
        )
        if result.status != 200 or not isinstance(result.json_body, dict):
            logger.debug(
                "[%s/%s] stop at page %d (status=%s)",
                store.store_id,
                endpoint_tag,
                page,
                result.status,
            )
            break
        products = result.json_body.get("products") or []
        if not products:
            break
        new_this_page = 0
        for raw in products:
            rp = _to_raw_product(raw, store)
            if rp.source_product_id in seen_ids:
                continue
            seen_ids.add(rp.source_product_id)
            out.append(rp)
            new_this_page += 1
            if product_limit and len(out) >= product_limit:
                return out
        logger.debug(
            "[%s/%s] page %d → %d products (+%d new, cumul=%d)",
            store.store_id,
            endpoint_tag,
            page,
            len(products),
            new_this_page,
            len(out),
        )
        if new_this_page == 0:
            break
    return out


def _to_raw_product(raw: dict[str, Any], store: StoreConfig) -> RawProduct:
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    images_raw = raw.get("images") or []
    images: list[str] = []
    for img in images_raw:
        src = (img.get("src") or "") if isinstance(img, dict) else str(img)
        if src:
            images.append(src)
    handle = (raw.get("handle") or raw.get("alias") or "").strip()
    url_path = (raw.get("url") or "").strip()
    if not handle and url_path:
        handle = url_path.rstrip("/").split("/")[-1]
    if url_path.startswith("http://") or url_path.startswith("https://"):
        product_url = url_path
    elif url_path.startswith("/"):
        product_url = f"{store.website}{url_path}"
    elif handle:
        product_url = f"{store.website}/products/{handle}"
    else:
        product_url = ""
    return RawProduct(
        source_store_id=store.store_id,
        source_product_id=str(raw.get("id") or handle or ""),
        handle=handle,
        title=(raw.get("title") or raw.get("name") or "").strip(),
        vendor=(raw.get("vendor") or "").strip(),
        product_type=(raw.get("product_type") or "").strip(),
        tags=[str(t) for t in tags],
        description_html=raw.get("body_html") or raw.get("content") or raw.get("summary") or "",
        images=images,
        variants=list(raw.get("variants") or []),
        product_url=product_url,
    )
