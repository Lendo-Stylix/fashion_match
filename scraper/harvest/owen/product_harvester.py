"""
Owen.vn Product Harvester
=========================
Platform: Magento 2 (GraphQL API)
Endpoint: https://owen.vn/graphql

This script harvests detailed product info, variants, pricing, stock,
and parsed specifications from Owen.vn.

Output: harvest/owen/output/owen_products_full.json
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
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/owen/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "owen_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://owen.vn"
API_ENDPOINT = f"{SITE_BASE}/graphql"
PAGE_SIZE = 50
DELAY = 0.5
VENDOR = "Owen"

CATEGORIES = [
    # Áo (Parent Nam)
    {"id": "59", "name": "Áo Polo", "parent": "Nam"},
    {"id": "60", "name": "Áo Sơ Mi", "parent": "Nam"},
    {"id": "56", "name": "Áo T-Shirt", "parent": "Nam"},
    {"id": "58", "name": "Áo Veston", "parent": "Nam"},
    {"id": "62", "name": "Áo Jacket", "parent": "Nam"},
    {"id": "57", "name": "Áo Len", "parent": "Nam"},
    {"id": "2472", "name": "Bộ đồ", "parent": "Nam"},
    {"id": "2743", "name": "Áo Blazer", "parent": "Nam"},
    {"id": "3471", "name": "Áo Nỉ", "parent": "Nam"},
    
    # Quần (Parent Nam)
    {"id": "54", "name": "Quần Tây", "parent": "Nam"},
    {"id": "52", "name": "Quần Short", "parent": "Nam"},
    {"id": "55", "name": "Quần Khaki", "parent": "Nam"},
    {"id": "53", "name": "Quần Jeans", "parent": "Nam"},
    {"id": "101", "name": "Quần Jogger", "parent": "Nam"},
    {"id": "3470", "name": "Quần Nỉ", "parent": "Nam"},
    
    # Phụ Kiện (Parent Phụ Kiện)
    {"id": "100", "name": "Tất", "parent": "Phụ Kiện"},
    {"id": "64", "name": "Dây Lưng", "parent": "Phụ Kiện"},
    {"id": "65", "name": "Ví Da", "parent": "Phụ Kiện"},
    {"id": "66", "name": "Cà Vạt", "parent": "Phụ Kiện"}
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json"
}

def infer_sku(title: str, sku_from_api: str) -> str:
    if sku_from_api and sku_from_api.strip():
        return sku_from_api.strip()
        
    # Search for standard SKU pattern in title: uppercase letters followed by numbers
    # Matches strings like TA232520, BELT256249, QJS241265, AJ260149N
    words = re.findall(r'\b[A-Za-z]+[0-9]+[A-Za-z0-9_-]*\b', title)
    if words:
        for w in words:
            base = w.split("-")[0].split("_")[0].strip()
            if len(base) >= 4:
                return base
                
    # Fallback to first alphanumeric word if no match
    for w in title.split():
        clean = re.sub(r'[^A-Za-z0-9]', '', w)
        if len(clean) >= 4 and any(c.isdigit() for c in clean) and any(c.isalpha() for c in clean):
            return clean
            
    return sku_from_api or "OWEN_" + str(int(time.time() * 1000))

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', text)
    return clean.strip()

def extract_specifications(body_html, sku):
    specs = {
        "Mã sản phẩm": sku,
        "Chất liệu": "",
        "Form dáng": "",
        "Màu sắc": "",
        "Xuất xứ": "Việt Nam"
    }
    if not body_html:
        return specs
        
    soup = BeautifulSoup(body_html, "html.parser")
    text = soup.get_text()
    
    # Material
    mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^\n\r<]+)', text, re.IGNORECASE)
    if mat_match:
        specs["Chất liệu"] = mat_match.group(1).strip().strip('.')
    else:
        # Fallback: look for percentage patterns like "87% Polyester 13% Rayon"
        pct_matches = re.findall(r'\d+%\s*[A-Za-z]+', text)
        if pct_matches:
            specs["Chất liệu"] = ", ".join(pct_matches)
            
    # Form/Fit
    form_match = re.search(r'(?:Form|Phom|Dáng|Dáng form|Kiểu dáng):\s*([^\n\r<,]+)', text, re.IGNORECASE)
    if form_match:
        specs["Form dáng"] = form_match.group(1).strip().strip('.')
    else:
        # Look for known fits in text
        for fit in ["Regular Fit", "Slim Fit", "Classic Fit", "Smart Fit", "J-form", "Regular", "Slimfit"]:
            if fit.lower() in text.lower():
                specs["Form dáng"] = fit
                break
                
    return specs

def query_graphql(query_str: str, variables: dict) -> dict:
    payload = json.dumps({"query": query_str, "variables": variables}).encode('utf-8')
    req = urllib.request.Request(API_ENDPOINT, data=payload, headers=HEADERS, method='POST')
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
                elif resp.status == 429:
                    wait_t = 2 ** attempt + 1
                    time.sleep(wait_t)
                else:
                    time.sleep(2)
        except Exception as e:
            time.sleep(2 * (attempt + 1))
    return {}

PRODUCTS_DETAIL_QUERY = """
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      id
      name
      sku
      url_key
      description {
        html
      }
      price_range {
        minimum_price {
          regular_price {
            value
          }
          final_price {
            value
          }
        }
        maximum_price {
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
      media_gallery {
        url
        disabled
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
            stock_status
            price_range {
              minimum_price {
                final_price {
                  value
                }
                regular_price {
                  value
                }
              }
            }
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

def parse_product(item: dict, category_name: str, parent_cat: str) -> dict:
    p_id = str(item.get("id"))
    name = item.get("name", "")
    sku_api = item.get("sku", "")
    sku = infer_sku(name, sku_api)
    url_key = item.get("url_key", "")
    
    body_html = item.get("description", {}).get("html", "") if item.get("description") else ""
    description = clean_html(body_html)
    
    price_range = item.get("price_range", {})
    min_price_info = price_range.get("minimum_price", {})
    max_price_info = price_range.get("maximum_price", {})
    
    price_min = float(min_price_info.get("final_price", {}).get("value", 0))
    price_max = float(max_price_info.get("final_price", {}).get("value", 0))
    
    # Regular price check
    compare_at_price = float(min_price_info.get("regular_price", {}).get("value", 0))
    if compare_at_price <= price_min:
        compare_at_price = None
        
    discount_percent = 0
    if compare_at_price and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    # Images (Filter placeholders)
    images = []
    media_gallery = item.get("media_gallery") or []
    for img in media_gallery:
        url = img.get("url")
        disabled = img.get("disabled", False)
        if url and not disabled and "placeholder" not in url:
            images.append(url)
            
    # Fallback to main image
    main_img = item.get("image", {}).get("url")
    if main_img and "placeholder" not in main_img and main_img not in images:
        images.insert(0, main_img)
        
    featured_image = main_img if (main_img and "placeholder" not in main_img) else (images[0] if images else "")
    
    # Specifications
    specifications = extract_specifications(body_html, sku)
    
    # Options & Variants
    variants = []
    colors = []
    sizes = []
    
    raw_variants = item.get("variants") or []
    configurable_options = item.get("configurable_options") or []
    
    # Retrieve all possible colors and sizes from options metadata
    for opt in configurable_options:
        code = opt.get("attribute_code", "")
        vals = [v.get("label") for v in opt.get("values", [])]
        if code == "color":
            colors = vals
        elif code == "size":
            sizes = vals
            
    # Map variants
    for v in raw_variants:
        v_prod = v.get("product") or {}
        v_id = str(v_prod.get("id"))
        v_sku = v_prod.get("sku") or ""
        v_name = v_prod.get("name", "")
        
        v_price = float(v_prod.get("price_range", {}).get("minimum_price", {}).get("final_price", {}).get("value", price_min))
        v_compare = float(v_prod.get("price_range", {}).get("minimum_price", {}).get("regular_price", {}).get("value", 0))
        if v_compare <= v_price:
            v_compare = None
            
        stock = v_prod.get("stock_status", "IN_STOCK")
        available = stock == "IN_STOCK"
        qty = 10 if available else 0
        
        # Get variant image
        v_img = v_prod.get("image", {}).get("url")
        if not v_img or "placeholder" in v_img:
            v_img = featured_image
            
        # Match option values from attributes
        opt1 = None  # Color
        opt2 = None  # Size
        
        v_attrs = v.get("attributes") or []
        for attr in v_attrs:
            code = attr.get("code")
            label = attr.get("label")
            if code == "color":
                opt1 = label
            elif code == "size":
                opt2 = label
                
        if not v_sku:
            v_sku = f"{sku}-{opt1 or 'DEFAULT'}-{opt2 or 'DEFAULT'}"
            
        variants.append({
            "id": v_id,
            "sku": v_sku,
            "title": f"{name} - {opt1} - Size {opt2}" if (opt1 and opt2) else v_name,
            "option1": opt1,
            "option2": opt2,
            "price": v_price,
            "compare_at_price": v_compare,
            "available": available,
            "inventory_quantity": qty,
            "featured_image": v_img,
            "specifications": specifications
        })
        
    # If it is a simple product with no configurable variants, create default variant
    if not variants:
        # Check if color can be inferred from title
        color_fallback = None
        if colors:
            color_fallback = colors[0]
        else:
            # Try parsing color from name if common
            for col in ["Đen", "Trắng", "Xám", "Navy", "Xanh", "Đỏ", "Be", "Kem", "Nâu"]:
                if col.lower() in name.lower():
                    color_fallback = col
                    break
        
        variants.append({
            "id": p_id,
            "sku": sku,
            "title": name,
            "option1": color_fallback,
            "option2": "FREESIZE",
            "price": price_min,
            "compare_at_price": compare_at_price,
            "available": True,
            "inventory_quantity": 10,
            "featured_image": featured_image,
            "specifications": specifications
        })
        
        if color_fallback and color_fallback not in colors:
            colors = [color_fallback]
        if "FREESIZE" not in sizes:
            sizes = ["FREESIZE"]
        
    if colors:
        specifications["Màu sắc"] = ", ".join(colors)
        
    return {
        "id": p_id,
        "handle": url_key,
        "title": name,
        "vendor": VENDOR,
        "type": category_name,
        "parent_category": parent_cat,
        "description": description,
        "description_html": body_html,
        "available": any(v["available"] for v in variants) if variants else False,
        "url": f"{SITE_BASE}/{url_key}.html",
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
        "specifications": specifications,
        "tags": [VENDOR, category_name, parent_cat],
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def main():
    print("=" * 60)
    print("🏆 OWEN PRODUCT HARVESTER STARTING")
    print("=" * 60)
    
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Discovery output file not found at: {DISCOVERY_INPUT_FILE}")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        
    # Build maps
    discovered_urls = set()
    url_to_category = {}
    for cat_name, urls in discovery_map.items():
        for url in urls:
            discovered_urls.add(url)
            url_to_category[url] = cat_name
            
    print(f"[*] Total discovered URLs: {len(discovered_urls)}")
    
    harvested_products = []
    seen_ids = set()
    
    # Load existing for resume
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
            for p in harvested_products:
                seen_ids.add(p["id"])
            print(f"[*] Loaded {len(harvested_products)} existing harvested products.")
        except Exception as e:
            print(f"[!] Error loading existing output: {e}. Starting fresh.")
            
    for cat in CATEGORIES:
        cat_id = cat["id"]
        cat_name = cat["name"]
        parent_cat = cat["parent"]
        print(f"\n[*] Harvesting products from category {cat_name} (ID: {cat_id})...")
        
        page = 1
        cat_harvested = 0
        
        while True:
            variables = {
                "catId": cat_id,
                "pageSize": PAGE_SIZE,
                "page": page
            }
            
            data = query_graphql(PRODUCTS_DETAIL_QUERY, variables)
            if not data or "data" not in data:
                print(f"  [!] Failed to get page {page}")
                break
                
            products_data = data.get("data", {}).get("products", {})
            items = products_data.get("items") or []
            if not items:
                break
                
            print(f"  Page {page} — fetched {len(items)} products details")
            
            page_added = 0
            for item in items:
                p_id = str(item.get("id"))
                url_key = item.get("url_key", "")
                p_url = f"{SITE_BASE}/{url_key}.html"
                
                # Check if it was in the clean discovered URLs list
                if p_url in url_to_category:
                    if p_id in seen_ids:
                        continue
                        
                    parsed = parse_product(item, cat_name, parent_cat)
                    harvested_products.append(parsed)
                    seen_ids.add(p_id)
                    page_added += 1
                    cat_harvested += 1
                    
            print(f"  → Parsed {page_added} new products from page {page}")
            
            total_count = products_data.get("total_count", 0)
            if page * PAGE_SIZE >= total_count:
                break
                
            page += 1
            time.sleep(DELAY)
            
        print(f"[*] Completed category {cat_name}: {cat_harvested} products harvested.")
        
        # Save batch incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "=" * 60)
    print("🏆 OWEN HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Total variants parsed          : {total_variants}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
