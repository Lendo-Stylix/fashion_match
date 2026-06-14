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
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/levents/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "levents_products_full.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://levents.asia"
API_URL = f"{SITE_BASE}/view/products"
VENDOR = "Levents"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*"
}

def clean_html(raw_html):
    if not raw_html:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]*>', ' ', raw_html)
    # Replace multiple spaces with a single space
    clean = re.sub(r'\s+', ' ', clean)
    return html.unescape(clean.strip())

def extract_info_image(short_desc):
    for item in short_desc:
        desc_text = item.get("description") or ""
        match = re.search(r'src=["\']([^"\']+)["\']', desc_text)
        if match:
            return match.group(1)
    return ""

def extract_specifications(body_html, short_desc):
    specs = {
        "Chất liệu": "",
        "Form dáng": "",
        "Hình in / Công nghệ": ""
    }
    # Combine description text to search keywords
    combined_text = body_html or ""
    for item in short_desc:
        combined_text += "\n" + (item.get("description") or "")
        
    # Standardize HTML to text lines
    text_content = re.sub(r'<[^>]*>', '\n', combined_text)
    text_content = html.unescape(text_content)
    
    for line in text_content.split('\n'):
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Match Material
        mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^•\n\-]+)', line_clean, re.IGNORECASE)
        if mat_match:
            val = mat_match.group(1).strip().strip('.')
            if not specs["Chất liệu"]:
                specs["Chất liệu"] = val
                
        # Match Form
        form_match = re.search(r'(?:Form|Dáng|Kiểu dáng):\s*([^•\n\-]+)', line_clean, re.IGNORECASE)
        if form_match:
            val = form_match.group(1).strip().strip('.')
            if not specs["Form dáng"]:
                specs["Form dáng"] = val
                
        # Match Print
        print_match = re.search(r'(?:Hình in|Công nghệ in|Artwork|Chất liệu in):\s*([^•\n\-]+)', line_clean, re.IGNORECASE)
        if print_match:
            val = print_match.group(1).strip().strip('.')
            if not specs["Hình in / Công nghệ"]:
                specs["Hình in / Công nghệ"] = val
                
    return specs

def resolve_options(fields):
    color_val = None
    size_val = None
    for f in fields:
        name_l = f.get("name", "").lower()
        val = f.get("value")
        if "màu" in name_l or "color" in name_l:
            color_val = val
        elif "size" in name_l or "kích" in name_l:
            size_val = val
    return color_val, size_val

