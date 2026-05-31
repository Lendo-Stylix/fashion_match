"""Sitemap-based fallback adapters.

Why this exists: most VN fashion sites in `link_web.txt` are not vanilla
Shopify. Several still expose high-quality product discovery through XML
sitemaps, but hide or disable `/products.json`.

Adapters exported here still return `shopify.RawProduct` so normalize.py and
the image/downstream code stay unchanged.
"""

from __future__ import annotations

import html
import logging
import re
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import fetch_json, fetch_text
from .config import StoreConfig
from .shopify import RawProduct

logger = logging.getLogger(__name__)

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_IMAGE_LOC_RE = re.compile(r"<image:loc>\s*(.*?)\s*</image:loc>", re.IGNORECASE | re.DOTALL)
_IMAGE_TITLE_RE = re.compile(r"<image:title>\s*(.*?)\s*</image:title>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(
    r"<meta\s+[^>]*(?:property|name)=[\"']"
    r"(?P<key>og:[^\"']+|twitter:[^\"']+)[\"'][^>]*"
    r"content=[\"'](?P<val>[^\"']*)[\"'][^>]*>",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"(?:sale_price|original_price|price|final_price|retail_price)"
    r"\"?\s*[:=]\s*\"?(?P<n>\d{5,9})(?:\.0+)?\"?",
    re.IGNORECASE,
)
_DISPLAY_PRICE_RE = re.compile(
    r"(?P<n>\d{2,3}(?:[.,]\d{3}){1,2})\s*(?:đ|VND|VNĐ)",
    re.IGNORECASE,
)


def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _locs(xml: str) -> list[str]:
    return [html.unescape(m.strip()) for m in _LOC_RE.findall(xml or "")]


def _sitemap_urls(
    client: httpx.Client,
    store: StoreConfig,
    *,
    use_cache: bool,
    offline: bool,
) -> list[str]:
    root = fetch_text(
        client,
        f"{store.website}/sitemap.xml",
        store_id=store.store_id,
        cache_key="sitemap_root",
        use_cache=use_cache,
        offline=offline,
    )
    if root.status != 200 or not root.text:
        return []
    locs = _locs(root.text)
    # Sitemap index: choose product-looking child sitemaps first, otherwise root itself.
    children = [
        u
        for u in locs
        if "sitemap" in u.lower() and ("product" in u.lower() or "products" in u.lower())
    ]
    if not children and "<sitemapindex" in root.text.lower():
        children = [u for u in locs if u.endswith(".xml")]
    if not children:
        return [f"{store.website}/sitemap.xml"]
    return children[: max(1, store.max_pages)]


def _product_urls_from_xml(
    xml: str, store: StoreConfig
) -> list[tuple[str, str | None, str | None]]:
    """Return (loc, image_url, image_title)."""
    rows: list[tuple[str, str | None, str | None]] = []
    for block in re.findall(r"<url>.*?</url>", xml or "", re.IGNORECASE | re.DOTALL):
        loc_m = _LOC_RE.search(block)
        if not loc_m:
            continue
        loc = html.unescape(loc_m.group(1).strip())
        host = urlparse(store.website).netloc.replace("www.", "")
        loc_host = urlparse(loc).netloc.replace("www.", "")
        if host not in loc_host:
            continue
        # Keep only likely product pages, not category/listing/pages.
        path = urlparse(loc).path.lower()
        likely = (
            "/products/" in path
            or "/product/" in path
            or bool(re.search(r"/[a-z0-9-]+(?:-[a-z]{1,4}\d{2,}|-[0-9]{4,}|z\d{5,})$", path))
        )
        if not likely:
            continue
        img = None
        title = None
        im = _IMAGE_LOC_RE.search(block)
        tm = _IMAGE_TITLE_RE.search(block)
        if im:
            img = html.unescape(im.group(1).strip())
        if tm:
            title = html.unescape(_strip_tags(tm.group(1)))
        rows.append((loc, img, title))
    return rows


def discover_product_urls(
    client: httpx.Client,
    store: StoreConfig,
    *,
    use_cache: bool = True,
    offline: bool = False,
    product_limit: int | None = None,
) -> list[tuple[str, str | None, str | None]]:
    rows: list[tuple[str, str | None, str | None]] = []
    seen: set[str] = set()
    sitemaps = _sitemap_urls(client, store, use_cache=use_cache, offline=offline)
    for i, sm_url in enumerate(sitemaps, start=1):
        res = fetch_text(
            client,
            sm_url,
            store_id=store.store_id,
            cache_key=f"sitemap_child_{i:02d}",
            use_cache=use_cache,
            offline=offline,
        )
        if res.status != 200 or not res.text:
            continue
        for row in _product_urls_from_xml(res.text, store):
            if row[0] in seen:
                continue
            seen.add(row[0])
            rows.append(row)
            if product_limit and len(rows) >= product_limit:
                return rows
    return rows


