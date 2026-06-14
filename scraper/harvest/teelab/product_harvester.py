import os
import json
import sys
import re
import urllib.request
import ssl
import time
from datetime import datetime
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/teelab/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "teelab_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://teelab.vn"
VENDOR = "Teelab"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*"
}

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # Get text and clean whitespace
    text = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', text)
    return clean.strip()

def extract_specifications(body_html, title, first_variant_sku):
    specs = {
        "Mã sản phẩm": "",
        "Chất liệu": "",
        "Form dáng": "",
        "Họa tiết": "",
        "Màu sắc": "",
        "Xuất xứ": "Việt Nam"
    }
    
    # 1. Resolve product code (Mã sản phẩm)
    base_sku = ""
    if first_variant_sku:
        base_sku = first_variant_sku.split("-")[0].split("_")[0].strip()
    if not base_sku:
        # Fallback to last word in title
        words = title.split()
        if words:
            last_word = words[-1]
            if re.search(r'[a-zA-Z0-9]+', last_word):
                base_sku = last_word
    specs["Mã sản phẩm"] = base_sku
    
    if not body_html:
        return specs
        
    soup = BeautifulSoup(body_html, "html.parser")
    text = soup.get_text()
    
    # Heuristics specs parsing based on Teelab description pattern
    mat_match = re.search(r'(?:Chất liệu|Chất liệu|Chất liệu):\s*([^\n\r<]+)', text, re.IGNORECASE)
    if mat_match:
        specs["Chất liệu"] = mat_match.group(1).strip().strip('.')
        
    form_match = re.search(r'(?:Form|Phom|Dáng|Dáng form|Kiểu dáng):\s*([^\n\r<]+)', text, re.IGNORECASE)
    if form_match:
        specs["Form dáng"] = form_match.group(1).strip().strip('.')
        
    color_match = re.search(r'(?:Màu sắc|Màu|Color):\s*([^\n\r<]+)', text, re.IGNORECASE)
    if color_match:
        specs["Màu sắc"] = color_match.group(1).strip().strip('.')
        
    tech_match = re.search(r'(?:Kỹ thuật|Kỹ thuật|Kỹ thuật):\s*([^\n\r<]+)', text, re.IGNORECASE)
    if tech_match:
        specs["Họa tiết"] = tech_match.group(1).strip().strip('.')
        
    return specs

