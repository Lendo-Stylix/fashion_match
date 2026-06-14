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

# Output paths relative to project root
DISCOVERY_OUT = os.path.abspath(os.path.join(BASE_DIR, "../../discovery/degrey/output/scraped_products.json"))
HARVEST_OUT = os.path.abspath(os.path.join(BASE_DIR, "../../harvest/degrey/output/degrey_products_full.json"))

SITE_BASE = "https://degrey.vn"
VENDOR = "DEGREY"

# SSL Context to bypass certificate verification issues
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
    
    if p_type == "ÁO" or "áo" in title_l:
        if "polo" in title_l:
            return "Áo Polo"
        elif "sơ mi" in title_l or "shirt" in title_l:
            return "Áo Sơ Mi"
        elif "hoodie" in title_l or "sweater" in title_l or "nỉ" in title_l or "len" in title_l:
            return "Áo Hoodie & Nỉ & Len"
        elif "jacket" in title_l or "khoác" in title_l:
            return "Áo Khoác"
        else:
            return "Áo Thun"
    elif p_type == "QUẦN" or "quần" in title_l:
        if "short" in title_l or "lửng" in title_l or "đùi" in title_l:
            return "Quần Shorts"
        else:
            return "Quần Dài"
    elif p_type == "PHỤ KIỆN" or "balo" in title_l or "bag" in title_l or "túi" in title_l or "nón" in title_l or "mũ" in title_l:
        if "balo" in title_l or "bag" in title_l or "túi" in title_l:
            return "Balo & Túi"
        else:
            return "Phụ Kiện"
    else:
        return "Khác"

