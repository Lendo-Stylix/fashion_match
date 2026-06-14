"""
underarmour.com.vn Full Product Scraper
======================================
Platform: Shopify
API Endpoint: https://underarmour.com.vn/products.json?limit=250&page={page}

Description:
  Automates retrieving the entire Under Armour Vietnam product catalog, 
  filtering out kids' clothing, footwear, cosmetics, and underwear (except swimwear/socks),
  classifying categories and gender, parsing detailed HTML specifications, 
  and saving the structured results into the project's harvest database.

Output:
  harvest/underarmour/output/underarmour_products_full.json
"""

import os
import sys
import json
import time
import ssl
import urllib.request
import urllib.error
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# Set utf-8 encoding for standard output
sys.stdout.reconfigure(encoding='utf-8')

# Paths setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Locate loc_scraper root (experience/underarmour is nested 2 levels down from root)
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

OUTPUT_DIR = os.path.join(ROOT_DIR, "harvest", "underarmour", "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "underarmour_products_full.json")

# Constants
SITE_BASE = "https://underarmour.com.vn"
VENDOR = "UNDER ARMOUR"
PAGE_SIZE = 250
DELAY_SECONDS = 1.0

# Exclusion Lists
EXCLUDE_KIDS = [
    "trẻ em", "bé trai", "bé gái", "sơ sinh", "em bé", "trẻ nhỏ",
    "kid", "kids", "youth", "child", "children", "toddler", "toddlers", "infant", "infants",
    "y ", "y-", "y_s", "y_m", "y_l" # Youth sizes
]

EXCLUDE_FOOTWEAR = [
    "giày", "dép", "guốc", "sandal", "sandals", "sneaker", "sneakers", "boot", "boots",
    "slides", "slippers", "slip-on", "slip-ons", "dép quai ngang", "dép xỏ ngón", "shoes", "footwear"
]

EXCLUDE_UNDERWEAR = [
    "đồ lót", "quần lót", "áo lót", "sịp", "boxer", "boxers", "boxerjock", "brief", "briefs", "panties",
    "bra", "bras", "sports bra", "sports bras", "áo ngực", "underwear"
]

EXCLUDE_COSMETICS = [
    "mỹ phẩm", "trang điểm", "cosmetics", "makeup", "son", "phấn", "kem chống nắng"
]

# Exceptions to Keep (must not be excluded by underwear check)
KEEP_KEYWORDS = [
    "tất", "vớ", "socks", "stockings", "đồ bơi", "swimwear", "swim", "quần bơi", "áo bơi"
]

# Configure SSL to bypass verification if needed
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}

