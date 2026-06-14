"""
Aristino.com Full Product Scraper
==================================
Platform: Shopify
API: https://aristino.com/collections/{collection-slug}/products.json?limit=250&page={n}

Collections to scrape (no kids/underwear/shoes):
  - all (Tất cả sản phẩm)
  - Alternatively specific collections like: ao-so-mi-nam, ao-thun-nam, ao-polo-nam, ao-khoac-nam, quan-tay-nam, etc.

Output: harvest/aristino/output/aristino_products_full.json
"""

import os
import sys
import json
import time
import ssl
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Optional, Set

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "aristino_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://aristino.com"
VENDOR = "Aristino"
PAGE_SIZE = 250
DELAY = 0.7

COLLECTIONS = [
    {"slug": "all", "name": "Tất Cả", "parent": "Nam"}
]

EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker",
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh", "kids"
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}

def is_excluded(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in EXCLUDE_KEYWORDS)

def fetch_collection_products(collection_slug: str, page: int) -> Optional[List[Dict]]:
    url = f"{SITE_BASE}/collections/{collection_slug}/products.json?limit={PAGE_SIZE}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("products", [])
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return None
            print(f"    [!] Attempt {attempt+1} failed with code {he.code}. Retrying...")
            time.sleep(2)
        except Exception as e:
            print(f"    [!] Attempt {attempt+1} failed: {e}. Retrying...")
            time.sleep(2)
    return None

def parse_product(raw: Dict, parent_category: str) -> Dict:
    title = raw.get("title", "")
    handle = raw.get("handle", "")
    product_type = raw.get("product_type", "")
    
    # Base prices
    prices = []
    compare_prices = []
    
    variants = []
    raw_variants = raw.get("variants", [])
    
    # Options mapping
    options_meta = raw.get("options", [])
    color_index = -1
    size_index = -1
    for idx, opt in enumerate(options_meta):
        name_lower = opt.get("name", "").lower()
        if "màu" in name_lower or "color" in name_lower:
            color_index = idx
        elif "size" in name_lower or "kích" in name_lower:
            size_index = idx
            
    for v in raw_variants:
        v_id = str(v.get("id"))
        sku = v.get("sku") or ""
        v_title = v.get("title", "")
        price_val = float(v.get("price") or 0)
        comp_val = float(v.get("compare_at_price") or 0)
        available = v.get("available", True)
        
        prices.append(price_val)
        if comp_val:
            compare_prices.append(comp_val)
            
        opt1 = v.get("option1")
        opt2 = v.get("option2")
        opt3 = v.get("option3")
        
        color_val = None
        size_val = None
        
        opts = [opt1, opt2, opt3]
        if color_index != -1 and color_index < len(opts):
            color_val = opts[color_index]
        if size_index != -1 and size_index < len(opts):
            size_val = opts[size_index]
            
        variants.append({
            "id": v_id,
            "sku": sku,
            "title": v_title,
            "option1": color_val or opt1,
            "option2": size_val or opt2,
            "price": price_val,
            "compare_at_price": comp_val or None,
            "available": available,
            "inventory_quantity": v.get("inventory_quantity", 0),
            "images": []
        })
        
    price_min = min(prices) if prices else 0
    price_max = max(prices) if prices else 0
    compare_at_price = max(compare_prices) if compare_prices else None
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    images = [img.get("src") for img in raw.get("images", []) if img.get("src")]
    featured_image = images[0] if images else None
    
    # Extract options values
    colors = []
    sizes = []
    for opt in options_meta:
        name_lower = opt.get("name", "").lower()
        vals = opt.get("values", [])
        if "màu" in name_lower or "color" in name_lower:
            colors = vals
        elif "size" in name_lower or "kích" in name_lower:
            sizes = vals
            
    # Specifications (extract from body_html if possible, or leave basic)
    specs = {}
    body_html = raw.get("body_html", "")
    if body_html:
        # basic cleanup for material
        mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^<]+)', body_html, re.IGNORECASE)
        if mat_match:
            specs["Chất liệu"] = mat_match.group(1).strip()
            
    product_url = f"{SITE_BASE}/products/{handle}"
    
    return {
        "id": str(raw.get("id")),
        "handle": handle,
        "title": title,
        "vendor": VENDOR,
        "type": product_type,
        "parent_category": parent_category,
        "description": re.sub('<[^<]+?>', '', body_html).strip() if body_html else "",
        "available": any(v["available"] for v in variants),
        "url": product_url,
        "price": price_min,
        "price_min": price_min,
        "price_max": price_max,
        "compare_at_price": compare_at_price,
        "discount_percent": discount_percent,
        "images": images,
        "featured_image": featured_image,
        "options": {
            "colors": colors,
            "sizes": sizes
        },
        "specifications": specs,
        "tags": raw.get("tags", []),
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def main():
    print("="*65)
    print("  ARISTINO.COM — FULL PRODUCT SCRAPER (Shopify API)")
    print("="*65)
    
    # Load existing if exists to merge/update
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
            
    for coll in COLLECTIONS:
        slug = coll["slug"]
        name = coll["name"]
        parent = coll["parent"]
        print(f"\n[{name}] Fetching collection: {slug}...")
        
        page = 1
        while True:
            products = fetch_collection_products(slug, page)
            if not products:
                break
                
            print(f"  Page {page} — fetched {len(products)} products")
            
            new_count = 0
            for raw in products:
                p_id = str(raw.get("id"))
                if p_id in seen_ids:
                    continue
                if is_excluded(raw.get("title", "")) or is_excluded(raw.get("product_type", "")):
                    continue
                    
                parsed = parse_product(raw, parent)
                all_products.append(parsed)
                seen_ids.add(p_id)
                new_count += 1
                
            print(f"  → Added {new_count} new products")
            
            if len(products) < PAGE_SIZE:
                break
            page += 1
            time.sleep(DELAY)
            
    # Save output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    print("\n" + "=" * 65)
    print("  ✅ ARISTINO SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(all_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)

if __name__ == "__main__":
    main()