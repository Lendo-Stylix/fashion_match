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

# Output paths relative to script location
DISCOVERY_OUT = os.path.abspath(os.path.join(BASE_DIR, "output/scraped_products.json"))
HARVEST_OUT = os.path.abspath(os.path.join(BASE_DIR, "../../harvest/badrabbit/output/badrabbit_products_full.json"))

SITE_BASE = "https://badrabbitclub.vn"
VENDOR = "Bad Rabbit"

# SSL Context to bypass certificate issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*"
}

def is_kid(title, tags):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags or "").lower()
    
    # Exceptions
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
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags or "").lower()
    type_l = (product_type or "").lower()
    
    # Exceptions: Keep swimwear (đồ bơi) and socks/stockings (tất, vớ)
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
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags or "").lower()
    type_l = (product_type or "").lower()
    
    if type_l in ["slides", "footwear"]:
        return True
        
    foot_kws = ["giày", "dép", "sandal", "sneaker", "guốc", "derby", "slippers", "giày dép", "sandals", "boot", "shoes", "slides"]
    if any(kw in title_l for kw in foot_kws):
        return True
    if any(kw in tags_l for kw in foot_kws):
        return True
    return False

def is_cosmetic(title, tags, product_type):
    title_l = title.lower()
    tags_l = " ".join(tags).lower() if isinstance(tags, list) else str(tags or "").lower()
    
    cosm_kws = ["mỹ phẩm", "trang điểm", "son môi", "makeup", "cosmetics", "dưỡng da", "sữa tắm", "dầu gội"]
    if any(kw in title_l for kw in cosm_kws):
        return True
    if any(kw in tags_l for kw in cosm_kws):
        return True
    return False

def classify_product(p):
    p_type = (p.get("product_type") or "").upper().strip()
    title = p.get("title", "")
    title_l = title.lower()
    
    if p_type == "ÁO THUN" or "áo thun" in title_l or "tee" in title_l:
        return "Áo Thun"
    elif p_type == "ÁO POLO" or "polo" in title_l:
        return "Áo Polo"
    elif p_type == "ÁO SƠ MI" or "sơ mi" in title_l or "shirt" in title_l:
        return "Áo Sơ Mi"
    elif p_type in ["ÁO HOODIE", "ÁO SWEATER", "SWEATER", "HOODIE", "ÁO NỈ", "ÁO LEN"] or any(x in title_l for x in ["hoodie", "sweater", "nỉ", "len"]):
        return "Áo Hoodie & Nỉ & Len"
    elif p_type in ["ÁO KHOÁC", "JACKET", "CARDIGAN"] or any(x in title_l for x in ["jacket", "khoác", "cardigan"]):
        return "Áo Khoác"
    elif p_type == "QUẦN DÀI" or "quần dài" in title_l or "pants" in title_l or "jeans" in title_l:
        return "Quần Dài"
    elif p_type in ["QUẦN SHORTS", "QUẦN SHORT", "SHORTS", "QUẦN ĐÙI", "QUẦN LỬNG"] or any(x in title_l for x in ["short", "đùi", "lửng"]):
        return "Quần Shorts"
    elif p_type in ["BALO", "TÚI", "BAG", "BACKPACK"] or any(x in title_l for x in ["balo", "backpack", "túi xách", "túi đeo"]):
        return "Balo & Túi"
    elif p_type in ["PHỤ KIỆN", "ACCESSORIES", "SOCKS", "TẤT", "VỚ", "NÓN", "MŨ", "CAP", "HAT"] or any(x in title_l for x in ["tất", "vớ", "socks", "nón", "mũ", "cap", "hat", "móc khóa", "keychain", "ví"]):
        return "Phụ Kiện"
    else:
        return "Khác"

def extract_color_fallback(title, sku):
    title_l = title.lower()
    sku_l = sku.lower() if sku else ""
    
    color_phrases = [
        "đen xám", "wax xám", "wax đen", "wax blue", "wax hồng", "đen hồng", "đen vàng", "trắng đen", "trắng hồng", "trắng xanh",
        "đen", "trắng", "xám", "navy", "green", "blue", "cream", "hồng", "đỏ", "vàng", "nâu", "be", "rêu", "kem", "tím", "cam",
        "black", "white", "grey", "pink", "brown", "blue", "yellow", "purple", "orange", "beige"
    ]
    
    for cp in color_phrases:
        pattern = r'\b' + re.escape(cp) + r'\b'
        if re.search(pattern, title_l):
            return cp.upper()
            
    # Check SKU as fallback
    sku_colors = {
        "navy": "NAVY",
        "green": "GREEN",
        "trang": "TRẮNG",
        "xam": "XÁM",
        "den": "ĐEN",
        "blue": "BLUE",
        "vang": "VÀNG",
    }
    for k, v in sku_colors.items():
        if sku_l.endswith(k) or k in sku_l:
            return v
            
    return None

