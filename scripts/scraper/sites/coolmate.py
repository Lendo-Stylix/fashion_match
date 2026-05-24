"""
sites/coolmate.py — Scraper chuyên biệt cho coolmate.me

Tech stack: Nuxt.js (Vue, SSR)
Strategy:
  1. Lấy danh sách URL sản phẩm từ trang listing (scroll + extract links)
  2. Cho mỗi sản phẩm: navigate → lấy HTML → parse __NUXT_DATA__
  3. Fallback: dùng AX Tree + heuristic nếu __NUXT_DATA__ không đủ
"""

import re
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page

from core.browser import navigate_and_wait, scroll_to_bottom, get_page_html, get_full_ax_tree
from core.ax_utils import filter_ignored, extract_static_texts
from core.payload_parser import parse_nuxt_data, parse_json_ld, extract_product_from_json_ld
import config


BASE_URL = "https://www.coolmate.me"
BRAND = "Coolmate"


# ── Lấy danh sách URL sản phẩm ───────────────────────────────────────────────

async def get_product_urls_from_collection(page: Page, category_slug: str) -> list[str]:
    """
    Vào trang collection, scroll xuống hết, lấy tất cả link sản phẩm.
    """
    collection_url = f"{BASE_URL}/collection/{category_slug}"
    print(f"[Coolmate] Đang lấy URL từ: {collection_url}")

    ok = await navigate_and_wait(page, collection_url)
    if not ok:
        return []

    # Scroll để lazy load
    await scroll_to_bottom(page, pause=1.5)

    # Lấy tất cả href có /product/
    links = await page.evaluate("""
        () => {
            const anchors = document.querySelectorAll('a[href*="/product/"]');
            return [...new Set([...anchors].map(a => a.href))];
        }
    """)

    product_urls = [
        url for url in links
        if "/product/" in url and BASE_URL in url
    ]
    print(f"[Coolmate] Tìm thấy {len(product_urls)} sản phẩm trong '{category_slug}'")
    return product_urls


async def get_all_product_urls(page: Page) -> list[str]:
    """Lấy URL sản phẩm từ tất cả category trong config."""
    all_urls = set()
    site_cfg = config.SITES["coolmate"]
    for category in site_cfg["categories"]:
        urls = await get_product_urls_from_collection(page, category)
        all_urls.update(urls)
    return list(all_urls)


# ── Parse thông tin sản phẩm từ __NUXT_DATA__ ────────────────────────────────

