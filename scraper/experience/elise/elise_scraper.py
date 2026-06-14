"""
Elise.vn Full Product Harvester
================================
Platform: Magento 2 + GraphQL API
API Endpoint: POST https://elise.vn/graphql

Output: harvest/elise/output/elise_products_full.json
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
from typing import Dict, List, Optional

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "elise_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_ENDPOINT = "https://elise.vn/graphql"
VENDOR = "Elise"
PAGE_SIZE = 20
DELAY = 0.5

# Category tree to crawl: (id, parent_category, type_name)
CATEGORIES = [
    # Thời Trang Nữ (ID 3)
    {"id": "40", "parent": "Nữ", "type": "Áo"},
    {"id": "41", "parent": "Nữ", "type": "Đầm"},
    {"id": "42", "parent": "Nữ", "type": "Chân Váy"},
    {"id": "43", "parent": "Nữ", "type": "Quần"},
    
    # Elise Urban (ID 164)
    {"id": "165", "parent": "Nữ", "type": "Đầm"},
    {"id": "166", "parent": "Nữ", "type": "Áo"},
    {"id": "167", "parent": "Nữ", "type": "Chân Váy"},
    {"id": "168", "parent": "Nữ", "type": "Quần"},
    
    # Phụ Kiện (ID 102)
    {"id": "127", "parent": "Phụ Kiện", "type": "Túi"},
    {"id": "160", "parent": "Phụ Kiện", "type": "Trang Sức"},
    
    # Outlet / Sale (ID 142)
    {"id": "143", "parent": "Nữ", "type": "Đầm (Sale)"},
    {"id": "144", "parent": "Nữ", "type": "Chân Váy (Sale)"},
    {"id": "145", "parent": "Nữ", "type": "Áo (Sale)"},
    {"id": "147", "parent": "Nữ", "type": "Quần (Sale)"},
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

def query_graphql(query_str: str, variables: Dict) -> Optional[Dict]:
    payload = json.dumps({"query": query_str, "variables": variables}).encode('utf-8')
    req = urllib.request.Request(API_ENDPOINT, data=payload, headers=HEADERS, method='POST')
    
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"    [!] GraphQL query failed (attempt {attempt+1}): {e}")
            time.sleep(2)
    return None

PRODUCTS_QUERY = """
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      id
      name
      sku
      url_key
      price_range {
        minimum_price {
          regular_price {
            value
          }
          final_price {
            value
          }
        }
      }
      image {
        url
      }
      small_image {
        url
      }
      media_gallery {
        url
      }
      ... on ConfigurableProduct {
        configurable_options {
          attribute_code
          label
          values {
            value_index
            label
          }
        }
        variants {
          product {
            id
            sku
            name
            image {
              url
            }
          }
          attributes {
            label
            code
            value_index
          }
        }
      }
    }
  }
}
"""

def parse_product(item: Dict, parent_category: str, type_name: str) -> Dict:
    p_id = str(item.get("id"))
    name = item.get("name", "")
    sku = item.get("sku", "")
    url_key = item.get("url_key", "")
    
    price_range = item.get("price_range", {})
    min_price = price_range.get("minimum_price", {})
    
    price = min_price.get("final_price", {}).get("value", 0)
    compare_price = min_price.get("regular_price", {}).get("value", None)
    
    discount_percent = 0
    if compare_price and price and compare_price > price:
        discount_percent = int(round((compare_price - price) / compare_price * 100))
        
    # Images
    images = []
    gallery = item.get("media_gallery") or []
    for g in gallery:
        url = g.get("url")
        if url:
            images.append(url)
            
    # Fallback to main image
    main_img = item.get("image", {}).get("url") or item.get("small_image", {}).get("url")
    if main_img and main_img not in images:
        images.insert(0, main_img)
        
    featured_image = main_img if main_img else (images[0] if images else None)
    
    # Options & Variants
    variants = []
    colors_list = []
    sizes_list = []
    
    raw_variants = item.get("variants") or []
    config_opts = item.get("configurable_options") or []
    
    # Extract available colors/sizes
    for opt in config_opts:
        code = opt.get("attribute_code", "")
        vals = [v.get("label") for v in opt.get("values", [])]
        if code == "color" or "màu" in opt.get("label", "").lower():
            colors_list = vals
        elif code == "size" or "kích" in opt.get("label", "").lower():
            sizes_list = vals
            
    # Extract color from name if color config is missing (common in Magento)
    if not colors_list:
        # try simple color detection from name
        color_match = re.search(r'\b(ĐEN|TRẮNG|ĐỎ|VÀNG|XANH|HỒNG|XÁM|KEM|NÂU|TÍM|BẠC|VÀNG KEM|HỌA TIẾT)\b', name.upper())
        if color_match:
            colors_list = [color_match.group(1).title()]

    for v in raw_variants:
        v_prod = v.get("product") or {}
        v_id = str(v_prod.get("id", ""))
        v_sku = v_prod.get("sku", "")
        v_name = v_prod.get("name", "")
        
        v_img = v_prod.get("image", {}).get("url")
        v_imgs = [v_img] if v_img and "placeholder" not in v_img else []
        
        opt1 = None  # color
        opt2 = None  # size
        
        v_attrs = v.get("attributes") or []
        for attr in v_attrs:
            code = attr.get("code")
            label = attr.get("label")
            if code == "color":
                opt1 = label
            elif code == "size":
                opt2 = label
                
        # Fallback options
        if not opt1 and colors_list:
            opt1 = colors_list[0]
            
        variants.append({
            "id": v_id or f"{p_id}_{v_sku}",
            "sku": v_sku,
            "title": v_name,
            "option1": opt1,
            "option2": opt2,
            "price": price,
            "compare_at_price": compare_price,
            "available": True,
            "inventory_quantity": 10,  # default placeholder stock
            "images": v_imgs
        })
        
    return {
        "id": p_id,
        "handle": url_key or sku.lower(),
        "title": name,
        "vendor": VENDOR,
        "type": type_name,
        "parent_category": parent_category,
        "description": "",
        "available": True,
        "url": f"https://elise.vn/{url_key}.html" if url_key else f"https://elise.vn/{sku.lower()}.html",
        "price": price,
        "price_min": price,
        "price_max": price,
        "compare_at_price": compare_price,
        "discount_percent": discount_percent,
        "images": images,
        "featured_image": featured_image,
        "options": {
            "colors": colors_list,
            "sizes": sizes_list
        },
        "specifications": {},
        "tags": [],
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def main():
    print("="*65)
    print("  ELISE.VN — FULL PRODUCT SCRAPER (Magento GraphQL)")
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
        cat_id = cat["id"]
        parent = cat["parent"]
        t_name = cat["type"]
        print(f"\nFetching category ID {cat_id} ({parent} / {t_name})...")
        
        page = 1
        while True:
            variables = {
                "catId": cat_id,
                "pageSize": PAGE_SIZE,
                "page": page
            }
            resp = query_graphql(PRODUCTS_QUERY, variables)
            if not resp or "data" not in resp:
                print(f"  [!] Failed to get page {page}")
                break
                
            products_data = resp.get("data", {}).get("products", {})
            items = products_data.get("items") or []
            if not items:
                break
                
            print(f"  Page {page} — fetched {len(items)} products")
            
            new_count = 0
            for item in items:
                p_id = str(item.get("id"))
                if p_id in seen_ids:
                    continue
                
                parsed = parse_product(item, parent, t_name)
                all_products.append(parsed)
                seen_ids.add(p_id)
                new_count += 1
                
            print(f"  → Added {new_count} new products")
            
            total_count = products_data.get("total_count", 0)
            if page * PAGE_SIZE >= total_count:
                break
                
            page += 1
            time.sleep(DELAY)
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    print("\n" + "=" * 65)
    print("  ✅ ELISE SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(all_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)

if __name__ == "__main__":
    main()
