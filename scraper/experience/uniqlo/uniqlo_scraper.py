"""
Uniqlo Vietnam E-Commerce Scraper
=================================
Platform: Custom API (Fast Retailing Commerce API v5)
Discovery: Taxonomies query -> category-by-category product ID collection
Harvest: Concurrent detailed retrieval -> specifications, variants and image links

Output: harvest/uniqlo/output/uniqlo_products_full.json
"""

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
# Map output directly to the harvest structure of the project
OUTPUT_DIR = os.path.join(BASE_DIR, "../../harvest/uniqlo/output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "uniqlo_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://www.uniqlo.com/vn/vi"
API_BASE = "https://www.uniqlo.com/vn/api/commerce/v5/vi"
VENDOR = "Uniqlo"
CONCURRENCY = 4
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

# Excluded categories/keywords
EXCLUDE_KEYWORDS = [
    "bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "infant", "toddler",
    "giày", "dép", "sandal", "sneaker", "guốc", "derby", "shoes", "slides", "boots", "loafer",
    "đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "boxer", "panties", "bra", "underwear",
    "mỹ phẩm", "trang điểm", "makeup", "cosmetics", "dưỡng da", "son môi", "pajamas", "pyjama"
]

# Standard category map
CATEGORY_MAP = {
    "t-shirts": "Áo Thun",
    "ut-graphic-tees": "Áo Thun",
    "peace-for-all": "Áo Thun",
    "polo-shirts": "Áo Polo",
    "dress-shirts": "Áo Sơ Mi",
    "casual-shirts": "Áo Sơ Mi",
    "shirts-and-blouses": "Áo Sơ Mi",
    "shirts": "Áo Sơ Mi",
    "sweatshirts-and-hoodies": "Áo Hoodie & Nỉ & Len",
    "sweaters-and-knitwear": "Áo Hoodie & Nỉ & Len",
    "cardigans": "Áo Hoodie & Nỉ & Len",
    "jackets": "Áo Khoác",
    "blouson-and-parkas": "Áo Khoác",
    "ultra-light-down": "Áo Khoác",
    "miracle-air-jackets": "Áo Khoác",
    "outerwear": "Áo Khoác",
    "coats": "Áo Khoác",
    "fleece": "Áo Khoác",
    "pufftech": "Áo Khoác",
    "shorts": "Quần Shorts",
    "wide-leg-pants": "Quần Dài",
    "chinos": "Quần Dài",
    "jeans": "Quần Dài",
    "easy-pants": "Quần Dài",
    "sweat-pants": "Quần Dài",
    "ankle-pants": "Quần Dài",
    "trousers": "Quần Dài",
    "warm-pants": "Quần Dài",
    "bottoms": "Quần Dài",
    "leggings": "Quần Dài",
    "bags": "Balo & Túi",
    "socks": "Phụ Kiện",
    "fashion-glasses": "Phụ Kiện",
    "hats-and-caps": "Phụ Kiện",
    "neck-warmers": "Phụ Kiện",
    "belts": "Phụ Kiện",
    "umbrellas": "Phụ Kiện",
    "gloves": "Phụ Kiện",
    "accessories": "Phụ Kiện",
    "sunglasses": "Phụ Kiện",
    "scarves": "Phụ Kiện",
    "tights": "Phụ Kiện",
    "hats": "Phụ Kiện",
    "caps": "Phụ Kiện"
}

def is_excluded(title):
    t_clean = title.lower().strip()
    if any(kw in t_clean for kw in ["bơi", "swim", "tất", "vớ", "socks"]):
        if any(kw in t_clean for kw in ["trẻ em", "bé trai", "bé gái", "kids", "baby"]):
            return True
        return False
    return any(kw in t_clean for kw in EXCLUDE_KEYWORDS)

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

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
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
    print("=" * 65)
    print("🚀 UNIQLO.COM FULL WEB SCRAPER (CONCURRENT)")
    print("=" * 65)
    
    # 1. DISCOVERY PHASE
    print("\n--- PHASE 1: DISCOVERY ---")
    print("[*] Fetching taxonomy categories...")
    tax_url = f"{API_BASE}/products/taxonomies?withSubcategories=true"
    tax_data = fetch_json(tax_url)
    if not tax_data or "result" not in tax_data:
        print("[!] Failed to load taxonomies. Exiting.")
        return
        
    result = tax_data["result"]
    categories = result.get("categories", [])
    classes = result.get("classes", [])
    
    target_genders = {17246: "Nam", 17011: "Nữ"}
    query_categories = []
    
    for cat in categories:
        cat_id = cat.get("id")
        cat_name = cat.get("name")
        cat_key = cat.get("key")
        parents = cat.get("parents", [])
        
        gender_id = None
        class_id = None
        for p in parents:
            p_id = p.get("id")
            if p_id in target_genders:
                gender_id = p_id
            elif p_id in [c.get("id") for c in classes]:
                class_id = p_id
                
        if gender_id and class_id:
            mapped_cat = CATEGORY_MAP.get(cat_key)
            if not mapped_cat:
                name_l = cat_name.lower()
                for key, val in CATEGORY_MAP.items():
                    if key in name_l:
                        mapped_cat = val
                        break
                        
            is_under_or_shoe = False
            for parent in parents:
                pk = parent.get("key", "").lower()
                if "underwear" in pk or "bra" in pk or "shoes" in pk or "innerwear" in pk:
                    if cat_key != "socks":
                        is_under_or_shoe = True
            if cat_key in ["underwear", "bra", "shoes", "innerwear", "loungewear"] and cat_key != "socks":
                is_under_or_shoe = True
                
            if mapped_cat and not is_under_or_shoe:
                query_categories.append({
                    "gender_id": gender_id,
                    "class_id": class_id,
                    "category_id": cat_id,
                    "name": cat_name,
                    "mapped_category": mapped_cat,
                    "gender_name": target_genders[gender_id]
                })

    print(f"[*] Discovered {len(query_categories)} category endpoints to crawl.")
    
    url_to_category = {}
    seen_urls = set()
    
    for idx, q in enumerate(query_categories):
        g_id = q["gender_id"]
        cl_id = q["class_id"]
        c_id = q["category_id"]
        mapped_cat = q["mapped_category"]
        
        offset = 0
        limit = 100
        while True:
            path = f"{g_id},{cl_id},{c_id}"
            url = f"{API_BASE}/products?path={path}&genderId={g_id}&offset={offset}&limit={limit}&imageRatio=3x4&httpFailure=true"
            data = fetch_json(url)
            if not data or "result" not in data:
                break
                
            res = data["result"]
            items = res.get("items", [])
            pagination = res.get("pagination", {})
            total = pagination.get("total", 0)
            
            if not items:
                break
                
            for item in items:
                title = item.get("name", "")
                p_id = item.get("productId", "")
                if not p_id or is_excluded(title):
                    continue
                p_url = f"{SITE_BASE}/products/{p_id}"
                
                if p_url not in seen_urls:
                    seen_urls.add(p_url)
                    url_to_category[p_url] = mapped_cat
                    
            if offset + limit >= total or len(items) < limit:
                break
            offset += limit
            time.sleep(0.1)
            
    print(f"[*] Discovery Phase complete. Discovered product count: {len(url_to_category)}")
    
    # 2. HARVEST PHASE
    print("\n--- PHASE 2: HARVEST ---")
    harvested_products = []
    seen_ids = set()
    
    # Load existing to resume
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
            for p in harvested_products:
                seen_ids.add(p["id"])
            print(f"[*] Loaded {len(harvested_products)} existing scraped products. Resuming...")
        except Exception:
            pass
            
    pending_items = []
    for p_url, category in url_to_category.items():
        p_id = p_url.split("/")[-1]
        if p_id not in seen_ids:
            pending_items.append((p_id, category, p_url))
            
    print(f"[*] Remaining products to retrieve: {len(pending_items)}")
    
    if pending_items:
        def process_item(item):
            p_id, category, p_url = item
            res = fetch_product_details(p_id)
            if not res:
                return None
            try:
                return parse_product(res, category)
            except Exception as e:
                print(f"  [!] Error parsing {p_id}: {e}")
                return None

        harvest_count = 0
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            future_to_item = {executor.submit(process_item, item): item for item in pending_items}
            
            for future in as_completed(future_to_item):
                p_id, category, p_url = future_to_item[future]
                parsed = future.result()
                if parsed:
                    harvested_products.append(parsed)
                    seen_ids.add(parsed["id"])
                    harvest_count += 1
                    
                    print(f"[{len(harvested_products)}/{len(url_to_category)}] Harvested: {parsed['id']} ({parsed['_scraped_category']})")
                    
                    if harvest_count % 10 == 0:
                        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
                else:
                    print(f"  [!] Failed to harvest {p_id}")
                time.sleep(DELAY_BETWEEN_BATCHES)
                
    # Save final output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "=" * 65)
    print("  ✅ UNIQLO SCRAPE COMPLETED!")
    print(f"  Total unique products : {len(harvested_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("=" * 65)

if __name__ == "__main__":
    main()