def extract_specifications_from_html(body_html):
    specs = {
        "Chất liệu": "",
        "Form dáng": "",
        "Màu sắc": "",
        "Kỹ thuật": "",
        "Phụ kiện": "",
        "Họa tiết": "",
        "Sản xuất": "Vietnam"
    }
    if not body_html:
        return specs
    
    # Standardize HTML tag boundaries to plain newlines
    html_temp = body_html.replace("<br>", "\n").replace("</p>", "\n").replace("</div>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    soup = BeautifulSoup(html_temp, 'html.parser')
    text = soup.get_text()
    
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        line_clean = re.sub(r'^[•\-\–\s\*]+', '', line).strip()
        
        # Form dáng
        if "form dáng:" in line_clean.lower() or "form:" in line_clean.lower() or "dáng:" in line_clean.lower():
            val = re.sub(r'^(?:form dáng|form|dáng):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Form dáng"] = val
        # Chất liệu
        elif "chất liệu:" in line_clean.lower() or "thành phần:" in line_clean.lower():
            val = re.sub(r'^(?:chất liệu|thành phần):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Chất liệu"] = val
        # Màu sắc
        elif "màu sắc:" in line_clean.lower() or "màu:" in line_clean.lower():
            val = re.sub(r'^(?:màu sắc|màu):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Màu sắc"] = val
        # Kỹ thuật
        elif "kỹ thuật:" in line_clean.lower() or "công nghệ:" in line_clean.lower():
            val = re.sub(r'^(?:kỹ thuật|công nghệ):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Kỹ thuật"] = val
        # Phụ kiện
        elif "phụ kiện:" in line_clean.lower():
            val = re.sub(r'^(?:phụ kiện):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Phụ kiện"] = val
        # Họa tiết
        elif "họa tiết:" in line_clean.lower() or "hoạ tiết:" in line_clean.lower():
            val = re.sub(r'^(?:họa tiết|hoạ tiết):\s*', '', line_clean, flags=re.IGNORECASE).strip()
            specs["Họa tiết"] = val

    # Backup regexes for empty fields
    if not specs["Chất liệu"]:
        mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^.\n\-\–]+)', text, re.IGNORECASE)
        if mat_match:
            specs["Chất liệu"] = mat_match.group(1).strip()
            
    if not specs["Form dáng"]:
        form_match = re.search(r'(?:Form dáng|Form|Dáng):\s*([^.\n\-\–]+)', text, re.IGNORECASE)
        if form_match:
            specs["Form dáng"] = form_match.group(1).strip()
            
    if not specs["Màu sắc"]:
        color_match = re.search(r'(?:Màu sắc|Màu):\s*([^.\n\-\–]+)', text, re.IGNORECASE)
        if color_match:
            specs["Màu sắc"] = color_match.group(1).strip()

    return specs

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # remove tables which we parse separately
    for table in soup.find_all('table'):
        table.decompose()
    text = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', text)
    return clean.strip()

def parse_product(p, category):
    title = p.get("title", "")
    handle = p.get("handle", "")
    body_html = p.get("body_html", "")
    vendor = p.get("vendor", VENDOR)
    p_id = str(p.get("id"))
    
    product_url = f"{SITE_BASE}/products/{handle}"
    description = clean_html(body_html)
    specifications = extract_specifications_from_html(body_html)
    
    # Extract images (absolute URL structure)
    images = []
    raw_images = p.get("images", [])
    for img in raw_images:
        src = img.get("src") if isinstance(img, dict) else img
        if src:
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
            
    featured_image = images[0] if images else ""
    
    # Build options
    raw_variants = p.get("variants", [])
    first_var_sku = raw_variants[0].get("sku", "") if raw_variants else ""
    
    # Dynamic Option Index lookup
    options_meta = p.get("options", [])
    color_index = -1
    size_index = -1
    for idx, opt in enumerate(options_meta):
        name_lower = opt.get("name", "").lower()
        if "màu" in name_lower or "color" in name_lower:
            color_index = idx
        elif "size" in name_lower or "kích" in name_lower:
            size_index = idx

    # Resolve default colors & sizes
    color_val_fallback = extract_color_fallback(title, first_var_sku) or specifications.get("Màu sắc") or "MULTICOLOR"
    
    variants = []
    prices = []
    compare_prices = []
    
    colors_set = set()
    sizes_set = set()
    
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
        
        # Option mapping
        opt1 = v.get("option1")
        opt2 = v.get("option2")
        opt3 = v.get("option3")
        opts = [opt1, opt2, opt3]
        
        color_val = opts[color_index] if (color_index != -1 and color_index < len(opts) and opts[color_index]) else color_val_fallback
        size_val = opts[size_index] if (size_index != -1 and size_index < len(opts) and opts[size_index]) else "FREESIZE"
        
        if color_val == "Default Title" or not color_val:
            color_val = color_val_fallback
        if size_val == "Default Title" or not size_val:
            size_val = "FREESIZE"
            
        colors_set.add(color_val)
        sizes_set.add(size_val)
        
        # Map variant image
        v_img = ""
        image_id = v.get("image_id")
        if image_id:
            for img in raw_images:
                if isinstance(img, dict) and img.get("id") == image_id:
                    v_img = img.get("src")
                    if v_img and v_img.startswith("//"):
                        v_img = "https:" + v_img
                    break
        if not v_img:
            v_img = featured_image
            
        variants.append({
            "id": v_id,
            "sku": sku,
            "title": f"{title} - {color_val} - {size_val}",
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
        
    tags = p.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not tags:
        tags = []
        
    parent_cat = "Unisex" # Standard fallback for Bad Rabbit street wear
    
    return {
        "id": p_id,
        "handle": handle,
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
            "colors": list(colors_set),
            "sizes": list(sizes_set)
        },
        "specifications": specifications,
        "tags": tags,
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def fetch_products_page(page, limit=250):
    url = f"{SITE_BASE}/collections/all/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8')).get("products", [])
                elif resp.status == 429:
                    time.sleep(2 ** attempt + 2)
                else:
                    time.sleep(2)
        except Exception as e:
            print(f"[!] Error fetching page {page} on attempt {attempt+1}: {e}")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🚀 BAD RABBIT CONSOLIDATED SCRAPER: DISCOVERY PHASE")
    print("=" * 60)
    
    os.makedirs(os.path.dirname(DISCOVERY_OUT), exist_ok=True)
    os.makedirs(os.path.dirname(HARVEST_OUT), exist_ok=True)
    
    discovery_results = {}
    seen_urls = set()
    page = 1
    limit = 250
    
    # Fetch all pages
    all_raw_products = []
    while True:
        products = fetch_products_page(page, limit)
        if not products:
            break
            
        print(f"[*] Page {page}: Received {len(products)} products")
        all_raw_products.extend(products)
        
        for p in products:
            title = p.get("title", "")
            tags = p.get("tags", [])
            p_type = p.get("product_type") or ""
            handle = p.get("handle", "")
            if not handle:
                continue
            p_url = f"{SITE_BASE}/products/{handle}"
            
            # Apply exclusion filters
            if is_kid(title, tags) or is_underwear(title, tags, p_type) or is_footwear(title, tags, p_type) or is_cosmetic(title, tags, p_type):
                print(f"  [Skip] Filtered item: {title} | Type: {p_type}")
                continue
                
            category = classify_product(p)
            if category not in discovery_results:
                discovery_results[category] = []
            if p_url not in seen_urls:
                discovery_results[category].append(p_url)
                seen_urls.add(p_url)
                
        # Fix pagination stopping bug (Haravan enforces page limit of 50)
        # Check if list is empty instead of length < limit
        if not products:
            break
        page += 1
        time.sleep(0.5)
        
    with open(DISCOVERY_OUT, "w", encoding="utf-8") as f:
        json.dump(discovery_results, f, ensure_ascii=False, indent=2)
        
    print(f"[✓] Discovered unique products: {len(seen_urls)}")
    
    print("\n" + "=" * 60)
    print("🚀 BAD RABBIT CONSOLIDATED SCRAPER: HARVEST PHASE")
    print("=" * 60)
    
    url_to_category = {}
    for category, urls in discovery_results.items():
        for url in urls:
            url_to_category[url] = category
            
    # Load existing harvested products to merge & prevent duplicates
    harvested_products = []
    seen_ids = set()
    if os.path.exists(HARVEST_OUT):
        try:
            with open(HARVEST_OUT, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
                seen_ids = {str(p["id"]) for p in harvested_products}
            print(f"Loaded {len(harvested_products)} existing products from output file.")
        except Exception:
            pass
            
    added_count = 0
    updated_count = 0
    
    for p in all_raw_products:
        handle = p.get("handle", "")
        if not handle:
            continue
        p_url = f"{SITE_BASE}/products/{handle}"
        
        # Only harvest if it was discovered (meaning it passed exclusion filters)
        if p_url in url_to_category:
            p_id = str(p.get("id"))
            category = url_to_category[p_url]
            parsed = parse_product(p, category)
            
            if p_id in seen_ids:
                # Update existing product in place to prevent duplication
                for idx, old_p in enumerate(harvested_products):
                    if str(old_p["id"]) == p_id:
                        harvested_products[idx] = parsed
                        updated_count += 1
                        break
            else:
                harvested_products.append(parsed)
                seen_ids.add(p_id)
                added_count += 1
                
    with open(HARVEST_OUT, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    print(f"[✓] Harvest complete: Added {added_count} new, Updated {updated_count} existing.")
    print(f"[✓] Total unique products in dataset: {len(harvested_products)}")
    print(f"[✓] Output saved to: {HARVEST_OUT}")
    print("=" * 60)

if __name__ == "__main__":
    main()
