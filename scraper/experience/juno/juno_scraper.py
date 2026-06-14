"""
Juno.vn Full Product Scraper
================================
Platform: Next.js (React Server Components) + OneLife.vn SaaS Backend
API Base: https://onelife-api.juno.vn/v1
Products Endpoint: GET /products/categories/{slug}/products?page={n}&limit={limit}&order=NEWEST&direction=DESC
Filters Endpoint: GET /products/categories/{slug}/filters

Categories scraped:
  - Giày: giay-xang-dan, giay-cao-got, giay-bup-be, giay-sneakers, dep-guoc
  - Túi: tui-co-nho, tui-co-trung, tui-co-lon, balo, vi-clutch
  - Phụ Kiện: mat-kinh, non, moc-khoa, phu-kien-toc, vo, tui-my-pham
  - Quần Áo: dam-jumpsuit, ao, quan, vay, khoac

Output: harvest/juno/output/juno_products_full.json
"""

import os
import sys
import json
import time
import ssl
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional

sys.stdout.reconfigure(encoding='utf-8')

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "juno_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_BASE = "https://onelife-api.juno.vn/v1"
SITE_BASE = "https://juno.vn"
VENDOR = "Juno"
PAGE_LIMIT = 40   # products per page (max tested: 40)
DELAY = 0.4       # seconds between requests

# Global fallback for Juno's universal clothing size IDs (when not found in category filters)
GLOBAL_SIZE_FALLBACK = {
    "171": "XL",
    "172": "L",
    "173": "S",
    "174": "M",
    "175": "XXL",
}

# Category tree to scrape (slug → display name, parent_name)
CATEGORIES_TO_SCRAPE = [
    # Giày (shoes)
    {"slug": "giay-xang-dan",   "name": "Giày xăng đan",   "parent": "Giày"},
    {"slug": "giay-cao-got",    "name": "Giày cao gót",     "parent": "Giày"},
    {"slug": "giay-bup-be",     "name": "Giày búp bê",      "parent": "Giày"},
    {"slug": "giay-sneakers",   "name": "Giày Sneakers",    "parent": "Giày"},
    {"slug": "dep-guoc",        "name": "Dép guốc",         "parent": "Giày"},
    # Túi (bags)
    {"slug": "tui-co-nho",      "name": "Túi cỡ nhỏ",      "parent": "Túi"},
    {"slug": "tui-co-trung",    "name": "Túi cỡ trung",    "parent": "Túi"},
    {"slug": "tui-co-lon",      "name": "Túi cỡ lớn",      "parent": "Túi"},
    {"slug": "balo",            "name": "Balo",              "parent": "Túi"},
    {"slug": "vi-clutch",       "name": "Ví - Clutch",      "parent": "Túi"},
    # Phụ Kiện (accessories)
    {"slug": "mat-kinh",        "name": "Mắt kính",         "parent": "Phụ Kiện"},
    {"slug": "non",             "name": "Nón",               "parent": "Phụ Kiện"},
    {"slug": "moc-khoa",        "name": "Móc Khóa",         "parent": "Phụ Kiện"},
    {"slug": "phu-kien-toc",    "name": "Phụ kiện tóc",     "parent": "Phụ Kiện"},
    {"slug": "vo",              "name": "Vớ",                "parent": "Phụ Kiện"},
    # Quần Áo (clothing)
    {"slug": "dam-jumpsuit",    "name": "Đầm & Jumpsuit",   "parent": "Quần Áo"},
    {"slug": "ao",              "name": "Áo",                "parent": "Quần Áo"},
    {"slug": "quan",            "name": "Quần",              "parent": "Quần Áo"},
    {"slug": "vay",             "name": "Váy",               "parent": "Quần Áo"},
    {"slug": "khoac",           "name": "Khoác",             "parent": "Quần Áo"},
]

# HTTP headers mirroring the browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://juno.vn/",
    "Origin": "https://juno.vn",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