def strip_html_tags(text: str) -> str:
    """Strip HTML tags using regex fallback."""
    if not text:
        return ""
    # Remove script and style contents
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Replace HTML tags with spaces/newlines
    text = re.sub(r'<[^>]+>', ' ', text)
    # Normalize whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_specs_from_html(body_html: str) -> Dict[str, str]:
    """Extract structured product specs (material, fit, style code, technology) from body_html."""
    specs = {}
    if not body_html:
        return specs
    
    # Try importing BeautifulSoup, fall back to regex if not available
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body_html, 'html.parser')
        li_items = [li.get_text().strip() for li in soup.find_all('li') if li.get_text().strip()]
    except ImportError:
        # Regex-based extraction of list items
        li_items = []
        raw_lis = re.findall(r'<li[^>]*>(.*?)</li>', body_html, re.DOTALL | re.IGNORECASE)
        for raw_li in raw_lis:
            clean_li = strip_html_tags(raw_li)
            if clean_li:
                li_items.append(clean_li)
                
    materials = []
    fits = []
    technologies = []
    style_code = None
    
    for text in li_items:
        text_lower = text.lower()
        
        # 1. Style Code (Mã sản phẩm)
        if "mã sản phẩm" in text_lower or "style #" in text_lower or "style:" in text_lower or "mã:" in text_lower:
            code_match = re.search(r'(?:mã sản phẩm|style\s*#|style|mã):\s*([a-z0-9\-]+)', text, re.IGNORECASE)
            if code_match:
                style_code = code_match.group(1).strip()
            else:
                parts = text.split(":")
                if len(parts) > 1:
                    style_code = parts[-1].strip()
            continue
            
        # 2. Material (Chất liệu)
        if "%" in text or "chất liệu" in text_lower or "thành phần" in text_lower or any(m in text_lower for m in ["cotton", "polyester", "elastane", "nylon", "spandex", "viscose", "modal", "wool"]):
            materials.append(text)
            continue
            
        # 3. Fit (Form dáng)
        if "form" in text_lower or "dáng" in text_lower or "fit" in text_lower or any(f in text_lower for f in ["rộng rãi", "thoải mái", "vừa vặn", "ôm sát", "ôm vừa"]):
            fits.append(text)
            continue
            
        # 4. Tech
        if any(tech in text_lower for tech in ["heatgear", "coldgear", "storm", "iso-chill", "rush", "charged"]):
            technologies.append(text)
            
    # Fallback to search body_html text lines if lists are empty
    if not style_code or not materials or not fits:
        clean_desc = strip_html_tags(body_html)
        lines = [line.strip() for line in clean_desc.split(".") if line.strip()]
        for line in lines:
            line_lower = line.lower()
            if not style_code and ("mã sản phẩm" in line_lower or "style #" in line_lower):
                code_match = re.search(r'(?:mã sản phẩm|style\s*#|style|mã):\s*([a-z0-9\-]+)', line, re.IGNORECASE)
                if code_match:
                    style_code = code_match.group(1).strip()
            if not materials and ("%" in line and any(m in line_lower for m in ["cotton", "polyester", "elastane", "nylon", "spandex"])):
                materials.append(line)
            if not fits and ("form dáng" in line_lower or "kiểu dáng" in line_lower or "dáng vừa" in line_lower or "dáng rộng" in line_lower):
                fits.append(line)
                
    if style_code:
        specs["Mã sản phẩm"] = style_code
    if materials:
        specs["Chất liệu"] = "; ".join(materials)
    if fits:
        specs["Form dáng"] = "; ".join(fits)
    if technologies:
        specs["Công nghệ"] = "; ".join(technologies)
        
    return specs

def get_gender_and_category(product: Dict) -> Tuple[str, str]:
    """Determine gender ('male', 'female', 'unisex') and parent_category ('Nam', 'Nữ', 'Unisex')."""
    title = product.get("title", "")
    product_type = product.get("product_type", "")
    tags = product.get("tags", [])
    handle = product.get("handle", "")
    
    text_to_search = f" {title} {product_type} {' '.join(tags)} {handle} ".lower()
    
    # Men indicators
    is_male = False
    if any(w in text_to_search for w in [" nam ", "nam-", "nam_", " men ", "men-", "men's"]):
        is_male = True
    if re.search(r'\b(nam|men|man|mens)\b', title.lower()) or any(t.lower() in ["nam", "men", "mens", "man"] for t in tags):
        is_male = True
        
    # Women indicators
    is_female = False
    if any(w in text_to_search for w in [" nữ ", "nữ-", "nữ_", " women ", "women-", "women's"]):
        is_female = True
    if re.search(r'\b(nữ|women|woman|womens)\b', title.lower()) or any(t.lower() in ["nữ", "women", "womens", "woman"] for t in tags):
        is_female = True
        
    if is_male and is_female:
        return "unisex", "Unisex"
    elif is_male:
        return "male", "Nam"
    elif is_female:
        return "female", "Nữ"
    else:
        return "unisex", "Unisex"

