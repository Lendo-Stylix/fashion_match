import os
import sys
import io
import json
import time
import ssl
import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

# Setup UTF-8 encoding for Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Config directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Output should map to the project's standard harvest path
HARVEST_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "harvest", "citycycle", "output"))
os.makedirs(HARVEST_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(HARVEST_DIR, "citycycle_products_full.json")

SITE_BASE = "https://citycycle.store"
VENDOR = "City Cycle"

# SSL context to bypass validation errors
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'X-Requested-With': 'XMLHttpRequest'
}

# Exclusions
EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker", "guốc", "boot",
    "đồ lót", "sịp", "boxer", "quần lót", "áo lót", "bra", "panties",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh", "em bé", "kids", "baby"
]

def is_excluded(text: str) -> bool:
    text_l = text.lower()
    is_swimwear = "bơi" in text_l or "swim" in text_l
    is_socks = "tất" in text_l or "vớ" in text_l or "socks" in text_l
    
    for kw in EXCLUDE_KEYWORDS:
        if kw in text_l:
            if kw in ["đồ lót", "quần lót", "áo lót", "boxer", "bra", "sịp"] and (is_swimwear or is_socks):
                continue
            return True
    return False

def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': HEADERS['User-Agent']})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return resp.read().decode('utf-8')
        except Exception as e:
            print(f"  [!] Fetch failed for {url}: {e}. Retrying {attempt+1}/5...")
            time.sleep(1.5 * (attempt + 1))
    return ""

def query_live_inventory(variant_ids: list) -> dict:
    url = f"{SITE_BASE}/product/checkinventory"
    
    payload_data = {}
    for idx, vid in enumerate(variant_ids):
        payload_data[f"ps[{idx}][storeId]"] = "24295"
        payload_data[f"ps[{idx}][id]"] = str(vid)
        
    encoded_data = urllib.parse.urlencode(payload_data).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, headers=HEADERS)
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                res_text = response.read().decode('utf-8')
                res_json = json.loads(res_text)
                return res_json.get("inventories", {})
        except Exception as e:
            print(f"  [!] Failed query inventory attempt {attempt+1}/5: {e}")
            time.sleep(2)
            
    return {}

def parse_specifications(desc_text: str) -> dict:
    specs = {}
    
    # Material
    mat_match = re.search(r'(?:Chất liệu|Chất vải|Chất liệu\s*&\s*Tính năng):\s*([^\n.]+)', desc_text, re.IGNORECASE)
    if mat_match:
        specs["Chất liệu"] = mat_match.group(1).strip()
    else:
        mats = []
        if "cotton" in desc_text.lower():
            mats.append("Classic Cotton")
        if "pique" in desc_text.lower():
            mats.append("Pique Cotton")
        if "len" in desc_text.lower():
            mats.append("Len")
        if "nỉ" in desc_text.lower():
            mats.append("Nỉ")
        if mats:
            specs["Chất liệu"] = ", ".join(mats)
            
    # Kiểu dáng
    fit_match = re.search(r'(?:Kiểu dáng|Form dáng|Phom dáng):\s*([^\n.]+)', desc_text, re.IGNORECASE)
    if fit_match:
        specs["Kiểu dáng"] = fit_match.group(1).strip()
    else:
        fits = []
        if "boxy" in desc_text.lower():
            fits.append("Boxy")
        if "unisex" in desc_text.lower():
            fits.append("Unisex")
        if "form rộng" in desc_text.lower() or "oversize" in desc_text.lower():
            fits.append("Form rộng / Oversized")
        if fits:
            specs["Kiểu dáng"] = ", ".join(fits)
            
    # Print type
    print_match = re.search(r'(?:Hình in|Họa tiết|Công nghệ in):\s*([^\n.]+)', desc_text, re.IGNORECASE)
    if print_match:
        specs["Hình in"] = print_match.group(1).strip()
        
    return specs