def fetch_products_via_product_json(
    client: httpx.Client,
    store: StoreConfig,
    *,
    use_cache: bool = True,
    offline: bool = False,
    product_limit: int | None = None,
) -> list[RawProduct]:
    """Sitemap → per-product `.json` (works on Aristino/Haravan-hidden feeds)."""
    out: list[RawProduct] = []
    for loc, _, _ in discover_product_urls(
        client, store, use_cache=use_cache, offline=offline, product_limit=product_limit
    ):
        json_url = loc.rstrip("/") + ".json"
        slug = urlparse(loc).path.strip("/").replace("/", "_") or "product"
        res = fetch_json(
            client,
            json_url,
            store_id=store.store_id,
            cache_key=f"product_json_{slug}",
            use_cache=use_cache,
            offline=offline,
        )
        if res.status != 200 or not isinstance(res.json_body, dict):
            continue
        raw = res.json_body.get("product") or res.json_body
        if isinstance(raw, dict):
            out.append(_to_raw_product_with_url(raw, store, loc))
    logger.info("[%s] sitemap_product_json yielded %d products", store.store_id, len(out))
    return out


def fetch_products_via_html(
    client: httpx.Client,
    store: StoreConfig,
    *,
    use_cache: bool = True,
    offline: bool = False,
    product_limit: int | None = None,
) -> list[RawProduct]:
    """Sitemap → product HTML → OG meta + price regex.

    This is a fallback for custom sites (YODY/Canifa). It is intentionally
    conservative: products without title/image/price are dropped by normalize.py.
    """
    out: list[RawProduct] = []
    for loc, sitemap_img, sitemap_title in discover_product_urls(
        client, store, use_cache=use_cache, offline=offline, product_limit=product_limit
    ):
        slug = urlparse(loc).path.strip("/").replace("/", "_") or "product"
        res = fetch_text(
            client,
            loc,
            store_id=store.store_id,
            cache_key=f"product_html_{slug}",
            use_cache=use_cache,
            offline=offline,
        )
        if res.status != 200 or not res.text:
            continue
        raw = _html_to_raw(
            res.text,
            store,
            loc,
            sitemap_img=sitemap_img,
            sitemap_title=sitemap_title,
        )
        if raw:
            out.append(raw)
    logger.info("[%s] sitemap_html yielded %d products", store.store_id, len(out))
    return out


def _to_raw_product_with_url(
    raw: dict[str, Any], store: StoreConfig, product_url: str
) -> RawProduct:
    from .shopify import _to_raw_product  # reuse tested mapper

    rp = _to_raw_product(raw, store)
    rp.product_url = product_url
    if not rp.handle:
        rp.handle = urlparse(product_url).path.rstrip("/").split("/")[-1]
    if not rp.source_product_id:
        rp.source_product_id = rp.handle
    return rp


def _html_to_raw(
    html_text: str,
    store: StoreConfig,
    product_url: str,
    *,
    sitemap_img: str | None,
    sitemap_title: str | None,
) -> RawProduct | None:
    metas: dict[str, str] = {}
    for m in _META_RE.finditer(html_text):
        metas[m.group("key").lower()] = html.unescape(m.group("val").strip())
    title = sitemap_title or metas.get("og:title") or metas.get("twitter:title")
    desc = metas.get("og:description") or metas.get("twitter:description") or ""
    image = sitemap_img or metas.get("og:image") or metas.get("twitter:image")
    price = _extract_price(html_text)
    if not title or not image or not price:
        return None
    handle = urlparse(product_url).path.rstrip("/").split("/")[-1]
    return RawProduct(
        source_store_id=store.store_id,
        source_product_id=handle,
        handle=handle,
        title=title.strip(),
        vendor=store.store_name,
        product_type="",
        tags=[],
        description_html=desc,
        images=[image],
        variants=[{"sku": handle, "price": price, "available": True}],
        product_url=product_url,
    )


def _extract_price(html_text: str) -> int | None:
    structured: list[int] = []
    for m in _PRICE_RE.finditer(html_text):
        with suppress(ValueError):
            structured.append(int(m.group("n")))
    plausible = [n for n in structured if 30_000 <= n <= 50_000_000]
    if plausible:
        return min(plausible)

    displayed: list[int] = []
    for m in _DISPLAY_PRICE_RE.finditer(html_text):
        raw = m.group("n").replace(".", "").replace(",", "")
        with suppress(ValueError):
            displayed.append(int(raw))
    plausible = [n for n in displayed if 30_000 <= n <= 50_000_000]
    return min(plausible) if plausible else None