def _make_product_id(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"coolmate_{slug}_{h}"


def _extract_price(val) -> Optional[int]:
    """Chuẩn hóa giá tiền về int (VND)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d]", "", val)
        return int(cleaned) if cleaned else None
    return None


def _find_in_nuxt(data, keys: list[str], depth: int = 0, max_depth: int = 12):
    """
    Tìm kiếm đệ quy trong cấu trúc __NUXT_DATA__ (có thể là list hoặc dict lồng nhau).
    """
    if depth > max_depth:
        return None

    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data[key]
        for v in data.values():
            result = _find_in_nuxt(v, keys, depth + 1, max_depth)
            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data:
            result = _find_in_nuxt(item, keys, depth + 1, max_depth)
            if result is not None:
                return result

    return None


def parse_product_from_nuxt(nuxt_data: dict | list, source_url: str) -> Optional[dict]:
    """
    Extract thông tin sản phẩm từ __NUXT_DATA__ payload.
    Trả về dict chuẩn hóa, sẵn sàng cho graph DB.
    """
    # Tìm data sản phẩm trong cấu trúc Nuxt (có thể lồng sâu)
    product_data = _find_in_nuxt(nuxt_data, ["product", "productDetail", "item"])
    if not product_data or not isinstance(product_data, dict):
        return None

    # ── Basic Info ────────────────────────────────────────────────────────────
    name = (
        product_data.get("name") or
        product_data.get("title") or
        product_data.get("productName") or ""
    )
    if not name:
        return None  # Không tìm được tên → skip

    price_raw = (
        product_data.get("price") or
        product_data.get("salePrice") or
        product_data.get("promotionPrice")
    )
    original_price_raw = (
        product_data.get("originalPrice") or
        product_data.get("regularPrice") or
        product_data.get("marketPrice") or
        price_raw
    )

    price = _extract_price(price_raw)
    original_price = _extract_price(original_price_raw)
    discount = None
    if price and original_price and original_price > price:
        discount = round((1 - price / original_price) * 100)

    # ── Categories ────────────────────────────────────────────────────────────
    categories_raw = (
        product_data.get("categories") or
        product_data.get("category") or
        product_data.get("breadcrumbs") or []
    )
    if isinstance(categories_raw, str):
        categories = [categories_raw]
    elif isinstance(categories_raw, list):
        categories = [
            c.get("name") or c.get("title") or c if isinstance(c, dict) else c
            for c in categories_raw
            if c
        ]
    else:
        categories = []

    # ── Description ──────────────────────────────────────────────────────────
    desc_full = (
        product_data.get("description") or
        product_data.get("content") or
        product_data.get("detail") or ""
    )
    # Xóa HTML tags nếu có
    desc_clean = re.sub(r"<[^>]+>", " ", desc_full).strip()
    desc_short = desc_clean[:200] if desc_clean else ""

    # ── Images ────────────────────────────────────────────────────────────────
    images_raw = (
        product_data.get("images") or
        product_data.get("media") or
        product_data.get("photos") or []
    )
    images = []
    for idx, img in enumerate(images_raw if isinstance(images_raw, list) else []):
        if isinstance(img, str):
            images.append({"url": img, "alt": name, "type": "main" if idx == 0 else "gallery", "color": None})
        elif isinstance(img, dict):
            images.append({
                "url": img.get("url") or img.get("src") or img.get("image") or "",
                "alt": img.get("alt") or name,
                "type": "main" if idx == 0 else "gallery",
                "color": img.get("color") or None,
            })

    # ── Variants (size × color) ───────────────────────────────────────────────
    variants_raw = (
        product_data.get("variants") or
        product_data.get("configurations") or
        product_data.get("options") or []
    )
    variants = []
    colors_set = set()
    sizes_set = set()

    for v in (variants_raw if isinstance(variants_raw, list) else []):
        if not isinstance(v, dict):
            continue
        color = v.get("color") or v.get("colorName") or v.get("option1") or None
        size = v.get("size") or v.get("sizeName") or v.get("option2") or None
        if color:
            colors_set.add(str(color))
        if size:
            sizes_set.add(str(size))
        variants.append({
            "variant_id": f"{_make_product_id(source_url)}_{color}_{size}",
            "color": color,
            "color_hex": v.get("colorHex") or v.get("hex") or None,
            "size": size,
            "in_stock": v.get("inStock") or v.get("available") or v.get("quantity", 0) > 0 or True,
            "quantity": v.get("quantity") or v.get("stock") or None,
            "price": _extract_price(v.get("price") or price_raw),
            "sku": v.get("sku") or v.get("id") or None,
        })

    # ── Attributes (chất liệu, fit, v.v.) ────────────────────────────────────
    attrs_raw = (
        product_data.get("attributes") or
        product_data.get("specifications") or
        product_data.get("properties") or {}
    )
    attrs = {}
    if isinstance(attrs_raw, dict):
        attrs = attrs_raw
    elif isinstance(attrs_raw, list):
        for item in attrs_raw:
            if isinstance(item, dict):
                k = item.get("name") or item.get("key") or ""
                v = item.get("value") or ""
                if k:
                    attrs[k] = v

    # ── Rating ────────────────────────────────────────────────────────────────
    rating_raw = (
        product_data.get("rating") or
        product_data.get("averageRating") or
        product_data.get("ratingAverage") or None
    )
    review_count = (
        product_data.get("reviewCount") or
        product_data.get("totalReview") or
        product_data.get("ratingCount") or None
    )

    # ── Tags ─────────────────────────────────────────────────────────────────
    tags = product_data.get("tags") or product_data.get("keywords") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        "product_id": _make_product_id(source_url),
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "brand": BRAND,
        "source_domain": "coolmate.me",

        "name": name,
        "price": price,
        "original_price": original_price,
        "discount_percent": discount,
        "currency": "VND",

        "categories": [c for c in categories if c],
        "gender": "male",  # Coolmate chủ yếu thời trang nam
        "collection": product_data.get("collection") or product_data.get("collectionName") or None,

        "description_short": desc_short,
        "description_full": desc_clean,
        "care_instructions": product_data.get("careInstructions") or [],
        "tags": tags,
        "style_tags": product_data.get("styleTags") or [],
        "season": product_data.get("season") or ["all_season"],

        "attributes": {
            "material": attrs.get("material") or attrs.get("Chất liệu") or attrs.get("chatLieu") or None,
            "material_weight": attrs.get("weight") or attrs.get("gramWeight") or None,
            "fit_type": attrs.get("fit") or attrs.get("fitType") or attrs.get("Kiểu dáng") or None,
            "neckline": attrs.get("neckline") or attrs.get("colAo") or None,
            "sleeve_length": attrs.get("sleeve") or attrs.get("tayAo") or None,
            "bottom_length": attrs.get("bottomLength") or None,
            "pattern": attrs.get("pattern") or attrs.get("hoaTiet") or None,
            "technology": attrs.get("technology") or attrs.get("congNghe") or [],
            "raw": attrs,
        },

        "variants": variants,
        "colors": sorted(list(colors_set)),
        "sizes": sorted(list(sizes_set)),

        "images": images,

        "rating": float(rating_raw) if rating_raw else None,
        "review_count": int(review_count) if review_count else None,

        "related_products": [],
        "outfit_suggestions": [],
    }


def parse_product_from_json_ld_data(json_ld_product: dict, source_url: str) -> dict:
    """
    Parse dữ liệu sản phẩm từ JSON-LD Product schema của Coolmate (Next.js).
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

    # Variants (nếu offers có mảng offers con)
    variants = []
    colors_set = set()
    sizes_set = set()
    
    sub_offers = offers.get("offers") or []
    if isinstance(sub_offers, list):
        for idx, sub_off in enumerate(sub_offers):
            sku = sub_off.get("sku") or ""
            variants.append({
                "variant_id": f"{_make_product_id(source_url)}_{idx}",
                "color": None,
                "color_hex": None,
                "size": None,
                "in_stock": "InStock" in sub_off.get("availability", "") or True,
                "quantity": None,
                "price": _extract_price(sub_off.get("price")),
                "sku": sku,
            })

    # Phân tích danh mục từ URL
    categories = []
    path = urlparse(source_url).path.strip("/")
    segments = path.split("/")
    if len(segments) > 0:
        categories = [segments[0]]

    return {
        "product_id": _make_product_id(source_url),
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "brand": BRAND,
        "source_domain": "coolmate.me",

        "name": name,
        "price": price,
        "original_price": original_price,
        "discount_percent": discount,
        "currency": "VND",

        "categories": categories,
        "gender": "male",
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

        "variants": variants,
        "colors": sorted(list(colors_set)),
        "sizes": sorted(list(sizes_set)),

        "images": images,

        "rating": rating,
        "review_count": review_count,

        "related_products": [],
        "outfit_suggestions": [],
    }


# ── Fallback: Parse từ AX Tree ────────────────────────────────────────────────

def parse_product_from_ax_texts(texts: list[str], source_url: str) -> dict:
    """
    Khi __NUXT_DATA__ không đủ, dùng static text từ AX Tree để heuristic parse.
    Đây là fallback, data sẽ ít đầy đủ hơn.
    """
    product_id = _make_product_id(source_url)

    # Tìm tên sản phẩm (thường là text dài đầu tiên, trước khi gặp giá)
    name = ""
    price = None
    description_parts = []

    for text in texts:
        text = text.strip()
        if not text:
            continue

        # Detect giá (chứa ký tự số + đồng/VND hoặc format xxx.xxx)
        price_match = re.search(r"(\d{2,3}(?:[.,]\d{3})+)\s*(?:đ|VND|₫)?", text)
        if price_match and price is None:
            price_str = re.sub(r"[.,]", "", price_match.group(1))
            price = int(price_str) if price_str.isdigit() else None
            if not name:
                # Text trước giá là tên sản phẩm
                name = text.replace(price_match.group(0), "").strip()
            continue

        if not name and len(text) > 5 and not text.startswith("http"):
            name = text
            continue

        if len(text) > 20:
            description_parts.append(text)

    return {
        "product_id": product_id,
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "brand": BRAND,
        "source_domain": "coolmate.me",
        "name": name,
        "price": price,
        "original_price": None,
        "discount_percent": None,
        "currency": "VND",
        "categories": [],
        "gender": "male",
        "collection": None,
        "description_short": description_parts[0] if description_parts else "",
        "description_full": " | ".join(description_parts),
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

def extract_product_id(html: str) -> Optional[str]:
    """Tìm ID sản phẩm dạng 24 ký tự hex từ HTML."""
    match = re.search(r'data-product-id-new=["\']([a-f0-9]{24})["\']', html)
    if match:
        return match.group(1)
    match = re.search(r'data-product-id=["\']([a-f0-9]{24})["\']', html)
    if match:
        return match.group(1)
    match = re.search(r'"productId"\s*:\s*"([a-f0-9]{24})"', html)
    if match:
        return match.group(1)
    match = re.search(r'"id"\s*:\s*"([a-f0-9]{24})"', html)
    if match:
        return match.group(1)
    match = re.search(r'"_id"\s*:\s*"([a-f0-9]{24})"', html)
    if match:
        return match.group(1)
    return None


def parse_product_from_api_data(api_data: dict, source_url: str) -> dict:
    """
    Map dữ liệu sản phẩm từ Coolmate API proxy response sang schema chuẩn của dự án.
    """
    prod = api_data
    title = prod.get("title") or ""
    price = _extract_price(prod.get("price"))
    original_price = _extract_price(prod.get("compare_price") or prod.get("price"))
    discount = None
    if price and original_price and original_price > price:
        discount = round((1 - price / original_price) * 100)
        
    # Mô tả
    desc_html = prod.get("body_html") or ""
    desc_clean = re.sub(r"<[^>]+>", " ", desc_html).strip()
    desc_clean = re.sub(r"\s+", " ", desc_clean)
    
    # Images
    images = []
    prod_images = prod.get("images") or []
    for idx, img in enumerate(prod_images):
        src = img.get("src") or ""
        if src:
            if not src.startswith("http"):
                src = "https://mcdn.coolmate.me" + src
            images.append({
                "url": src,
                "alt": title,
                "type": "main" if idx == 0 else "gallery",
                "color": None
            })
            
    # Lấy danh sách màu sắc và size
    colors_set = set()
    sizes_set = set()
    
    options = prod.get("options") or []
    for opt in options:
        opt_id = opt.get("option_id")
        if opt_id == "color":
            colors_set.update(opt.get("values") or [])
        elif opt_id == "size":
            sizes_set.update(opt.get("values") or [])
            
    # Map hình ảnh theo màu sắc từ options_value
    options_value = prod.get("options_value") or []
    for opt_val in options_value:
        if isinstance(opt_val, dict) and opt_val.get("options_id") == "color":
            color_opts = opt_val.get("options") or []
            for co in color_opts:
                color_name = co.get("title")
                color_images = co.get("image") or []
                for c_img in color_images:
                    c_src = c_img.get("src") or ""
                    if c_src:
                        if not c_src.startswith("http"):
                            c_src = "https://mcdn.coolmate.me" + c_src
                        for img in images:
                            if img["url"].endswith(c_src) or c_src in img["url"]:
                                img["color"] = color_name

    # Variants detail
    variants = []
    api_variants = prod.get("variants") or []
    for v in api_variants:
        color = v.get("option1") or None
        size = v.get("option2") or None
        variants.append({
            "variant_id": f"{_make_product_id(source_url)}_{color}_{size}",
            "color": color,
            "color_hex": None,
            "size": size,
            "in_stock": v.get("available") or v.get("quantity", 0) > 0 or True,
            "quantity": v.get("quantity") or None,
            "price": _extract_price(v.get("regular_price")),
            "sku": v.get("sku") or None
        })
        
    # Features & attributes
    features = prod.get("features") or []
    attrs = {
        "material": None,
        "material_weight": None,
        "fit_type": None,
        "neckline": None,
        "sleeve_length": None,
        "bottom_length": None,
        "pattern": None,
        "technology": [],
        "raw": {}
    }
    
    for ft in features:
        if "Chất liệu" in ft or "Thành phần" in ft:
            attrs["material"] = ft.replace("Thành phần Vải chính:", "").replace("Thành phần vải phối:", "").strip()
            
    # Phân tích danh mục từ URL
    categories = []
    path = urlparse(source_url).path.strip("/")
    segments = path.split("/")
    if len(segments) > 0:
        categories = [segments[0]]
        
    rating = prod.get("review", {}).get("avg") or None
    review_count = prod.get("review", {}).get("count") or None

    return {
        "product_id": _make_product_id(source_url),
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "brand": BRAND,
        "source_domain": "coolmate.me",

        "name": title,
        "price": price,
        "original_price": original_price,
        "discount_percent": discount,
        "currency": "VND",

        "categories": categories,
        "gender": prod.get("gender_type") or "male",
        "collection": prod.get("note_collections") or None,

        "description_short": desc_clean[:200],
        "description_full": desc_clean,
        "care_instructions": [],
        "tags": prod.get("tags") or [],
        "style_tags": [],
        "season": ["all_season"],

        "attributes": attrs,

        "variants": variants,
        "colors": sorted(list(colors_set)),
        "sizes": sorted(list(sizes_set)),

        "images": images,

        "rating": float(rating) if rating else None,
        "review_count": int(review_count) if review_count else None,

        "related_products": prod.get("related_products") or [],
        "outfit_suggestions": [],
        "_parse_method": "hidden_api",
    }


async def scrape_product(page: Page, url: str) -> Optional[dict]:
    """
    Scrape đầy đủ thông tin 1 sản phẩm Coolmate.
    Returns dict sản phẩm hoặc None nếu thất bại.
    """
    ok = await navigate_and_wait(page, url)
    if not ok:
        return None

    # Chờ nhẹ để Next.js render
    await page.wait_for_timeout(1000)

    html = await get_page_html(page)

    # ── Phương pháp 1: Trích xuất productId và gọi API Proxy (Next.js) ──────
    product_id = extract_product_id(html)
    if product_id:
        try:
            api_url = f"https://www.coolmate.me/api/proxy/products?ids={product_id}&limit=6&visibility=true"
            response_js = await page.evaluate(f"""
                async () => {{
                    const res = await fetch('{api_url}');
                    return res.json();
                }}
            """)
            if response_js and "data" in response_js and len(response_js["data"]) > 0:
                product = parse_product_from_api_data(response_js["data"][0], url)
                return product
        except Exception as e:
            print(f"[Coolmate] LỖI fetch/parse Hidden API cho {url}: {e}")

    # ── Phương pháp 2: JSON-LD (Next.js SEO Data) ─────────────────────────
    json_ld_list = parse_json_ld(html)
    json_ld_product = extract_product_from_json_ld(json_ld_list)
    if json_ld_product and json_ld_product.get("name"):
        try:
            product = parse_product_from_json_ld_data(json_ld_product, url)
            return product
        except Exception as e:
            print(f"[Coolmate] LỖI parse JSON-LD: {e}")

    # ── Phương pháp 3: Parse __NUXT_DATA__ (Dự phòng cho Nuxt cũ nếu có) ───
    nuxt_data = parse_nuxt_data(html)
    if nuxt_data:
        product = parse_product_from_nuxt(nuxt_data, url)
        if product and product.get("name"):
            product["_parse_method"] = "nuxt_data"
            return product

    # ── Phương pháp 4: Fallback AX Tree ───────────────────────────────────
    print(f"[Coolmate] Không có API/JSON-LD/NUXT_DATA cho {url}, dùng AX Tree fallback...")
    try:
        ax_raw = await get_full_ax_tree(page)
        ax_filtered = filter_ignored(ax_raw)
        texts = extract_static_texts(ax_filtered)
        product = parse_product_from_ax_texts(texts, url)
        if product.get("name"):
            return product
    except Exception as e:
        print(f"[Coolmate] LỖI AX Tree: {e}")

    return None