def should_exclude(product: Dict) -> Tuple[bool, Optional[str]]:
    """Apply product filtering constraints."""
    title = product.get("title", "").lower()
    product_type = product.get("product_type", "").lower()
    tags = [t.lower() for t in product.get("tags", [])]
    handle = product.get("handle", "").lower()
    
    search_fields = [title, product_type, handle] + tags
    
    # 1. Kids exclusion
    for kw in EXCLUDE_KIDS:
        for field in search_fields:
            if re.search(r'\b' + re.escape(kw) + r'\b', field) or (kw in ["trẻ em", "bé trai", "bé gái", "sơ sinh", "em bé", "trẻ nhỏ"] and kw in field):
                return True, "kids"
                
    # 2. Cosmetics exclusion
    for kw in EXCLUDE_COSMETICS:
        for field in search_fields:
            if kw in field:
                return True, "cosmetics"
                
    # 3. Footwear exclusion
    for kw in EXCLUDE_FOOTWEAR:
        for field in search_fields:
            if re.search(r'\b' + re.escape(kw) + r'\b', field) or (kw in ["giày", "dép", "dép quai ngang", "dép xỏ ngón"] and kw in field):
                return True, "footwear"
                
    # 4. Underwear/Bra exclusion (with exception for socks & swim)
    is_keep_exception = False
    for kw in KEEP_KEYWORDS:
        for field in search_fields:
            if re.search(r'\b' + re.escape(kw) + r'\b', field) or (kw in ["tất", "vớ", "đồ bơi", "quần bơi", "áo bơi"] and kw in field):
                is_keep_exception = True
                break
        if is_keep_exception:
            break
            
    if not is_keep_exception:
        for kw in EXCLUDE_UNDERWEAR:
            for field in search_fields:
                if re.search(r'\b' + re.escape(kw) + r'\b', field) or (kw in ["đồ lót", "quần lót", "áo lót", "sịp", "áo ngực"] and kw in field):
                    return True, "underwear"
                    
    return False, None

def fetch_products_page(page: int) -> Optional[List[Dict]]:
    """Fetch a single page of Shopify products."""
    url = f"{SITE_BASE}/products.json?limit={PAGE_SIZE}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("products", [])
        except urllib.error.HTTPError as he:
            print(f"    [!] HTTP Error on page {page}, attempt {attempt+1}: {he.code}")
            time.sleep(2)
        except Exception as e:
            print(f"    [!] Error on page {page}, attempt {attempt+1}: {e}")
            time.sleep(2)
    return None

def parse_product(raw: Dict) -> Dict:
    """Parse raw Shopify product dict into standard fashion catalog schema."""
    title = raw.get("title", "")
    handle = raw.get("handle", "")
    product_type = raw.get("product_type", "")
    body_html = raw.get("body_html", "")
    tags = raw.get("tags", [])
    
    # Classify gender and category
    gender, parent_category = get_gender_and_category(raw)
    
    # Parse prices
    prices = []
    compare_prices = []
    
    variants = []
    raw_variants = raw.get("variants", [])
    
    # Map Option Indices
    options_meta = raw.get("options", [])
    color_index = -1
    size_index = -1
    for idx, opt in enumerate(options_meta):
        name_lower = opt.get("name", "").lower()
        if any(kw in name_lower for kw in ["màu", "color", "colour"]):
            color_index = idx
        elif any(kw in name_lower for kw in ["size", "kích", "kích thước", "kích cỡ"]):
            size_index = idx
            
    for v in raw_variants:
        v_id = str(v.get("id"))
        sku = v.get("sku") or ""
        v_title = v.get("title", "")
        
        # Shopify prices are usually strings, parse to float
        price_val = float(v.get("price") or 0)
        comp_val = float(v.get("compare_at_price") or 0) if v.get("compare_at_price") else 0
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
            "option3": opt3 if (color_index == -1 and size_index == -1) else None,
            "price": price_val,
            "compare_at_price": comp_val or None,
            "available": available,
            "inventory_quantity": 1 if available else 0, # Fallback representation
            "images": []
        })
        
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0
    compare_at_price = max(compare_prices) if compare_prices else None
    
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    # Standardize image URLs (must keep absolute paths, no local saving)
    images = [img.get("src") for img in raw.get("images", []) if img.get("src")]
    featured_image = images[0] if images else None
    
    # Extract overall option values list
    colors = []
    sizes = []
    for opt in options_meta:
        name_lower = opt.get("name", "").lower()
        vals = opt.get("values", [])
        if any(kw in name_lower for kw in ["màu", "color", "colour"]):
            colors = vals
        elif any(kw in name_lower for kw in ["size", "kích", "kích thước", "kích cỡ"]):
            sizes = vals
            
    # Description text
    description = strip_html_tags(body_html) if body_html else ""
    
    # Detailed specifications
    specifications = parse_specs_from_html(body_html)
    
    product_url = f"{SITE_BASE}/products/{handle}"
    
    return {
        "id": str(raw.get("id")),
        "handle": handle,
        "title": title,
        "vendor": VENDOR,
        "type": product_type,
        "parent_category": parent_category,
        "category_slug": "all",
        "gender": gender,
        "description": description,
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
        "specifications": specifications,
        "tags": tags,
        "variants": variants,
        "_scraped_at": datetime.now().isoformat(),
        "_scraped_category": "Tất Cả"
    }

