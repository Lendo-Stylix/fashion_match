"""
Teelab (teelab.vn) Consolidated Scraper
======================================
Platform: Sapo / Bizweb E-Commerce System
API Endpoints:
  - List/Details: https://teelab.vn/products.json?limit=250&page={page}

This script executes both phases sequentially:
1. Discovery Phase: Crawls all products, applies standard filters to exclude kids, underwear, footwear, and cosmetics, classifies categories, and saves URLs to discovery/teelab/output/scraped_products.json.
2. Harvest Phase: Parses details (options, variants, image URLs, specifications) for the discovered products and saves them to harvest/teelab/output/teelab_products_full.json.
"""

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
# Map paths relative to project root
DISCOVERY_OUT = os.path.abspath(os.path.join(BASE_DIR, "../../discovery/teelab/output/scraped_products.json"))
HARVEST_OUT = os.path.abspath(os.path.join(BASE_DIR, "../../harvest/teelab/output/teelab_products_full.json"))

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

def is_kid(title, tags):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
    if "baby tee" in title_l or "baby-tee" in title_l:
        return False
    if "baby pink" in title_l or "baby blue" in title_l:
        return False
        
    kid_kws = ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "boy", "girl", "child", "children"]
    if any(kw in title_l for kw in kid_kws):
        return True
    if any(kw in tags_l for kw in kid_kws):
        return True
    return False

def is_underwear(title, tags, product_type):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
    type_l = (product_type or "").lower()
    
    if any(kw in title_l or kw in tags_l for kw in ["bơi", "swim", "tất", "vớ", "socks"]):
        return False
        
    under_kws = ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer", "panties", "underwear", "innerwear"]
    if any(kw in title_l for kw in under_kws):
        return True
    if any(kw in tags_l for kw in under_kws):
        return True
    if type_l == "innerwear":
        return True
    return False

def is_footwear(title, tags, product_type):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
    type_l = (product_type or "").lower()
    
    if type_l in ["slides", "footwear"]:
        return True
        
    foot_kws = ["giày", "dép", "sandal", "sneaker", "guốc", "derby", "slippers", "giày dép", "sandals"]
    if any(kw in title_l for kw in foot_kws):
        return True
    if any(kw in tags_l for kw in foot_kws):
        return True
    return False

def is_cosmetic(title, tags, product_type):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
    
    cosm_kws = ["mỹ phẩm", "trang điểm", "son môi", "makeup", "cosmetics", "dưỡng da", "sữa tắm", "dầu gội"]
    if any(kw in title_l for kw in cosm_kws):
        return True
    if any(kw in tags_l for kw in cosm_kws):
        return True
    return False

