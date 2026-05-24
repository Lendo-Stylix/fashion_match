"""
sites/gumac.py — Scraper chuyên biệt cho gumac.vn

Tech stack: React SPA (custom)
Strategy:
  1. Lấy danh sách URL sản phẩm từ sitemap.xml (có lastmod → tốt cho incremental)
  2. Cho mỗi sản phẩm: navigate → chờ React render → lấy HTML/AX Tree → parse
  3. Thử JSON-LD trước, sau đó dùng AX Tree static texts
"""

import re
import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.async_api import Page

from core.browser import navigate_and_wait, get_page_html, get_full_ax_tree, scroll_to_bottom
from core.ax_utils import filter_ignored, extract_static_texts
from core.payload_parser import parse_json_ld, extract_product_from_json_ld
import config


BASE_URL = "https://gumac.vn"
BRAND = "GUMAC"
SITEMAP_URL = "https://gumac.vn/sitemap.xml"

# Patterns để xác định URL sản phẩm (có SKU như df12025, ag01003...)
PRODUCT_URL_RE = re.compile(
    r"^https://gumac\.vn/[\w-]+/[a-z]{2,4}[\w\d]{4,}$",
    re.IGNORECASE
)

EXCLUDE_PATTERNS = [
    r"/tin-tuc/", r"/bo-suu-tap/", r"/sale-off/", r"/showrooms",
    r"/gioi-thieu", r"/tuyen-dung", r"/huong-dan-", r"/chinh-sach-",
    r"/lien-he", r"/dang-ky", r"/quen-mat-khau", r"/gio-hang",
    r"/dang-nhap", r"/nang-hoi-gu-dap", r"/gmorning$", r"/aleeva$",
]


# ── Lấy danh sách URL sản phẩm từ Sitemap ────────────────────────────────────

def get_product_urls_from_sitemap() -> list[tuple[str, Optional[str]]]:
    """
    Parse sitemap.xml của Gumac, trả về list (url, lastmod) cho các trang sản phẩm.
    Dùng requests tĩnh vì sitemap là XML không cần JS.
    Returns: list of (url, lastmod_str or None)
    """
    print(f"[Gumac] Đang tải sitemap: {SITEMAP_URL}")
    try:
        with urlopen(SITEMAP_URL, timeout=30) as resp:
            xml_content = resp.read()
    except Exception as e:
        print(f"[Gumac] LỖI tải sitemap: {e}")
        return []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"[Gumac] LỖI parse XML: {e}")
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    results = []

    for url_el in root.findall("sm:url", ns):
        loc = url_el.findtext("sm:loc", namespaces=ns) or ""
        lastmod = url_el.findtext("sm:lastmod", namespaces=ns)

        # Kiểm tra có phải URL sản phẩm không
        if not PRODUCT_URL_RE.match(loc):
            continue

        # Loại bỏ URL không phải sản phẩm
        excluded = any(re.search(pat, loc) for pat in EXCLUDE_PATTERNS)
        if excluded:
            continue

        results.append((loc, lastmod))

    print(f"[Gumac] Tìm thấy {len(results)} URL sản phẩm trong sitemap.")
    return results


# ── Parse thông tin sản phẩm ─────────────────────────────────────────────────

def _make_product_id(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"gumac_{slug}_{h}"


def _extract_price(val) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d]", "", val)
        return int(cleaned) if cleaned else None
    return None


def _infer_gender_from_url(url: str) -> str:
    """Suy đoán giới tính từ URL."""
    url_lower = url.lower()
    if "-nam" in url_lower or "/nam/" in url_lower:
        return "male"
    if "-nu" in url_lower or "/nu/" in url_lower or "gumac" in url_lower:
        return "female"
    return "female"  # Gumac chủ yếu thời trang nữ