# ──────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────
def fetch_json(url: str, retries: int = 4) -> Optional[Any]:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            wait = 2 ** attempt
            print(f"    [!] Attempt {attempt+1}/{retries} failed for {url}: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    print(f"    [✗] All retries exhausted for: {url}")
    return None


# ──────────────────────────────────────────────
# Fetch attribute (size/color) ID→name maps
# ──────────────────────────────────────────────
def fetch_attribute_maps(cat_slug: str) -> Dict[str, Dict[str, str]]:
    """
    Returns a dict of attribute maps for the given category:
      {
        'variant_sizes': {'172': 'L', '174': 'M', ...},
        'variant_colors': {'61': 'Đen', '66': 'Nâu', ...},
        'juno_shoe_height': {'id': 'value', ...}
      }
    """
    url = f"{API_BASE}/products/categories/{cat_slug}/filters"
    data = fetch_json(url)
    if not data:
        return {}

    maps: Dict[str, Dict[str, str]] = {}
    for attr in data.get("attributes", []):
        code = attr.get("code", "")
        options = attr.get("options", [])
        maps[code] = {str(opt["id"]): opt["value"] for opt in options if "id" in opt and "value" in opt}
    return maps


# ──────────────────────────────────────────────
# Fetch all products from a category (paginated)
# ──────────────────────────────────────────────
def fetch_all_category_products(cat_slug: str, cat_name: str) -> List[Dict]:
    all_products = []
    page = 1
    while True:
        url = (f"{API_BASE}/products/categories/{cat_slug}/products"
               f"?page={page}&limit={PAGE_LIMIT}&order=NEWEST&direction=DESC")
        data = fetch_json(url)
        if not data:
            break

        pagination = data.get("pagination", {})
        products = data.get("products", [])
        total = pagination.get("total", 0)
        last_page = pagination.get("last_page", 1)

        print(f"    Page {page}/{last_page} — {len(products)} products (total: {total})")
        all_products.extend(products)

        if page >= last_page or not products:
            break
        page += 1
        time.sleep(DELAY)

    return all_products


# ──────────────────────────────────────────────
# Parse product images (filter out color swatches)
# ──────────────────────────────────────────────
def parse_images(raw_images: List[str]) -> List[str]:
    """Filter out tiny color-swatch images (onelife.vn CDN proxy thumbnails)."""
    result = []
    for img in raw_images:
        if img and "img.onelife.vn/rs:fit:60:60" in img:
            continue  # skip 60x60 color swatches
        if img and img.startswith("http"):
            result.append(img)
    return result


# ──────────────────────────────────────────────
# Extract color name from variant media
# ──────────────────────────────────────────────
def get_variant_color(variant: Dict) -> str:
    media = variant.get("media", [])
    for m in media:
        if m.get("itemType") == "primary" and m.get("title"):
            return m["title"]
    # fallback: first media item with a title
    for m in media:
        if m.get("title"):
            return m["title"]
    return ""


# ──────────────────────────────────────────────
# Extract size name from variant attributes
# ──────────────────────────────────────────────
def get_variant_size(variant: Dict, size_map: Dict[str, str]) -> str:
    """
    Variant-level attributes contain: ol_juno_barcode, ol_juno_variant_position, etc.
    The actual size text can be found in media title or barcode suffix.
    For shoes, size is in a specific attribute code.
    """
    # Try to find size in variant attributes
    for attr in variant.get("attributes", []):
        code = attr.get("code", "")
        # Check juno-specific shoe height / size codes
        if "size" in code.lower() or "height" in code.lower():
            val = str(attr.get("value", ""))
            return size_map.get(val, val)
    return ""


# ──────────────────────────────────────────────
# Parse a single variant
# ──────────────────────────────────────────────
def parse_variant(variant: Dict, product_name: str, size_map: Dict[str, str], color_map: Dict[str, str]) -> Dict:
    vid = variant.get("id", "")
    sku = variant.get("sku", "")
    
    # Extract barcode from attributes
    barcode = ""
    for attr in variant.get("attributes", []):
        if attr.get("code", "") == "ol_juno_barcode":
            barcode = str(attr.get("value", ""))
            break
    
    color = get_variant_color(variant)
    size = get_variant_size(variant, size_map)
    
    # Build a human-readable title
    if color and size:
        v_title = f"{color} / {size}"
    elif color:
        v_title = color
    elif size:
        v_title = size
    else:
        v_title = product_name

    # Images for this variant (filter out swatches)
    v_images = parse_images(variant.get("images", []))
    v_thumbnail = variant.get("thumbnail", "")
    
    # Prices
    orig_price = variant.get("originalPrice", 0)
    disc_price = variant.get("discountPrice", 0) or variant.get("price", 0)
    if disc_price == 0:
        disc_price = orig_price
    compare_at = orig_price if orig_price > disc_price else None
    disc_pct = variant.get("discountPercent", 0)
    
    # Stock
    stock_item = variant.get("stockItem", {})
    qty = stock_item.get("quantity", 0) if stock_item else 0
    in_stock = qty > 0
    
    # Promotion info
    promo = variant.get("promotionInfo", {})
    promo_name = promo.get("name", "") if promo else ""
    promo_end = promo.get("endDate", "") if promo else ""
    
    return {
        "id": vid,
        "sku": sku,
        "barcode": barcode,
        "title": v_title,
        "option1": color or None,
        "option2": size or None,
        "price": disc_price,
        "compare_at_price": compare_at,
        "discount_percent": disc_pct,
        "available": in_stock,
        "inventory_quantity": qty,
        "thumbnail": v_thumbnail,
        "images": v_images,
        "slug": variant.get("slug", ""),
        "promotion": {"name": promo_name, "end_date": promo_end} if promo_name else None,
    }


# ──────────────────────────────────────────────
# Parse full product
# ──────────────────────────────────────────────
def parse_product(raw: Dict, cat_info: Dict, attr_maps: Dict) -> Dict:
    size_map = attr_maps.get("variant_sizes", {})
    color_map = attr_maps.get("variant_colors", {})
    shoe_height_map = attr_maps.get("juno_shoe_height", {})

    pid = raw.get("id", "")
    name = raw.get("name", "")
    slug = raw.get("slug", "")
    
    # Extract available sizes/colors from product-level attributes
    available_sizes = []
    available_colors = []
    item_type = ""
    is_new = False
    
    for attr in raw.get("attributes", []):
        code = attr.get("code", "")
        val_raw = attr.get("value", "")
        
        if code == "variant_sizes":
            try:
                ids = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
                available_sizes = [size_map.get(str(i), GLOBAL_SIZE_FALLBACK.get(str(i), str(i))) for i in ids]
            except Exception:
                pass
        elif code == "variant_colors":
            try:
                ids = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
                available_colors = [color_map.get(str(i), str(i)) for i in ids]
            except Exception:
                pass
        elif code == "juno_item_type":
            item_type = str(val_raw)
        elif code == "is_new":
            is_new = str(val_raw).lower() == "true"
        elif code == "juno_shoe_height":
            try:
                ids = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
                heights = [shoe_height_map.get(str(i), str(i)) for i in (ids if isinstance(ids, list) else [ids])]
                if heights:
                    available_sizes = heights  # shoe height used as "size"
            except Exception:
                pass
    
    # Prices at product level
    orig_price = raw.get("originalPrice", 0)
    disc_price = raw.get("discountPrice", 0)
    if disc_price == 0:
        disc_price = orig_price
    compare_at = orig_price if orig_price > disc_price else None
    disc_pct = raw.get("discountPercent", 0)

    # Images
    all_images = parse_images(raw.get("images", []))
    thumbnail = raw.get("thumbnail", "")
    if thumbnail and thumbnail not in all_images:
        all_images.insert(0, thumbnail)
    featured_image = all_images[0] if all_images else ""

    # Description (usually empty for Juno)
    description = raw.get("description", "").strip()
    desc_json = raw.get("descriptionJson", {}) or {}
    if not description:
        parts = []
        for key in ["highlights", "introduction", "ingredients", "usages", "uses", "producer"]:
            val = str(desc_json.get(key, "")).strip()
            if val:
                parts.append(val)
        description = "\n\n".join(parts)
    
    # Parse all variants
    variants = []
    variant_prices = []
    total_stock = 0
    
    for v_raw in raw.get("variants", []):
        v = parse_variant(v_raw, name, shoe_height_map if cat_info["parent"] == "Giày" else size_map, color_map)
        variants.append(v)
        if v["price"]:
            variant_prices.append(v["price"])
        total_stock += v.get("inventory_quantity", 0)

    price_min = min(variant_prices) if variant_prices else disc_price
    price_max = max(variant_prices) if variant_prices else disc_price
    total_in_stock = raw.get("inStock", 0)

    # Build tags from available colors and promotion
    tags = []
    if available_colors:
        tags.extend(available_colors)
    if is_new:
        tags.append("Hàng mới")
    if raw.get("discountPercent", 0) > 0:
        tags.append("Sale")

    # Product URL
    product_url = f"{SITE_BASE}/products/{slug}"
    
    return {
        "id": pid,
        "handle": slug,
        "title": name,
        "vendor": VENDOR,
        "type": cat_info["name"],
        "parent_category": cat_info["parent"],
        "category_slug": cat_info["slug"],
        "item_type": item_type,
        "is_new": is_new,
        "description": description,
        "available": total_in_stock > 0 or any(v["available"] for v in variants),
        "in_stock_count": total_in_stock,
        "url": product_url,
        "price": disc_price,
        "price_min": price_min,
        "price_max": price_max,
        "compare_at_price": compare_at,
        "discount_percent": disc_pct,
        "images": all_images,
        "featured_image": featured_image,
        "thumbnail": thumbnail,
        "options": {
            "colors": available_colors,
            "sizes": available_sizes,
        },
        "tags": tags,
        "specifications": {
            "Kích thước có sẵn": ", ".join(available_sizes) if available_sizes else "",
            "Màu sắc có sẵn": ", ".join(available_colors) if available_colors else "",
        },
        "variants": variants,
        "_scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  JUNO.VN — FULL PRODUCT SCRAPER")
    print("  API: https://onelife-api.juno.vn/v1")
    print("=" * 65)
    
    all_products: List[Dict] = []
    seen_ids: set = set()
    
    for cat_info in CATEGORIES_TO_SCRAPE:
        slug = cat_info["slug"]
        name = cat_info["name"]
        parent = cat_info["parent"]
        
        print(f"\n[{parent} / {name}] Fetching category: {slug}")
        
        # 1. Fetch attribute maps (size/color ID → name)
        attr_maps = fetch_attribute_maps(slug)
        sizes_count = len(attr_maps.get("variant_sizes", {}))
        colors_count = len(attr_maps.get("variant_colors", {}))
        print(f"  Attribute maps: {sizes_count} sizes, {colors_count} colors")
        
        # 2. Fetch all products
        raw_products = fetch_all_category_products(slug, name)
        print(f"  Found {len(raw_products)} raw products")
        
        # 3. Parse and deduplicate
        new_count = 0
        dup_count = 0
        for raw in raw_products:
            pid = raw.get("id")
            if not pid:
                continue
            if pid in seen_ids:
                dup_count += 1
                continue
            
            try:
                product = parse_product(raw, cat_info, attr_maps)
                all_products.append(product)
                seen_ids.add(pid)
                new_count += 1
            except Exception as e:
                print(f"    [!] Error parsing product {raw.get('name', 'N/A')}: {e}")
        
        print(f"  Added: {new_count} new | Duplicates skipped: {dup_count}")
        
        # Incremental save
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)
        
        time.sleep(DELAY)
    
    # Final save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    
    # Summary
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    
    print("\n" + "=" * 65)
    print("  ✅ JUNO SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(all_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)
    
    # Category breakdown
    print("\n  Product count by category:")
    cat_counts: Dict[str, int] = {}
    for p in all_products:
        key = f"{p['parent_category']} / {p['type']}"
        cat_counts[key] = cat_counts.get(key, 0) + 1
    for k, v in sorted(cat_counts.items()):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
