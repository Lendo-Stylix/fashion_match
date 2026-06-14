"""
Coolmate.me Full Product Scraper
==================================
Platform: Next.js 14+ App Router (RSC)
Strategy: Fetch collection pages directly (HTML), unescape self.__next_f pushes
          to extract the 'serverData.products' payload.

Output: harvest/coolmate/output/coolmate_products_full.json
"""

import os
import sys
import json
import time
import ssl
import re
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Optional, Set

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "coolmate_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://www.coolmate.me"
IMG_BASE = "https://media.coolmate.me"
VENDOR = "Coolmate"
DELAY = 0.6

CATEGORIES = [
    # Nam - Áo
    {"slug": "ao-thun-nam",          "name": "Áo Thun Nam",      "parent": "Nam"},
    {"slug": "ao-thun-nu",           "name": "Áo Thun Nữ",       "parent": "Nữ"},
    {"slug": "ao-polo-nam",          "name": "Áo Polo Nam",      "parent": "Nam"},
    {"slug": "ao-polo-nu",           "name": "Áo Polo Nữ",       "parent": "Nữ"},
    {"slug": "ao-so-mi-nam",         "name": "Áo Sơ Mi Nam",     "parent": "Nam"},
    {"slug": "ao-sweater-len-ni-nam","name": "Áo Sweater Nam",   "parent": "Nam"},
    {"slug": "ao-khoac-nam",         "name": "Áo Khoác Nam",     "parent": "Nam"},
    {"slug": "ao-khoac-nu",          "name": "Áo Khoác Nữ",      "parent": "Nữ"},
    {"slug": "ao-ba-lo-tank-top-nam","name": "Áo Tank Top Nam",  "parent": "Nam"},
    {"slug": "ao-nam-dai-tay",       "name": "Áo Dài Tay Nam",   "parent": "Nam"},
    {"slug": "ao-dai-tay-nu",        "name": "Áo Dài Tay Nữ",    "parent": "Nữ"},
    {"slug": "ao-cropped-top",       "name": "Áo Crop Top Nữ",   "parent": "Nữ"},
    {"slug": "ao-nu",                "name": "Áo Nữ",            "parent": "Nữ"},
    # Nam - Quần
    {"slug": "quan-short-nam",       "name": "Quần Short Nam",   "parent": "Nam"},
    {"slug": "quan-jogger-nam",      "name": "Quần Jogger Nam",  "parent": "Nam"},
    {"slug": "quan-dai-nam",         "name": "Quần Dài Nam",     "parent": "Nam"},
    {"slug": "quan-pants-nam",       "name": "Quần Pants Nam",   "parent": "Nam"},
    {"slug": "quan-jeans-nam",       "name": "Quần Jeans Nam",   "parent": "Nam"},
    {"slug": "quan-kaki-nam",        "name": "Quần Kaki Nam",    "parent": "Nam"},
    # Nữ - Quần & Váy
    {"slug": "quan-legging",         "name": "Quần Legging Nữ",  "parent": "Nữ"},
    {"slug": "quan-short-nu",        "name": "Quần Short Nữ",    "parent": "Nữ"},
    {"slug": "quan-dai-nu",          "name": "Quần Dài Nữ",      "parent": "Nữ"},
    {"slug": "vay-dam-nu",           "name": "Váy Đầm Nữ",       "parent": "Nữ"},
    # Đồ bơi
    {"slug": "do-boi-nam",           "name": "Đồ Bơi Nam",       "parent": "Nam"},
    {"slug": "do-boi-nam-nu",        "name": "Đồ Bơi",           "parent": "Chung"},
    # Tất/Vớ
    {"slug": "tat-coolmate",         "name": "Tất/Vớ",           "parent": "Phụ Kiện"},
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def fetch_collection_page(slug: str, page: int) -> Optional[str]:
    url = f"{SITE_BASE}/collection/{slug}?page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
                return r.read().decode('utf-8')
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return None
            print(f"    [!] Attempt {attempt+1} failed (HTTP {he.code}). Retrying...")
            time.sleep(2)
        except Exception as e:
            print(f"    [!] Attempt {attempt+1} failed: {e}. Retrying...")
            time.sleep(2)
    return None

def extract_products_from_html(html: str) -> List[Dict]:
    # Extract next_f push strings
    matches = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', html)
    if not matches:
        return []
        
    text = "\n".join(matches)
    # Unescape
    unescaped = text.replace('\\"', '"').replace('\\\\', '\\')
    
    # Locate serverData
    idx = unescaped.find('"serverData":')
    if idx == -1:
        return []
        
    start = unescaped.rfind('{', 0, idx)
    if start == -1:
        return []
        
    # Balance brackets
    count = 0
    json_str = ""
    for i in range(start, len(unescaped)):
        c = unescaped[i]
        if c == '{':
            count += 1
        elif c == '}':
            count -= 1
        json_str += c
        if count == 0:
            break
            
    try:
        data = json.loads(json_str)
        return data.get("serverData", {}).get("products", [])
    except Exception as e:
        print(f"    [!] JSON parsing error: {e}")
        return []

def format_image_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"{IMG_BASE}{url}"

def parse_product(item: Dict, parent_category: str) -> Dict:
    title = item.get("title", "")
    href = item.get("href", "")
    p_id = str(item.get("id", ""))
    
    price = item.get("regular_price") or 0
    compare_price = item.get("compare_price") or None
    sale_percent = item.get("sale_percent") or 0
    
    variants = []
    images = []
    colors_set = set()
    sizes_set = set()
    
    mapped_variants = item.get("mapped_variants") or {}
    for color, vars_list in mapped_variants.items():
        colors_set.add(color)
        for v in vars_list:
            v_id = str(v.get("id", ""))
            v_size = v.get("size", "")
            sizes_set.add(v_size)
            
            v_title = v.get("title", f"{color} / {v_size}")
            v_qty = v.get("quantity", 0)
            v_available = not v.get("isDisable", False)
            
            # Format variant images
            v_thumb = format_image_url(v.get("thumbnail"))
            v_hover = format_image_url(v.get("thumbnail_hover"))
            v_imgs = []
            if v_thumb:
                v_imgs.append(v_thumb)
                if v_thumb not in images:
                    images.append(v_thumb)
            if v_hover:
                v_imgs.append(v_hover)
                if v_hover not in images:
                    images.append(v_hover)
                    
            variants.append({
                "id": v_id,
                "sku": "",
                "title": v_title,
                "option1": color,
                "option2": v_size,
                "price": v.get("regular_price") or price,
                "compare_at_price": compare_price,
                "available": v_available,
                "inventory_quantity": v_qty,
                "images": v_imgs
            })
            
    # Fallback to general images if variants images empty
    if not images:
        thumbnail = format_image_url(item.get("thumbnail"))
        if thumbnail:
            images.append(thumbnail)
            
    featured_image = images[0] if images else None
    
    # Specs & description
    specs = {}
    note = item.get("note") or ""
    
    return {
        "id": p_id,
        "handle": href.replace("/product/", "").strip(),
        "title": title,
        "vendor": VENDOR,
        "type": parent_category,  # fallback type as parent category
        "parent_category": parent_category,
        "description": note,
        "available": item.get("active", True),
        "url": f"{SITE_BASE}{href}",
        "price": price,
        "price_min": price,
        "price_max": price,
        "compare_at_price": compare_price,
        "discount_percent": sale_percent,
        "images": images,
        "featured_image": featured_image,
        "options": {
            "colors": list(colors_set),
            "sizes": list(sizes_set)
        },
        "specifications": specs,
        "tags": [],
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def main():
    print("="*65)
    print("  COOLMATE.ME — FULL PRODUCT HARVESTER")
    print("="*65)
    
    all_products = []
    seen_ids = set()
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                all_products = json.load(f)
                seen_ids = {str(p["id"]) for p in all_products}
            print(f"Loaded {len(all_products)} existing products from output file.")
        except Exception:
            pass
            
    for cat in CATEGORIES:
        slug = cat["slug"]
        name = cat["name"]
        parent = cat["parent"]
        print(f"\n[{name}] Fetching collection: {slug}...")
        
        page = 1
        while True:
            html = fetch_collection_page(slug, page)
            if not html:
                break
                
            products = extract_products_from_html(html)
            if not products:
                print("  → No products found (end of pagination or parsing failed)")
                break
                
            print(f"  Page {page} — fetched {len(products)} products")
            
            new_count = 0
            for item in products:
                p_id = str(item.get("id"))
                if not p_id or p_id in seen_ids:
                    continue
                    
                parsed = parse_product(item, parent)
                all_products.append(parsed)
                seen_ids.add(p_id)
                new_count += 1
                
            print(f"  → Added {new_count} new products")
            page += 1
            time.sleep(DELAY)
            
    # Save output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    print("\n" + "=" * 65)
    print("  ✅ COOLMATE SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(all_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)

if __name__ == "__main__":
    main()