def extract_color(title, sku):
    title_l = title.lower()
    sku_l = sku.lower() if sku else ""
    
    color_phrases = [
        "trắng sọc đen", "trắng xanh", "đỏ cam", "đen vàng", "đen xám", "wax xám", "wax đen", "wax blue", "wax hồng",
        "đen", "trắng", "xám", "navy", "green", "blue", "cream", "hồng", "đỏ", "vàng", "nâu", "be", "rêu", "kem", "tím", "cam"
    ]
    
    # 1. Whole phrase boundary check
    for cp in color_phrases:
        pattern = r'\b' + re.escape(cp) + r'\b'
        if re.search(pattern, title_l):
            return cp.upper()
            
    # 2. Extract after "màu"
    màu_match = re.search(r'màu\s+([a-zắằẳẵặăấầẩẫậâáàảãạđêếềểễệêíìỉĩịôốồổỗộôớờởỡợơóòỏõọúùủũụưứừửữựýỳỷỹỴ]+(?:\s+[a-zắằẳẵặăấầẩẫậâáàảãạđêếềểễệêíìỉĩịôốồổỗộôớờởỡợơóòỏõọúùủũụưứừửữựýỳỷỹỴ]+)*)', title, re.IGNORECASE)
    if màu_match:
        color_candidate = màu_match.group(1).strip()
        stop_words = [
            "thêu", "in", "áo", "quần", "sport", "tank", "body", "logo", "new", "flannel", "shirt", 
            "athlete", "oversize", "tc", "compressor", "cap", "gods", "gear", "decần", "decade", 
            "short", "pants", "poly", "micro", "kiểu", "dáng", "collab", "box", "cross", "bag",
            "simili", "nap", "basic", "khoá", "gài", "decade", "vest", "kaki", "d dù", "thể thao", 
            "xanh poly", "đỏ cam", "trắng xanh", "dù", "chân cua", "mẫu", "degrey", "tee"
        ]
        words = color_candidate.split()
        cleaned_words = []
        for w in words:
            if w.lower() in stop_words:
                break
            cleaned_words.append(w)
        if cleaned_words:
            return " ".join(cleaned_words).upper()
            
    # 3. Check SKU as fallback
    sku_colors = {
        "navy": "NAVY",
        "green": "GREEN",
        "trang": "TRẮNG",
        "xam": "XÁM",
        "den": "ĐEN",
        "blue": "BLUE",
        "waxblue": "WAX BLUE",
        "waxxam": "WAX XÁM",
        "waxden": "WAX ĐEN",
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
        "Họa tiết": "",
        "Sản xuất": "Vietnam"
    }
    if not body_html:
        return specs
    
    soup = BeautifulSoup(body_html, 'html.parser')
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        is_spec_table = False
        row_data = []
        for row in rows:
            cols = [col.get_text(strip=True) for col in row.find_all(['td', 'th'])]
            if len(cols) >= 2:
                first_cell_l = cols[0].lower()
                if any(kw in first_cell_l for kw in ["đặc tính", "chất liệu", "thương hiệu", "kiểu dáng", "họa tiết", "màu sắc", "màu"]):
                    is_spec_table = True
                row_data.append((cols[0], cols[1]))
        
        if is_spec_table:
            for k, v in row_data:
                kl = k.lower()
                if "chất liệu" in kl:
                    specs["Chất liệu"] = v
                elif "kiểu dáng" in kl or "form" in kl or "dáng" in kl:
                    specs["Form dáng"] = v
                elif "họa tiết" in kl or "artwork" in kl or "hoạ tiết" in kl:
                    specs["Họa tiết"] = v
                elif "màu" in kl or "màu sắc" in kl:
                    specs["Màu sắc"] = v
                elif "sản xuất" in kl or "xuất xứ" in kl:
                    specs["Sản xuất"] = v
            break
            
    # Regex fallback if details still empty
    text = soup.get_text(separator=' ')
    if not specs["Chất liệu"]:
        mat_match = re.search(r'(?:Chất liệu|Thành phần):\s*([^.\n\-]+)', text, re.IGNORECASE)
        if mat_match:
            specs["Chất liệu"] = mat_match.group(1).strip()
            
    if not specs["Form dáng"]:
        form_match = re.search(r'(?:Form|Dáng|Kiểu dáng|Phom dáng):\s*([^.\n\-]+)', text, re.IGNORECASE)
        if form_match:
            specs["Form dáng"] = form_match.group(1).strip()
            
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
    
    # Determine Color
    color_val = extract_color(title, first_var_sku)
    if not color_val and specifications.get("Màu sắc"):
        # Extract from spec table Màu sắc
        spec_color = specifications["Màu sắc"].strip()
        # strip punctuation
        spec_color = re.split(r'[,;\-]', spec_color)[0].strip()
        color_val = spec_color.upper()
        
    # Final color fallback based on title content
    if not color_val:
        if "jean" in title.lower():
            color_val = "BLUE JEAN"
        else:
            color_val = "ĐEN" # Default standard
            
    # Mapped variants
    variants = []
    prices = []
    compare_prices = []
    
    colors = [color_val] if color_val else []
    sizes = []
    
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
        # option1 in Haravan payload is Size. option2, option3 are empty.
        # Project standard requires: option1 = Color, option2 = Size.
        size_val = v.get("option1")
        if size_val == "Default Title" or not size_val:
            size_val = "FREESIZE"
            
        if size_val not in sizes:
            sizes.append(size_val)
            
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
        
    parent_cat = "Nam"
    if "nữ" in category.lower():
        parent_cat = "Nữ"
    elif category in ["Balo & Túi", "Phụ Kiện", "Khác"]:
        parent_cat = "Unisex"
        
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
            "colors": colors,
            "sizes": sizes
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
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
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
    print("🚀 DEGREY CONSOLIDATED SCRAPER: DISCOVERY PHASE")
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
                
        if len(products) < limit:
            break
        page += 1
        time.sleep(0.5)
        
    with open(DISCOVERY_OUT, "w", encoding="utf-8") as f:
        json.dump(discovery_results, f, ensure_ascii=False, indent=2)
        
    print(f"[✓] Discovered unique products: {len(seen_urls)}")
    
    print("\n" + "=" * 60)
    print("🚀 DEGREY CONSOLIDATED SCRAPER: HARVEST PHASE")
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