def main():
    print("="*65)
    print("  UNDERARMOUR.COM.VN — AUTOMATED PRODUCT SCRAPER")
    print("="*65)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_products = []
    seen_ids = set()
    
    # Duplicate checking
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                all_products = json.load(f)
                seen_ids = {str(p["id"]) for p in all_products}
            print(f"[*] Loaded {len(all_products)} pre-existing products from destination file.")
        except Exception as e:
            print(f"[*] Could not parse existing catalog file: {e}. Starting fresh.")
            
    page = 1
    total_fetched = 0
    total_added = 0
    exclusions_metrics = {"kids": 0, "footwear": 0, "underwear": 0, "cosmetics": 0}
    
    while True:
        print(f"[*] Fetching products page {page}...")
        products = fetch_products_page(page)
        if not products:
            print("[*] No more products returned. Crawl complete.")
            break
            
        print(f"    Fetched {len(products)} products on page {page}.")
        total_fetched += len(products)
        
        new_count = 0
        for raw in products:
            p_id = str(raw.get("id"))
            if p_id in seen_ids:
                continue
                
            exclude, reason = should_exclude(raw)
            if exclude:
                if reason in exclusions_metrics:
                    exclusions_metrics[reason] += 1
                continue
                
            parsed = parse_product(raw)
            all_products.append(parsed)
            seen_ids.add(p_id)
            new_count += 1
            
        print(f"    → Processed page {page}: Added {new_count} new fashion items.")
        total_added += new_count
        
        if len(products) < PAGE_SIZE:
            print("[*] Page returned less than limit size. Reached end.")
            break
            
        page += 1
        time.sleep(DELAY_SECONDS)
        
    # Save the structured file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in all_products)
    
    print("\n" + "=" * 65)
    print("  ✅ SCRAPING STATISTICS FOR UNDER ARMOUR VIETNAM")
    print("=" * 65)
    print(f"  Total items checked       : {total_fetched}")
    print(f"  New items added           : {total_added}")
    print(f"  Total filtered in output  : {len(all_products)}")
    print(f"  Total variants harvested  : {total_variants}")
    print(f"  Filtered Out Kids         : {exclusions_metrics['kids']}")
    print(f"  Filtered Out Footwear     : {exclusions_metrics['footwear']}")
    print(f"  Filtered Out Underwear    : {exclusions_metrics['underwear']}")
    print(f"  Filtered Out Cosmetics    : {exclusions_metrics['cosmetics']}")
    print(f"  Output JSON file          : {OUTPUT_FILE}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
