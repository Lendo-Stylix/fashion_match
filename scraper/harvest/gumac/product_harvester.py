"""
GUMAC.vn Full Product Scraper
==================================
Platform: React SPA with CMS REST API  
API Base: https://cms.gumac.vn/api/v1/products

Strategy: Scrape ALL products (no filter), filter excluded types locally.
Exclude: giày, dép (shoes), đồ lót (underwear), trẻ em, bé (kids).
Output: harvest/gumac/output/gumac_products_full.json
"""

import os
import sys
import json
import time
import ssl
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Optional

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "gumac_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_BASE = "https://cms.gumac.vn/api/v1"
IMG_BASE = "https://cms.gumac.vn"
SITE_BASE = "https://gumac.vn"
VENDOR = "GUMAC"
DELAY = 0.5
PAGE_SIZE = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Origin": "https://gumac.vn",
    "Referer": "https://gumac.vn/",
}

EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker",
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh",
    "mỹ phẩm", "son môi", "kem dưỡng",
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def is_excluded(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in EXCLUDE_KEYWORDS)

def fetch_api(url: str, retries: int = 4) -> Optional[Dict]:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [!] Failed to fetch {url}: {e}")
            time.sleep(2 ** attempt)
    return None

def parse_product(item: Dict) -> Dict:
    p_id = str(item.get("id"))
    name = item.get("name", "")
    code = item.get("code", "")
    slug = item.get("slug", "")
    desc = item.get("description", "")
    
    cat_info = item.get("category") or {}
    cat_name = cat_info.get("name", "")
    cat_slug = cat_info.get("slug", "")
    
    # Infer gender/parent category
    parent_cat = "Nữ"
    gender = "female"
    if "nam" in name.lower() or "nam" in cat_name.lower():
        parent_cat = "Nam"
        gender = "male"
    elif "kid" in cat_slug.lower() or "tre-em" in cat_slug.lower():
        parent_cat = "Trẻ em"
        gender = "unisex"

    # Images & Swatches
    colors_data = item.get("colors") or []
    sizes_data = item.get("sizes") or []
    
    images = []
    variants = []
    
    # Map colors and sizes for top-level options
    colors_list = []
    sizes_list = [s.get("name") for s in sizes_data if s.get("name")]
    
    for color in colors_data:
        c_code = color.get("code", "")
        c_name = color.get("name", "")
        colors_list.append(c_name)
        
        media = color.get("media") or {}
        gallery = media.get("gallery") or []
        
        # Color specific images
        color_imgs = []
        for g in gallery:
            path = g.get("path")
            if path:
                # Ensure absolute URL
                full_url = path if path.startswith("http") else f"{IMG_BASE}{path}"
                color_imgs.append(full_url)
                if full_url not in images:
                    images.append(full_url)
                    
        # If no gallery, check color swatch image
        if not color_imgs:
            swatch_path = media.get("color", {}).get("path")
            if swatch_path:
                full_url = swatch_path if swatch_path.startswith("http") else f"{IMG_BASE}{swatch_path}"
                color_imgs.append(full_url)
                if full_url not in images:
                    images.append(full_url)

        for size in sizes_data:
            s_name = size.get("name", "")
            variants.append({
                "id": f"{p_id}_{c_code}_{s_name}",
                "sku": "",
                "title": f"{c_name} / {s_name}",
                "option1": c_name,
                "option2": s_name,
                "price": 0,
                "compare_at_price": None,
                "available": True,
                "inventory_quantity": 0,
                "images": color_imgs
            })
            
    featured_image = images[0] if images else None
    
    return {
        "id": p_id,
        "handle": slug or code.lower(),
        "title": name,
        "vendor": VENDOR,
        "type": cat_name,
        "parent_category": parent_cat,
        "category_slug": cat_slug,
        "gender": gender,
        "description": desc,
        "available": True,
        "url": f"{SITE_BASE}/{slug or code.lower()}",
        "price": 0,
        "price_min": 0,
        "price_max": 0,
        "compare_at_price": None,
        "discount_percent": 0,
        "images": images,
        "featured_image": featured_image,
        "options": {
            "colors": colors_list,
            "sizes": sizes_list
        },
        "specifications": {},
        "tags": item.get("hashtags") or [],
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def main():
    print("="*65)
    print("  GUMAC.VN — FULL PRODUCT SCRAPER (All Products)")
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
            
    page = 1
    total_pages = 1
    
    while page <= total_pages:
        url = f"{API_BASE}/products?page={page}&limit={PAGE_SIZE}"
        print(f"Fetching page {page}/{total_pages}...")
        resp = fetch_api(url)
        if not resp or "data" not in resp:
            print(f"  [!] Failed to get page {page}")
            break
            
        meta = resp.get("meta") or {}
        total_pages = meta.get("totalPages", 1)
        
        items = resp.get("data") or []
        new_count = 0
        
        for item in items:
            p_id = str(item.get("id"))
            if p_id in seen_ids:
                continue
            if is_excluded(item.get("name", "")):
                continue
                
            parsed = parse_product(item)
            all_products.append(parsed)
            seen_ids.add(p_id)
            new_count += 1
            
        print(f"  → Added {new_count} new products")
        page += 1
        time.sleep(DELAY)
        
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    print("\n" + "=" * 65)
    print("  ✅ GUMAC SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(all_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)

if __name__ == "__main__":
    main()