def parse_product_page(html: str, url: str, parent_category: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    
    title = soup.find("h1")
    title_text = title.text.strip() if title else ""
    
    code_text = ""
    code_el = soup.find(string=re.compile(r"Mã:", re.IGNORECASE))
    if code_el:
        parent = code_el.parent
        match = re.search(r'Mã:\s*([A-Za-z0-9_-]+)', parent.text, re.IGNORECASE)
        if match:
            code_text = match.group(1).strip()
            
    handle = url.split("/")[-1].replace(".html", "")
    p_id = ""
    id_match = re.search(r'-p(\d+)', handle)
    if id_match:
        p_id = id_match.group(1)
        
    price_min = 0
    compare_at_price = None
    
    old_price_tag = soup.find(class_="tp_product_detail_price_old")
    if old_price_tag:
        sibling = old_price_tag.find_next("b")
        if sibling:
            try:
                compare_at_price = float(re.sub(r"[^\d]", "", sibling.text))
            except:
                pass
                
    promo_price_tag = soup.find(class_="tp_product_detail_price")
    if promo_price_tag:
        sibling = promo_price_tag.find_next("b")
        if sibling:
            try:
                price_min = float(re.sub(r"[^\d]", "", sibling.text))
            except:
                pass
                
    if price_min == 0 and compare_at_price:
        price_min = compare_at_price
        compare_at_price = None
        
    discount_percent = 0
    if compare_at_price and price_min and compare_at_price > price_min:
        discount_percent = int(round((compare_at_price - price_min) / compare_at_price * 100))
        
    desc_section = soup.find("section", class_="pviewcontent")
    desc_text = desc_section.text.strip() if desc_section else ""
    
    images = []
    thumbs = soup.find_all("li", attrs={"data-src": True})
    for t in thumbs:
        src = t.get("data-src")
        if src and src.startswith("http") and src not in images:
            images.append(src)
            
    cz_tags = soup.find_all("img", class_="cloudzoom-gallery")
    for cz in cz_tags:
        src = cz.get("src") or cz.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and src not in images:
                images.append(src)
                
    featured_image = images[0] if images else None
    
    colors = []
    color_pids_map = {}
    color_span = soup.find("span", class_="color")
    if color_span:
        for a in color_span.find_all("a"):
            c_name = a.get("title") or a.get("data-original-title") or a.text.strip()
            pids = a.get("data-pids") or a.get("pids") or ""
            if c_name:
                colors.append(c_name)
                if pids:
                    color_pids_map[c_name] = [x.strip() for x in pids.split(",") if x.strip()]
                    
    sizes = []
    size_span = soup.find("span", class_="size")
    if size_span:
        for a in size_span.find_all("a"):
            s_name = a.text.strip()
            if s_name:
                sizes.append(s_name)
                
    variants = []
    if not colors and not sizes:
        variants.append({
            "id": p_id,
            "sku": code_text,
            "title": "Default",
            "option1": "Default Title",
            "option2": None,
            "price": price_min,
            "compare_at_price": compare_at_price,
            "available": True,
            "inventory_quantity": 0,
            "images": []
        })
    elif colors and not sizes:
        for c in colors:
            v_id = p_id
            pids = color_pids_map.get(c, [])
            if pids:
                v_id = pids[0]
            variants.append({
                "id": v_id,
                "sku": f"{code_text}-{c}" if code_text else "",
                "title": c,
                "option1": c,
                "option2": None,
                "price": price_min,
                "compare_at_price": compare_at_price,
                "available": True,
                "inventory_quantity": 0,
                "images": []
            })
    elif not colors and sizes:
        pids = []
        cz_main = soup.find("img", class_="cloudzoom")
        if cz_main and cz_main.get("data-pids"):
            pids = [x.strip() for x in cz_main.get("data-pids").split(",") if x.strip()]
            
        for idx, s in enumerate(sizes):
            v_id = p_id
            if idx < len(pids):
                v_id = pids[idx]
            variants.append({
                "id": v_id,
                "sku": f"{code_text}-{s}" if code_text else "",
                "title": s,
                "option1": s,
                "option2": None,
                "price": price_min,
                "compare_at_price": compare_at_price,
                "available": True,
                "inventory_quantity": 0,
                "images": []
            })
    else:
        for c in colors:
            pids = color_pids_map.get(c, [])
            for idx, s in enumerate(sizes):
                v_id = p_id
                if idx < len(pids):
                    v_id = pids[idx]
                else:
                    v_id = f"{p_id}-{c}-{s}"
                    
                variants.append({
                    "id": v_id,
                    "sku": f"{code_text}-{c}-{s}" if code_text and code_text != "" else "",
                    "title": f"{c} / {s}",
                    "option1": c,
                    "option2": s,
                    "price": price_min,
                    "compare_at_price": compare_at_price,
                    "available": True,
                    "inventory_quantity": 0,
                    "images": []
                })
                
    specs = parse_specifications(desc_text)
    
    return {
        "id": p_id,
        "handle": handle,
        "title": title_text,
        "vendor": VENDOR,
        "type": parent_category,
        "parent_category": parent_category,
        "description": desc_text,
        "available": True,
        "url": url,
        "price": price_min,
        "price_min": price_min,
        "price_max": price_min,
        "compare_at_price": compare_at_price,
        "discount_percent": discount_percent,
        "images": images,
        "featured_image": featured_image,
        "options": {
            "colors": colors,
            "sizes": sizes
        },
        "specifications": specs,
        "tags": [],
        "variants": variants,
        "_scraped_at": datetime.now().isoformat()
    }

def get_categories():
    print("[*] Parsing categories...")
    # Pre-defined known categories from recon to bypass any selector issues
    fallback = [
        {"name": "T-SHIRT", "url": f"{SITE_BASE}/tshirt-pc185564.html"},
        {"name": "POLO", "url": f"{SITE_BASE}/polo-pc189422.html"},
        {"name": "TANK TOP", "url": f"{SITE_BASE}/tank-top-pc192102.html"},
        {"name": "SHIRT", "url": f"{SITE_BASE}/shirt-pc185577.html"},
        {"name": "SWEATER", "url": f"{SITE_BASE}/sweater-pc185574.html"},
        {"name": "HOODIE", "url": f"{SITE_BASE}/hoodie-pc185565.html"},
        {"name": "HOODIE ZIP", "url": f"{SITE_BASE}/hoodie-zip-pc507303.html"},
        {"name": "JACKET", "url": f"{SITE_BASE}/jacket-pc185573.html"},
        {"name": "SHORTS", "url": f"{SITE_BASE}/shorts-pc185568.html"},
        {"name": "PANTS", "url": f"{SITE_BASE}/pants-pc185579.html"},
        {"name": "JEANS", "url": f"{SITE_BASE}/jeans-pc185578.html"},
        {"name": "SET", "url": f"{SITE_BASE}/set-pc507300.html"},
        {"name": "ACCESSORY", "url": f"{SITE_BASE}/accessory-pc185569.html"}
    ]
    return fallback

def extract_products_from_page(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    links = soup.find_all("a", href=re.compile(r"-p\d+\.html"))
    for a in links:
        href = a.get("href")
        text = a.text.strip()
        
        if href.startswith("/"):
            href = SITE_BASE + href
        elif not href.startswith("http"):
            href = SITE_BASE + "/" + href
            
        href_clean = href.split("?")[0]
        
        if is_excluded(text) or is_excluded(href_clean):
            continue
            
        products.append(href_clean)
        
    return list(set(products))

def parse_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    tp_el = soup.find(class_="totalPages")
    if tp_el:
        try:
            return int(tp_el.text.strip())
        except:
            pass
            
    lbl_el = soup.find(class_="labelPages")
    if lbl_el:
        text = lbl_el.text.strip()
        match = re.search(r'\d+\s*-\s*(\d+)\s*/\s*(\d+)', text)
        if match:
            limit = int(match.group(1))
            total = int(match.group(2))
            if limit > 0:
                import math
                return math.ceil(total / limit)
    return 1

def main():
    print("="*65)
    print("✨ CITY CYCLE CONSOLIDATED SCRAEPR — HIGH AESTHETIC CRAWLER ✨")
    print("="*65)
    
    # 1. DISCOVERY PHASE
    categories = get_categories()
    print(f"[*] Total categories to discover: {len(categories)}")
    
    url_to_cat = {}
    discovered_urls = []
    
    for cat in categories:
        name = cat["name"]
        url = cat["url"]
        print(f"  Discovering category: {name} ({url})...")
        
        html = fetch_html(url)
        if not html:
            continue
            
        p1_urls = extract_products_from_page(html)
        total_pages = parse_total_pages(html)
        print(f"    - Page 1 found {len(p1_urls)} products. Total pages: {total_pages}")
        
        for u in p1_urls:
            if u not in url_to_cat:
                url_to_cat[u] = name
                discovered_urls.append(u)
                
        for page in range(2, total_pages + 1):
            p_url = f"{url}?page={page}"
            p_html = fetch_html(p_url)
            if not p_html:
                continue
            p_urls = extract_products_from_page(p_html)
            print(f"    - Page {page} found {len(p_urls)} products.")
            for u in p_urls:
                if u not in url_to_cat:
                    url_to_cat[u] = name
                    discovered_urls.append(u)
            time.sleep(0.3)
            
    print(f"\n[*] Discovery Complete. Discovered {len(discovered_urls)} unique product URLs.")
    
    # 2. HARVEST PHASE
    # Load existing to resume
    harvested_products = []
    seen_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
                seen_urls = {p["url"] for p in harvested_products}
            print(f"[*] Loaded {len(harvested_products)} existing harvested products.")
        except Exception:
            pass
            
    new_scrapes = 0
    for idx, u in enumerate(discovered_urls):
        if u in seen_urls:
            continue
            
        cat_name = url_to_cat[u]
        print(f"[{idx+1}/{len(discovered_urls)}] Harvesting: {u}")
        
        html = fetch_html(u)
        if not html:
            continue
            
        try:
            parsed = parse_product_page(html, u, cat_name)
            if is_excluded(parsed["title"]) or is_excluded(parsed["type"]):
                continue
                
            harvested_products.append(parsed)
            seen_urls.add(u)
            new_scrapes += 1
        except Exception as e:
            print(f"  [!] Skip error on {u}: {e}")
            
        time.sleep(0.3)
        
        if new_scrapes > 0 and new_scrapes % 10 == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(harvested_products, f, ensure_ascii=False, indent=2)
                
    # 3. QUERY INVENTORIES
    print("\n[*] Refreshing live stocks for harvested variants...")
    variant_ids = []
    variant_to_product = {}
    
    for p_idx, p in enumerate(harvested_products):
        # Variant IDs
        for v_idx, v in enumerate(p.get("variants", [])):
            v_id = str(v["id"])
            if v_id and not v_id.startswith("http") and "-" not in v_id:
                variant_ids.append(v_id)
                variant_to_product[v_id] = (p_idx, v_idx)
        # Parent ID
        p_id = str(p["id"])
        if p_id and p_id not in variant_to_product:
            variant_ids.append(p_id)
            variant_to_product[p_id] = (p_idx, -1)
            
    # Query checkinventory API in batches of 50
    batch_size = 50
    inventory_map = {}
    for i in range(0, len(variant_ids), batch_size):
        batch = variant_ids[i:i+batch_size]
        batch_inv = query_live_inventory(batch)
        inventory_map.update(batch_inv)
        time.sleep(0.3)
        
    # Map back stocks
    for p_idx, p in enumerate(harvested_products):
        p_id = str(p["id"])
        parent_stock = inventory_map.get(p_id, 0)
        
        any_available = False
        for v in p.get("variants", []):
            v_id = str(v["id"])
            stock = inventory_map.get(v_id, 0)
            if v_id == p_id:
                stock = parent_stock
                
            v["inventory_quantity"] = stock
            v["available"] = stock > 0
            if v["available"]:
                any_available = True
                
        p["available"] = any_available
        
    # Write final output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "="*65)
    print("  ✅ SCRAEPR RUN COMPLETED!")
    print(f"  Total unique products : {len(harvested_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output file           : {OUTPUT_FILE}")
    print("="*65)

if __name__ == "__main__":
    main()
