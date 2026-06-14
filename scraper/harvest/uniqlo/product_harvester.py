import os
import json
import sys
import re
import urllib.request
import ssl
import time
import html
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/uniqlo/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "uniqlo_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://www.uniqlo.com/vn/vi"
API_BASE = "https://www.uniqlo.com/vn/api/commerce/v5/vi"
VENDOR = "Uniqlo"
CONCURRENCY = 4 # safe limit to avoid IP ban
DELAY_BETWEEN_BATCHES = 0.2

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "x-fr-clientid": "uq.vn.web-spa",
    "x-fr-client-version": "3.2506.1"
}

def clean_html(raw_html):
    if not raw_html:
        return ""
    clean = re.sub(r'<[^>]*>', ' ', raw_html)
    clean = re.sub(r'\s+', ' ', clean)
    return html.unescape(clean.strip())

def extract_design_detail(design_html):
    specs = {"Form dáng": "", "Chi tiết thiết kế": ""}
    if not design_html:
        return specs
        
    parts = re.split(r'<br\s*/?>|\n', design_html)
    details = []
    for part in parts:
        part = part.strip("- ").strip()
        if not part:
            continue
        if ":" in part:
            name, val = part.split(":", 1)
            name = name.strip()
            val = val.strip()
            if name.lower() in ["dáng", "phom", "form"]:
                specs["Form dáng"] = val
            else:
                details.append(f"{name}: {val}")
        else:
            details.append(part)
            
    if details:
        specs["Chi tiết thiết kế"] = "; ".join(details)
    return specs

def fetch_product_details(product_id):
    url = f"{API_BASE}/products/{product_id}?httpFailure=true"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("result")
        except Exception as e:
            # Simple cooling off before retry
            time.sleep(1 + attempt)
    return None