def parse_product(p, category, product_url):
    name = p.get("name", "")
    body_html = p.get("description", "")
    p_id = str(p.get("id"))
    short_desc = p.get("short_description") or []
    
    # Clean description
    description = clean_html(body_html)
    
    # Specs
    specifications = extract_specifications(body_html, short_desc)
    
    # Infographic / Size guide image URL
    info_image_url = extract_info_image(short_desc)
    
    # Extract option names/values from attributes
    colors = []
    sizes = []
    raw_attrs = p.get("products_attributes") or []
    for attr in raw_attrs:
        name_l = attr.get("name", "").lower()
        vals = attr.get("values") or []
        if "màu" in name_l or "color" in name_l:
            colors = vals
        elif "size" in name_l or "kích" in name_l:
            sizes = vals
            
    # Variants mapping
    variants = []
    prices = []
    compare_prices = []
    images_set = set()
    
    raw_variants = p.get("variations") or []
    for v in raw_variants:
        v_id = str(v.get("id"))
        sku = v.get("custom_id") or ""
        v_title = v.get("title") or ""
        
        # Prices
        price_val = float(v.get("retail_price") or 0)
        orig_val = float(v.get("original_price") or 0)
        
        prices.append(price_val)
        if orig_val and orig_val > price_val:
            compare_prices.append(orig_val)
            
        available = not v.get("is_runout", False) and (v.get("remain_quantity") is None or v.get("remain_quantity") > 0)
        qty = v.get("remain_quantity") or 0
        
        # Options
        color_val, size_val = resolve_options(v.get("fields") or [])
        if not v_title and (color_val and size_val):
            v_title = f"{color_val} / {size_val}"
            
        # Images specific to variant
        v_imgs = v.get("images") or []
        for img in v_imgs:
            if img:
                images_set.add(img)
                
        variants.append({
            "id": v_id,
            "sku": sku,
            "title": v_title,
            "option1": color_val,
            "option2": size_val,
            "option3": None,
            "price": price_val,
            "compare_at_price": orig_val if orig_val > price_val else None,
            "available": available,
            "inventory_quantity": qty,
            "images": v_imgs,
            "featured_image": v_imgs[0] if v_imgs else ""
        })
        
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0
    compare_at_price = max(compare_prices) if compare_prices else None
    
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    # Main product images list (deduplicated variants images)
    images = list(images_set)
    featured_image = images[0] if images else ""
    
    # Backfill variant featured_image if empty
    for v in variants:
        if not v["featured_image"]:
            v["featured_image"] = featured_image
            
    tags = p.get("tags") or []
    
    return {
        "id": p_id,
        "handle": p.get("slug", "").replace("products/", ""),
        "title": name,
        "vendor": VENDOR,
        "type": category,
        "parent_category": "Unisex",
        "gender": "unisex",
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
        "size_guide_image": info_image_url,
        "options": {
            "colors": colors,
            "sizes": sizes
        },
        "specifications": specifications,
        "tags": tags,
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def fetch_all_products(limit=100):
    body = {
        "category_id": "all_products",
        "category_page": {
            "id": "405be574-7685-4145-8b2c-5cf53a8f5292"
        },
        "current_index": 0,
        "disable_filter": False,
        "disable_search": False,
        "lang": "vi",
        "limit": limit,
        "page": 1,
        "query": {
            "category_slug": "all-products",
            "handle_error": True,
            "path": ["categories", "all-products"],
            "site_id": "af59cab4-c62d-4826-8e90-807ce1c501df"
        },
        "search_by_category": False,
        "site_id": "af59cab4-c62d-4826-8e90-807ce1c501df",
        "page_id": "b0efc3b7-b188-47be-89e2-e1333add65e2",
        "domain": "1",
        "is_grid_product": True,
        "date_range": "all",
        "element_id": "GRID-PRODUCT-wrwuljia",
        "currency": "VND",
        "is_published": True,
        "filter_product_by_attr_display": "display_all",
        "dev": "prod",
        "get_dom": False
    }
    
    page = 1
    all_products = []
    while True:
        body["page"] = page
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), headers=HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                if not resp_data.get("success"):
                    break
                products = resp_data.get("data", [])
                if not products:
                    break
                all_products.extend(products)
                if len(products) < limit:
                    break
                page += 1
                time.sleep(0.5)
        except Exception as e:
            print(f"[!] Error fetching products page {page}: {e}")
            break
            
    return all_products

def main():
    print("=" * 60)
    print("🏆 LEVENTS PRODUCT HARVESTER STARTING")
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
            
    # Fetch all products from Storecake API
    print("[*] Querying Storecake API for product details...")
    raw_products = fetch_all_products(100)
    print(f"[*] Retrieved {len(raw_products)} raw products from Storecake database.")
    
    harvest_count = 0
    for p in raw_products:
        slug = p.get("slug", "")
        if not slug:
            continue
            
        p_url = f"{SITE_BASE}/{slug}" if not slug.startswith("http") else slug
        
        # Only parse if it was discovered (not filtered out)
        if p_url in url_to_category:
            p_id = str(p.get("id"))
            if p_id in seen_ids:
                # Prevent duplication: if it is already in seen_ids, we skip
                continue
                
            category = url_to_category[p_url]
            parsed = parse_product(p, category, p_url)
            harvested_products.append(parsed)
            seen_ids.add(p_id)
            harvest_count += 1
            
    # Save the harvested products
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print("🏆 LEVENTS HARVEST COMPLETED!")
    print(f"Total unique products harvested: {len(harvested_products)}")
    print(f"Harvested in this run            : {harvest_count}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
