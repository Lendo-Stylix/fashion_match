import os
import json
import sys
import re
import urllib.request
import ssl
import time
import html
from datetime import datetime

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/yame/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "yame_products_full.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://yame.vn"
VENDOR = "YaMe.vn"

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

def extract_color_refined(title: str) -> str:
    parts = re.split(r'\s+Màu\s+', title, flags=re.IGNORECASE)
    if len(parts) < 2:
        return "N/A"
    
    color_text = parts[-1].strip()
    keywords = [
        r'\bdáng\b', r'\bphom\b', r'\bform\b', r'\bthe\b', 
        r'\bstyle\b', r'\bchất\b', r'\bvải\b', r'\bcó\b', 
        r'\bthể\b', r'\bthao\b', r'\bphối\b', r'\bthêu\b',
        r'\bin\b', r'\bchống\b'
    ]
    
    earliest_idx = len(color_text)
    for kw in keywords:
        m = re.search(kw, color_text, re.IGNORECASE)
        if m and m.start() < earliest_idx:
            earliest_idx = m.start()
            
    color_clean = color_text[:earliest_idx].strip()
    color_clean = color_clean.strip(',.-/()\"\' ').strip()
    return color_clean

def extract_specifications(body_html, title=""):
    specs = {
        "Chất liệu": "",
        "Form dáng": "",
        "Chi tiết": "",
        "Lưu ý giặt ủi": "",
        "Xuất xứ": "Việt Nam"
    }
    
    # Extract Form dáng from Title if possible
    form_match = re.search(r'\b(Dáng|Phom|Form)\s+([^-\(\)\"]+)', title, re.IGNORECASE)
    if form_match:
        specs["Form dáng"] = form_match.group(0).strip()
        
    if not body_html:
        return specs
        
    # Extract from list format
    li_matches = re.findall(r'<li>\s*<strong>([^:]+):</strong>\s*(.*?)\s*</li>', body_html, re.IGNORECASE | re.DOTALL)
    for name, val in li_matches:
        name_clean = re.sub(r'<[^>]*>', '', name).strip().lower()
        val_clean = re.sub(r'<[^>]*>', '', val).strip()
        val_clean = html.unescape(val_clean)
        
        if "chất liệu" in name_clean or "thành phần" in name_clean:
            specs["Chất liệu"] = val_clean
        elif "chi tiết" in name_clean:
            specs["Chi tiết"] = val_clean
        elif "giặt" in name_clean or "ủi" in name_clean or "bảo quản" in name_clean:
            specs["Lưu ý giặt ủi"] = val_clean
        elif "xuất xứ" in name_clean:
            specs["Xuất xứ"] = val_clean

    # Fallback to line-by-line scanning
    if not specs["Chất liệu"]:
        text_content = re.sub(r'<(?:br|p|div|li|span)[^>]*>', '\n', body_html)
        text_content = re.sub(r'<[^>]*>', '', text_content)
        text_content = html.unescape(text_content)
        
        for line in text_content.split('\n'):
            line_clean = line.strip()
            if not line_clean:
                continue
            mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*(.*)', line_clean, re.IGNORECASE)
            if mat_match:
                specs["Chất liệu"] = mat_match.group(1).strip()
                break
                
    return specs

def parse_product(p, category):
    title = p.get("title", "")
    handle = p.get("handle", "")
    body_html = p.get("body_html", "")
    vendor = p.get("vendor", "") or VENDOR
    product_type = p.get("product_type", "")
    p_id = str(p.get("id"))
    
    product_url = f"{SITE_BASE}/products/{handle}"
    description = clean_html(body_html)
    specifications = extract_specifications(body_html, title)
    
    # Extract color from title
    color_val = extract_color_refined(title)
    
    # Extract images (absolute URLs only)
    images = []
    raw_images = p.get("images", [])
    for img in raw_images:
        src = img.get("src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
            
    featured_image = images[0] if images else ""
    
    # Options & sizes lookup
    raw_options = p.get("options", [])
    size_index = -1
    sizes = []
    
    for idx, opt in enumerate(raw_options):
        name_l = opt.get("name", "").lower()
        vals = opt.get("values", [])
        if "kích" in name_l or "size" in name_l:
            size_index = idx
            sizes = vals
            break
            
    # If colors list needs to represent the current product color
    colors = [color_val] if color_val and color_val != "N/A" else []
    
    # Variants mapping
    variants = []
    prices = []
    compare_prices = []
    
    raw_variants = p.get("variants", [])
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
        
        # Resolve options
        opts = [v.get("option1"), v.get("option2"), v.get("option3")]
        size_val = opts[size_index] if (size_index != -1 and size_index < len(opts)) else v.get("option1")
        
        # Resolve variant image
        v_img = ""
        # 1. Check if variant has detailed featured_image dict
        feat_img_obj = v.get("featured_image")
        if isinstance(feat_img_obj, dict):
            v_img = feat_img_obj.get("src")
            if v_img and v_img.startswith("//"):
                v_img = "https:" + v_img
        
        # 2. Check by image_id lookup
        if not v_img:
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
            "option1": color_val if color_val != "N/A" else None,
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
        
    raw_tags = p.get("tags") or []
    if isinstance(raw_tags, list):
        tags = [t.strip() for t in raw_tags if t.strip()]
    else:
        tags = [t.strip() for t in str(raw_tags).split(",") if t.strip()]
        
    return {
        "id": p_id,
        "handle": handle,
        "title": title,
        "vendor": vendor,
        "type": product_type,
        "parent_category": "Nam",  # Yame is primarily a men's brand
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
                return json.loads(resp.read().decode('utf-8')).get("products", [])
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 YAME PRODUCT HARVESTER STARTING")
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
            
    page = 1
    limit = 250
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
            
            # Only harvest if it was discovered (passed filters)
            if p_url in url_to_category:
                p_id = str(p.get("id"))
                if p_id in seen_ids:
                    continue
                    
                category = url_to_category[p_url]
                parsed = parse_product(p, category)
                harvested_products.append(parsed)
                seen_ids.add(p_id)
                harvest_count += 1
                
        print(f"  - Page {page}: Cumulative harvested: {len(harvested_products)}")
        
        # Save batch incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
        if len(products) < limit:
            break
            
        page += 1
        time.sleep(0.5)
        
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "="*50)
    print("🏆 YAME HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Total variants harvested       : {total_variants}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