def parse_product(p, category):
    title = p.get("name", "")
    alias = p.get("alias", "")
    body_html = p.get("content", "")
    vendor = p.get("vendor", VENDOR)
    product_type = p.get("product_type", "")
    p_id = str(p.get("id"))
    
    # URL
    product_url = f"{SITE_BASE}/{alias}"
    
    # Clean description
    description = clean_html(body_html)
    
    # Images - Keep absolute URLs
    images = []
    raw_images = p.get("images", [])
    for img in raw_images:
        # Sometimes images is a list of strings, sometimes list of dicts
        src = img.get("src") if isinstance(img, dict) else img
        if src:
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
            
    featured_image = images[0] if images else ""
    
    # Fetch first variant to help extract SKU
    raw_variants = p.get("variants", [])
    first_var_sku = raw_variants[0].get("sku", "") if raw_variants else ""
    
    # Specs
    specifications = extract_specifications(body_html, title, first_var_sku)
    
    # If color or size was not found in description, fallback to variant values
    
    # Options mapping
    raw_options = p.get("options", [])
    color_index = -1
    size_index = -1
    
    colors = []
    sizes = []
    
    for idx, opt in enumerate(raw_options):
        name_l = opt.get("name", "").lower()
        if "màu" in name_l or "color" in name_l:
            color_index = idx
        elif "kích" in name_l or "size" in name_l:
            size_index = idx
            
    # Variants mapping
    variants = []
    prices = []
    compare_prices = []
    
    for v in raw_variants:
        v_id = str(v.get("id"))
        sku = v.get("sku") or ""
        v_title = v.get("title", "")
        
        price_val = float(v.get("price") or 0)
        comp_val = float(v.get("compare_at_price") or 0)
        
        prices.append(price_val)
        if comp_val and comp_val > price_val:
            compare_prices.append(comp_val)
            
        available = v.get("available", True)
        qty = v.get("inventory_quantity", 0)
        
        # Resolve options based on index
        opts = v.get("options", [])
        if not opts:
            # Fallback
            opts = [v.get("option1"), v.get("option2"), v.get("option3")]
            
        color_val = opts[color_index] if (color_index != -1 and color_index < len(opts)) else None
        size_val = opts[size_index] if (size_index != -1 and size_index < len(opts)) else None
        
        # If no index, fallback to parsing title or options array
        if not color_val and len(opts) > 0:
            color_val = opts[0]
        if not size_val and len(opts) > 1:
            size_val = opts[1]
            
        if color_val and color_val not in colors:
            colors.append(color_val)
        if size_val and size_val not in sizes:
            sizes.append(size_val)
            
        # Map variant image
        v_img = ""
        featured_image_dict = v.get("featured_image")
        if isinstance(featured_image_dict, dict):
            v_img = featured_image_dict.get("src", "")
            if v_img.startswith("//"):
                v_img = "https:" + v_img
        if not v_img:
            v_img = featured_image
            
        variants.append({
            "id": v_id,
            "sku": sku,
            "title": f"{title} - {color_val} - Size {size_val}" if (color_val and size_val) else v_title,
            "option1": color_val,
            "option2": size_val,
            "price": price_val,
            "compare_at_price": comp_val if comp_val > 0 else None,
            "available": available,
            "inventory_quantity": qty,
            "featured_image": v_img,
            "specifications": specifications
        })
        
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0
    compare_at_price = max(compare_prices) if compare_prices else None
    
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    # Standardize specifications: fallback color/size values if empty
    if not specifications.get("Màu sắc") and colors:
        specifications["Màu sắc"] = ", ".join(colors)
    if not specifications.get("Chất liệu"):
        # Default fallback check in title/tags
        specifications["Chất liệu"] = "Cotton" # Default local brand shirt style
        
    # Tags
    tags = p.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
        
    parent_cat = "Nam"
    if "nữ" in category.lower():
        parent_cat = "Nữ"
    elif "phụ kiện" in category.lower() or "balo" in category.lower():
        parent_cat = "Unisex"
        
    return {
        "id": p_id,
        "handle": alias,
        "title": title,
        "vendor": vendor,
        "type": category,
        "parent_category": parent_cat,
        "description": description,
        "description_html": body_html,
        "available": any(v["available"] for v in variants),
        "url": product_url,
        "_scraped_category": category,
        "_scraped_url": product_url,
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
        "tags": tags,
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def fetch_products_page(page, limit=250):
    url = f"{SITE_BASE}/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8')).get("products", [])
                elif resp.status == 429:
                    wait_t = 2 ** attempt + 1
                    print(f"  [!] HTTP 429 Rate Limited. Waiting {wait_t}s...")
                    time.sleep(wait_t)
                else:
                    time.sleep(2)
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 TEELAB PRODUCT HARVESTER STARTING")
    print("=" * 60)
    
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Discovery input file not found at: {DISCOVERY_INPUT_FILE}")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        
    url_to_category = {}
    for category, urls in discovery_map.items():
        for url in urls:
            url_to_category[url] = category
            
    total_discovered = len(url_to_category)
    print(f"[*] Discovered product URLs to harvest: {total_discovered}")
    
    # Load existing harvested products if available
    harvested_products = []
    seen_ids = set()
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
            for p in harvested_products:
                seen_ids.add(p["id"])
            print(f"[*] Loaded existing output file with {len(harvested_products)} products.")
        except Exception as e:
            print(f"[!] Error loading existing output: {e}. Starting fresh.")
            
    page = 1
    limit = 250
    harvest_count = 0
    
    while True:
        products = fetch_products_page(page, limit)
        if not products:
            break
            
        print(f"[*] Page {page}: Processing {len(products)} products...")
        
        for p in products:
            alias = p.get("alias", "")
            if not alias:
                continue
                
            p_url = f"{SITE_BASE}/{alias}"
            
            # Only harvest if it was discovered (meaning it passed the filters)
            if p_url in url_to_category:
                p_id = str(p.get("id"))
                if p_id in seen_ids:
                    continue
                    
                category = url_to_category[p_url]
                parsed = parse_product(p, category)
                harvested_products.append(parsed)
                seen_ids.add(p_id)
                harvest_count += 1
                
        print(f"  - Page {page}: Total parsed in this batch. Cumulative harvested: {len(harvested_products)}")
        
        # Save batch incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
        if len(products) < limit:
            break
            
        page += 1
        time.sleep(0.5)
        
    print("\n" + "="*60)
    print("🏆 TEELAB HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*60)

if __name__ == "__main__":
    main()