def classify_product(p):
    p_type = (p.get("product_type") or "").upper()
    title = p.get("name", "")
    title_l = title.lower()
    
    if "ÁO THUN" in p_type or "TS" in p_type or "TEE" in p_type or "T-SHIRT" in p_type:
        return "Áo Thun"
    elif "POLO" in p_type or "AP" in p_type:
        return "Áo Polo"
    elif "SƠ MI" in p_type or "SS" in p_type or "SHIRT" in p_type:
        return "Áo Sơ Mi"
    elif "HOODIE" in p_type or "SWEATER" in p_type or "HD" in p_type or "NỈ" in p_type or "LEN" in p_type:
        return "Áo Hoodie & Nỉ & Len"
    elif "KHOÁC" in p_type or "AK" in p_type or "JACKET" in p_type:
        return "Áo Khoác"
    elif "QUẦN DÀI" in p_type or "PS" in p_type or "PANTS" in p_type:
        return "Quần Dài"
    elif "SHORT" in p_type or "SH" in p_type:
        return "Quần Shorts"
    elif "PHỤ KIỆN" in p_type or "AC" in p_type or "SOCKS" in p_type or "tất" in title_l or "vớ" in title_l or "socks" in title_l:
        return "Phụ Kiện"
    else:
        return "Khác"

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
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
    
    base_sku = ""
    if first_variant_sku:
        base_sku = first_variant_sku.split("-")[0].split("_")[0].strip()
    if not base_sku:
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
    p_id = str(p.get("id"))
    
    product_url = f"{SITE_BASE}/{alias}"
    description = clean_html(body_html)
    
    images = []
    raw_images = p.get("images", [])
    for img in raw_images:
        src = img.get("src") if isinstance(img, dict) else img
        if src:
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
            
    featured_image = images[0] if images else ""
    
    raw_variants = p.get("variants", [])
    first_var_sku = raw_variants[0].get("sku", "") if raw_variants else ""
    
    specifications = extract_specifications(body_html, title, first_var_sku)
    
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
        
        opts = v.get("options", [])
        if not opts:
            opts = [v.get("option1"), v.get("option2"), v.get("option3")]
            
        color_val = opts[color_index] if (color_index != -1 and color_index < len(opts)) else None
        size_val = opts[size_index] if (size_index != -1 and size_index < len(opts)) else None
        
        if not color_val and len(opts) > 0:
            color_val = opts[0]
        if not size_val and len(opts) > 1:
            size_val = opts[1]
            
        if color_val and color_val not in colors:
            colors.append(color_val)
        if size_val and size_val not in sizes:
            sizes.append(size_val)
            
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
        
    if not specifications.get("Màu sắc") and colors:
        specifications["Màu sắc"] = ", ".join(colors)
    if not specifications.get("Chất liệu"):
        specifications["Chất liệu"] = "Cotton"
        
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
                    time.sleep(2 ** attempt + 1)
                else:
                    time.sleep(2)
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🚀 TEELAB CONSOLIDATED SCRAPER: DISCOVERY PHASE")
    print("=" * 60)
    
    os.makedirs(os.path.dirname(DISCOVERY_OUT), exist_ok=True)
    os.makedirs(os.path.dirname(HARVEST_OUT), exist_ok=True)
    
    discovery_results = {}
    seen_urls = set()
    page = 1
    limit = 250
    
    while True:
        products = fetch_products_page(page, limit)
        if not products:
            break
            
        print(f"[*] Page {page}: Received {len(products)} products")
        for p in products:
            title = p.get("name", "")
            tags = p.get("tags", [])
            p_type = p.get("product_type") or ""
            alias = p.get("alias", "")
            if not alias:
                continue
            p_url = f"{SITE_BASE}/{alias}"
            
            if is_kid(title, tags) or is_underwear(title, tags, p_type) or is_footwear(title, tags, p_type) or is_cosmetic(title, tags, p_type):
                continue
                
            category = classify_product(p)
            if category not in discovery_results:
                discovery_results[category] = []
            if p_url not in seen_urls:
                discovery_results[category].append(p_url)
                seen_urls.add(p_url)
                
        if len(products) < limit:
            break
        page += 1
        
    with open(DISCOVERY_OUT, "w", encoding="utf-8") as f:
        json.dump(discovery_results, f, ensure_ascii=False, indent=2)
        
    print(f"[✓] Discovered unique products: {len(seen_urls)}")
    
    print("\n" + "=" * 60)
    print("🚀 TEELAB CONSOLIDATED SCRAPER: HARVEST PHASE")
    print("=" * 60)
    
    url_to_category = {}
    for category, urls in discovery_results.items():
        for url in urls:
            url_to_category[url] = category
            
    harvested = []
    seen_ids = set()
    page = 1
    
    while True:
        products = fetch_products_page(page, limit)
        if not products:
            break
            
        for p in products:
            alias = p.get("alias", "")
            if not alias:
                continue
            p_url = f"{SITE_BASE}/{alias}"
            if p_url in url_to_category:
                p_id = str(p.get("id"))
                if p_id in seen_ids:
                    continue
                category = url_to_category[p_url]
                parsed = parse_product(p, category)
                harvested.append(parsed)
                seen_ids.add(p_id)
                
        if len(products) < limit:
            break
        page += 1
        
    with open(HARVEST_OUT, "w", encoding="utf-8") as f:
        json.dump(harvested, f, ensure_ascii=False, indent=2)
        
    print(f"[✓] Harvested unique products: {len(harvested)}")
    print(f"[✓] Output saved to: {HARVEST_OUT}")
    print("=" * 60)

if __name__ == "__main__":
    main()