def _infer_categories_from_url(url: str) -> list[str]:
    """Suy đoán category từ slug URL."""
    path = urlparse(url).path.strip("/")
    segments = path.split("/")
    if not segments:
        return []
    cat_slug = segments[0]

    mapping = {
        "vay-dam": ["bottoms", "dresses"],
        "dam-xep-ly": ["bottoms", "dresses", "pleated"],
        "vay-dam-form-a": ["bottoms", "dresses", "a-line"],
        "vay-dam-cong-so": ["bottoms", "dresses", "formal"],
        "vay-dam-du-tiec": ["bottoms", "dresses", "party"],
        "ao-so-mi": ["tops", "shirts"],
        "ao-thun": ["tops", "t-shirts"],
        "ao-khoac": ["outerwear", "jackets"],
        "ao-vest": ["outerwear", "blazers"],
        "ao-kieu": ["tops", "blouses"],
        "ao-len": ["tops", "sweaters"],
        "quan-short": ["bottoms", "shorts"],
        "quan-dai": ["bottoms", "trousers"],
        "quan-tay": ["bottoms", "trousers"],
        "quan-jeans": ["bottoms", "jeans"],
        "chan-vay": ["bottoms", "skirts"],
        "jumpsuit": ["one-pieces", "jumpsuits"],
        "giay-dep": ["accessories", "shoes"],
    }

    for key, cats in mapping.items():
        if key in cat_slug:
            return cats
    return [cat_slug]


def parse_product_from_json_ld_data(json_ld_product: dict, source_url: str, lastmod: Optional[str] = None) -> dict:
    """
    Parse dữ liệu sản phẩm từ JSON-LD Product schema.
    """
    name = json_ld_product.get("name") or ""
    description = json_ld_product.get("description") or ""
    desc_clean = re.sub(r"<[^>]+>", " ", description).strip()

    # Giá
    offers = json_ld_product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = _extract_price(offers.get("price") or offers.get("lowPrice"))
    original_price = _extract_price(
        offers.get("highPrice") or offers.get("originalPrice") or price
    )
    discount = None
    if price and original_price and original_price > price:
        discount = round((1 - price / original_price) * 100)

    # Images
    images_raw = json_ld_product.get("image") or []
    if isinstance(images_raw, str):
        images_raw = [images_raw]
    images = [
        {"url": img, "alt": name, "type": "main" if i == 0 else "gallery", "color": None}
        for i, img in enumerate(images_raw)
    ]

    # Availability
    availability = offers.get("availability") or ""
    in_stock = "InStock" in availability or "InStock" in str(offers)

    # Rating
    rating_obj = json_ld_product.get("aggregateRating") or {}
    rating = float(rating_obj.get("ratingValue") or 0) or None
    review_count = int(rating_obj.get("reviewCount") or 0) or None

    gender = _infer_gender_from_url(source_url)
    categories = _infer_categories_from_url(source_url)

    return {
        "product_id": _make_product_id(source_url),
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "lastmod": lastmod,
        "brand": BRAND,
        "source_domain": "gumac.vn",

        "name": name,
        "price": price,
        "original_price": original_price,
        "discount_percent": discount,
        "currency": "VND",

        "categories": categories,
        "gender": gender,
        "collection": json_ld_product.get("collection") or None,

        "description_short": desc_clean[:200],
        "description_full": desc_clean,
        "care_instructions": [],
        "tags": json_ld_product.get("keywords") or [],
        "style_tags": [],
        "season": ["all_season"],

        "attributes": {
            "material": json_ld_product.get("material") or None,
            "material_weight": None,
            "fit_type": None,
            "neckline": None,
            "sleeve_length": None,
            "bottom_length": None,
            "pattern": None,
            "technology": [],
            "raw": {},
        },

        "variants": [],
        "colors": [],
        "sizes": [],

        "images": images,

        "rating": rating,
        "review_count": review_count,

        "related_products": [],
        "outfit_suggestions": [],
        "_parse_method": "json_ld",
    }