def parse_product(res, category):
    name = res.get("name", "")
    p_id = res.get("productId", "")
    
    item_code = p_id
    code_match = re.search(r'\d{6}', p_id)
    if code_match:
        item_code = code_match.group(0)
        
    url = f"{SITE_BASE}/products/{p_id}"
    
    long_desc = res.get("longDescription", "")
    short_desc = res.get("shortDescription", "")
    
    desc_html = long_desc or short_desc
    description = clean_html(desc_html)
    
    composition = clean_html(res.get("composition", ""))
    washing = clean_html(res.get("washingInformation", ""))
    design_html = res.get("designDetail", "")
    design_specs = extract_design_detail(design_html)
    
    origins = res.get("countriesOfOrigin", [])
    origin = origins[0] if origins else "Việt Nam"
    
    specifications = {
        "Chất liệu": composition,
        "Form dáng": design_specs["Form dáng"],
        "Chi tiết thiết kế": design_specs["Chi tiết thiết kế"],
        "Lưu ý giặt ủi": washing,
        "Xuất xứ": origin,
        "Mã sản phẩm": item_code
    }
    
    images_dict = res.get("images", {})
    main_imgs = images_dict.get("main", {})
    sub_imgs = images_dict.get("sub", [])
    
    images = []
    for c_code, c_img_obj in main_imgs.items():
        img_url = c_img_obj.get("image")
        if img_url and img_url not in images:
            images.append(img_url)
            
    for s_img_obj in sub_imgs:
        img_url = s_img_obj.get("image")
        if img_url and img_url not in images:
            images.append(img_url)
            
    featured_image = images[0] if images else ""
    
    colors_list = res.get("colors", [])
    sizes_list = res.get("sizes", [])
    
    colors = [f"{c.get('displayCode')} {c.get('name')}" for c in colors_list]
    sizes = [s.get("name") for s in sizes_list]
    
    variants = []
    prices = []
    compare_prices = []
    
    l2s = res.get("l2s", [])
    for entry in l2s:
        v_id = entry.get("communicationCode") or entry.get("l2Id") or ""
        sku = entry.get("communicationCode") or ""
        
        color_obj = entry.get("color", {})
        size_obj = entry.get("size", {})
        
        color_val = f"{color_obj.get('displayCode')} {color_obj.get('name')}" if color_obj else None
        size_val = size_obj.get("name") if size_obj else None
        
        v_title = f"{color_val} / {size_val}" if color_val and size_val else (color_val or size_val or "")
        
        v_prices = entry.get("prices", {})
        base_price = float(v_prices.get("base", {}).get("value") or 0.0)
        promo_price_obj = v_prices.get("promo")
        
        if promo_price_obj and promo_price_obj.get("value"):
            price_val = float(promo_price_obj.get("value"))
            comp_val = base_price
        else:
            price_val = base_price
            comp_val = None
            
        prices.append(price_val)
        if comp_val and comp_val > price_val:
            compare_prices.append(comp_val)
            
        available = entry.get("sales", True)
        
        c_code = color_obj.get("displayCode") if color_obj else ""
        v_img = ""
        if c_code and c_code in main_imgs:
            v_img = main_imgs[c_code].get("image") or ""
        if not v_img:
            v_img = featured_image
            
        variants.append({
            "id": str(v_id),
            "sku": sku,
            "title": v_title,
            "option1": color_val,
            "option2": size_val,
            "price": price_val,
            "compare_at_price": comp_val,
            "available": available,
            "inventory_quantity": 1 if available else 0,
            "featured_image": v_img,
            "specifications": specifications
        })
        
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0
    compare_at_price = max(compare_prices) if compare_prices else None
    
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    raw_tags = res.get("tags", [])
    tags = [t.get("name") for t in raw_tags if t.get("name")]
    
    gender_name = res.get("genderName", "Nam")
    parent_category = "Nam"
    if "women" in gender_name.lower() or "nữ" in gender_name.lower():
        parent_category = "Nữ"
        
    return {
        "id": p_id,
        "handle": p_id,
        "title": name,
        "vendor": VENDOR,
        "type": res.get("productType") or "",
        "parent_category": parent_category,
        "description": description,
        "description_html": desc_html,
        "available": any(v["available"] for v in variants),
        "url": url,
        "_scraped_category": category,
        "_scraped_url": url,
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

def main():
    print("=" * 60)
    print("🏆 UNIQLO CONCURRENT PRODUCT HARVESTER STARTING")
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
    
    # Load existing harvested products if available for resume capability
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
            
    # Filter out already harvested URLs
    pending_tasks = []
    for p_url, category in url_to_category.items():
        p_id = p_url.split("/")[-1]
        if p_id not in seen_ids:
            pending_tasks.append((p_id, category, p_url))
            
    print(f"[*] Remaining products to harvest: {len(pending_tasks)}")
    if not pending_tasks:
        print("[*] All products have already been harvested.")
        return
        
    harvest_count = 0
    
    # Function to fetch and parse a single product
    def process_item(item):
        p_id, category, p_url = item
        res = fetch_product_details(p_id)
        if not res:
            return None
        try:
            parsed = parse_product(res, category)
            return parsed
        except Exception as e:
            print(f"  [!] Error parsing {p_id}: {e}")
            return None

    # Execute using ThreadPoolExecutor
    print(f"[*] Launching ThreadPoolExecutor with {CONCURRENCY} workers...")
    
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        # Submit all tasks
        future_to_item = {executor.submit(process_item, item): item for item in pending_tasks}
        
        for future in as_completed(future_to_item):
            p_id, category, p_url = future_to_item[future]
            parsed = future.result()
            
            if parsed:
                harvested_products.append(parsed)
                seen_ids.add(parsed["id"])
                harvest_count += 1
                
                print(f"[{len(harvested_products)}/{total_discovered}] Harvested: {parsed['id']} ({parsed['_scraped_category']})")
                
                # Save incrementally every 10 products
                if harvest_count % 10 == 0:
                    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            else:
                print(f"  [!] Failed to harvest {p_id}")
                
            time.sleep(DELAY_BETWEEN_BATCHES)
            
    # Save final batch
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "="*50)
    print("🏆 UNIQLO CONCURRENT HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Total variants harvested       : {total_variants}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
