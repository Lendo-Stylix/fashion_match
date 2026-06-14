import os
import json
import sys
import re
import urllib.request
import ssl
import time
from datetime import datetime
import html

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/dirtycoins/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "dirtycoins_products_full.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://dirtycoins.vn"

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
    # Remove HTML tags
    clean = re.sub(r'<[^>]*>', ' ', raw_html)
    # Replace multiple spaces with a single space
    clean = re.sub(r'\s+', ' ', clean)
    return html.unescape(clean.strip())

def extract_specifications(body_html):
    specs = {
        "Chất liệu": "",
        "Form dáng": "",
        "Hình in / Công nghệ": ""
    }
    if not body_html:
        return specs
        
    # Replace <br> and other line ending tags with \n to parse line-by-line
    text_content = re.sub(r'<(?:br|p|div|li)[^>]*>', '\n', body_html)
    text_content = re.sub(r'<[^>]*>', '', text_content)
    text_content = html.unescape(text_content)
    
    for line in text_content.split('\n'):
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Match Material
        mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^••\n\-]+)', line_clean, re.IGNORECASE)
        if mat_match:
            specs["Chất liệu"] = mat_match.group(1).strip().strip('.')
            continue
            
        # Match Form
        form_match = re.search(r'(?:Form|Dáng|Kiểu dáng):\s*([^••\n\-]+)', line_clean, re.IGNORECASE)
        if form_match:
            specs["Form dáng"] = form_match.group(1).strip().strip('.')
            continue
            
        # Match Print
        print_match = re.search(r'(?:Hình in|Công nghệ in|Artwork):\s*([^••\n\-]+)', line_clean, re.IGNORECASE)
        if print_match:
            specs["Hình in / Công nghệ"] = print_match.group(1).strip().strip('.')
            continue
            
    return specs

def parse_product(p, category):
    title = p.get("title", "")
    handle = p.get("handle", "")
    body_html = p.get("body_html", "")
    vendor = p.get("vendor", "")
    product_type = p.get("product_type", "")
    p_id = str(p.get("id"))
    
    # URL
    product_url = f"{SITE_BASE}/products/{handle}"
    
    # Description
    description = clean_html(body_html)
    
    # Specs
    specifications = extract_specifications(body_html)
    
    # Images - Keep absolute URLs
    images = []
    raw_images = p.get("images", [])
    for img in raw_images:
        src = img.get("src")
        if src:
            # Normalize schema relative URLs if any
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
            
    featured_image = images[0] if images else ""
    
    # Options lookup
    raw_options = p.get("options", [])
    color_index = -1
    size_index = -1
    
    colors = []
    sizes = []
    
    for idx, opt in enumerate(raw_options):
        name_l = opt.get("name", "").lower()
        vals = opt.get("values", [])
        if "màu" in name_l or "color" in name_l:
            color_index = idx
            colors = vals
        elif "kích" in name_l or "size" in name_l:
            size_index = idx
            sizes = vals
            
    # Variants mapping
    variants = []
    prices = []
    compare_prices = []
    
    raw_variants = p.get("variants", [])
    for v in raw_variants:
        v_id = str(v.get("id"))
        sku = v.get("sku") or ""
        v_title = v.get("title", "")
        
        # Price formatting
        price_val = float(v.get("price") or 0)
        comp_val = float(v.get("compare_at_price") or 0)
        
        prices.append(price_val)
        if comp_val and comp_val > price_val:
            compare_prices.append(comp_val)
            
        available = v.get("available", True)
        qty = v.get("inventory_quantity", 0)
        
        # Resolve options
        opts = [v.get("option1"), v.get("option2"), v.get("option3")]
        color_val = opts[color_index] if (color_index != -1 and color_index < len(opts)) else None
        size_val = opts[size_index] if (size_index != -1 and size_index < len(opts)) else None
        
        # Map variant image
        v_img = ""
        image_id = v.get("image_id")
        if image_id:
            for img in raw_images:
                if img.get("id") == image_id:
                    v_img = img.get("src")
                    if v_img and v_img.startswith("//"):
                        v_img = "https:" + v_img
                    break
        if not v_img:
            v_img = featured_image
            
        variants.append({
            "id": v_id,
            "sku": sku,
            "title": v_title,
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
        
    tags = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
    
    return {
        "id": p_id,
        "handle": handle,
        "title": title,
        "vendor": vendor,
        "type": product_type,
        "parent_category": "Nam" if "nam" in category.lower() else ("Nữ" if "nữ" in category.lower() else "Fashion"),
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

def fetch_products_page(page, limit=50):
    url = f"{SITE_BASE}/collections/all/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8')).get("products", [])
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 DIRTYCOINS PRODUCT HARVESTER STARTING")
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
    limit = 50
    harvest_count = 0
    
    while True:
        products = fetch_products_page(page, limit)
        if not products:
            break
            
        print(f"[*] Page {page}: Processing {len(products)} products...")
        
        for p in products:
            handle = p.get("handle", "")
            if not handle:
                continue
                
            p_url = f"{SITE_BASE}/products/{handle}"
            
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
        
    print("\n" + "="*50)
    print("🏆 DIRTYCOINS HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