def parse_product_from_ax_texts(texts: list[str], source_url: str, lastmod: Optional[str] = None) -> dict:
    """Fallback parse từ AX Tree static texts."""
    product_id = _make_product_id(source_url)
    name = ""
    price = None
    desc_parts = []

    for text in texts:
        text = text.strip()
        if not text:
            continue

        price_match = re.search(r"(\d{2,3}(?:[.,]\d{3})+)\s*(?:đ|VND|₫)?", text)
        if price_match and price is None:
            price_str = re.sub(r"[.,]", "", price_match.group(1))
            price = int(price_str) if price_str.isdigit() else None
            if not name:
                name = text.replace(price_match.group(0), "").strip()
            continue

        if not name and len(text) > 5 and not text.startswith("http"):
            name = text
            continue

        if len(text) > 20:
            desc_parts.append(text)

    return {
        "product_id": product_id,
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "lastmod": lastmod,
        "brand": BRAND,
        "source_domain": "gumac.vn",
        "name": name,
        "price": price,
        "original_price": None,
        "discount_percent": None,
        "currency": "VND",
        "categories": _infer_categories_from_url(source_url),
        "gender": _infer_gender_from_url(source_url),
        "collection": None,
        "description_short": desc_parts[0] if desc_parts else "",
        "description_full": " | ".join(desc_parts),
        "care_instructions": [],
        "tags": [],
        "style_tags": [],
        "season": ["all_season"],
        "attributes": {"raw": {}},
        "variants": [],
        "colors": [],
        "sizes": [],
        "images": [],
        "rating": None,
        "review_count": None,
        "related_products": [],
        "outfit_suggestions": [],
        "_parse_method": "ax_tree_fallback",
    }


# ── Scrape 1 sản phẩm ─────────────────────────────────────────────────────────

async def scrape_product(page: Page, url: str, lastmod: Optional[str] = None) -> Optional[dict]:
    """
    Scrape đầy đủ thông tin 1 sản phẩm Gumac.
    Returns dict sản phẩm hoặc None nếu thất bại.
    """
    ok = await navigate_and_wait(page, url)
    if not ok:
        return None

    # Gumac là React SPA, cần chờ thêm để JS render
    await page.wait_for_timeout(2000)

    html = await get_page_html(page)

    # ── Phương pháp 1: JSON-LD ────────────────────────────────────────────
    json_ld_list = parse_json_ld(html)
    json_ld_product = extract_product_from_json_ld(json_ld_list)
    if json_ld_product and json_ld_product.get("name"):
        product = parse_product_from_json_ld_data(json_ld_product, url, lastmod)

        # Bổ sung variants từ trang nếu có
        try:
            variants_js = await page.evaluate("""
                () => {
                    // Tìm biến variants trong global state (nếu có)
                    const data = window.__STORE_STATE__ || window.__redux_state__ || null;
                    return data ? JSON.stringify(data) : null;
                }
            """)
            if variants_js:
                store_data = json.loads(variants_js)
                # TODO: parse variants từ store state nếu tìm thấy
        except Exception:
            pass

        # Lấy danh sách size và màu từ DOM (Gumac React render ra DOM)
        try:
            sizes = await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('[class*="size"] button, [class*="Size"] button');
                    return [...btns].map(b => b.textContent.trim()).filter(t => t && t.length <= 5);
                }
            """)
            colors = await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('[class*="color"] [title], [class*="Color"] [title]');
                    return [...btns].map(b => b.getAttribute('title') || b.textContent.trim()).filter(Boolean);
                }
            """)
            if sizes:
                product["sizes"] = list(set(sizes))
            if colors:
                product["colors"] = list(set(colors))
        except Exception:
            pass

        return product

    # ── Phương pháp 2: Fallback AX Tree ──────────────────────────────────
    print(f"[Gumac] JSON-LD không đủ cho {url}, dùng AX Tree fallback...")
    try:
        ax_raw = await get_full_ax_tree(page)
        ax_filtered = filter_ignored(ax_raw)
        texts = extract_static_texts(ax_filtered)
        product = parse_product_from_ax_texts(texts, url, lastmod)
        if product.get("name"):
            return product
    except Exception as e:
        print(f"[Gumac] LỖI AX Tree: {e}")

    return None
