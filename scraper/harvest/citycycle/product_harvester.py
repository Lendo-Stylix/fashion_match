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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "citycycle_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DISCOVERY_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "discovery", "citycycle", "output", "scraped_products.json"))

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
            print(f"  [!] Harvester fetch failed for {url}: {e}. Retrying {attempt+1}/5...")
            time.sleep(1.5 * (attempt + 1))
    return ""

def query_live_inventory(variant_ids: list) -> dict:
    url = f"{SITE_BASE}/product/checkinventory"
    
    # We construct the form-encoded payload for checkinventory
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
    
    # 1. Chất liệu
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
            
    # 2. Kiểu dáng
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
            
    # 3. Hình in / Họa tiết
    print_match = re.search(r'(?:Hình in|Họa tiết|Công nghệ in):\s*([^\n.]+)', desc_text, re.IGNORECASE)
    if print_match:
        specs["Hình in"] = print_match.group(1).strip()
        
    return specs

def parse_product_page(html: str, url: str, parent_category: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    
    title = soup.find("h1")
    title_text = title.text.strip() if title else ""
    
    # SKU (Product Code)
    # Search for element containing "Mã:"
    code_text = ""
    code_el = soup.find(string=re.compile(r"Mã:", re.IGNORECASE))
    if code_el:
        parent = code_el.parent
        match = re.search(r'Mã:\s*([A-Za-z0-9_-]+)', parent.text, re.IGNORECASE)
        if match:
            code_text = match.group(1).strip()
            
    # Handle slug
    handle = url.split("/")[-1].replace(".html", "")
    
    # Product ID is typically at the end of the handle after -p
    p_id = ""
    id_match = re.search(r'-p(\d+)', handle)
    if id_match:
        p_id = id_match.group(1)
        
    # Prices
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
        
    # Description
    desc_section = soup.find("section", class_="pviewcontent")
    desc_text = desc_section.text.strip() if desc_section else ""
    
    # Images (absolute URLs from thumbnails li[data-src] or img.cloudzoom-gallery)
    images = []
    # Thumbnails
    thumbs = soup.find_all("li", attrs={"data-src": True})
    for t in thumbs:
        src = t.get("data-src")
        if src and src.startswith("http") and src not in images:
            images.append(src)
            
    # Fallback to img.cloudzoom-gallery
    cz_tags = soup.find_all("img", class_="cloudzoom-gallery")
    for cz in cz_tags:
        src = cz.get("src") or cz.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and src not in images:
                images.append(src)
                
    featured_image = images[0] if images else None
    
    # Color Option Mapping
    colors = []
    color_pids_map = {}
    
    # Colors are a elements inside .color span
    color_span = soup.find("span", class_="color")
    if color_span:
        for a in color_span.find_all("a"):
            c_name = a.get("title") or a.get("data-original-title") or a.text.strip()
            pids = a.get("data-pids") or a.get("pids") or ""
            if c_name:
                colors.append(c_name)
                if pids:
                    color_pids_map[c_name] = [x.strip() for x in pids.split(",") if x.strip()]
                    
    # Size Option Mapping
    sizes = []
    size_span = soup.find("span", class_="size")
    if size_span:
        for a in size_span.find_all("a"):
            s_name = a.text.strip()
            if s_name:
                sizes.append(s_name)
                
    # Build variants
    variants = []
    # If no colors/sizes found, create default variant
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
        # If no colors but sizes exist, try to parse data-pids from parent Zoom gallery
        # Usually it's in order of sizes
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
        # Both colors and sizes exist
        for c in colors:
            pids = color_pids_map.get(c, [])
            # Map each pid to size in order
            for idx, s in enumerate(sizes):
                v_id = p_id
                if idx < len(pids):
                    v_id = pids[idx]
                else:
                    # Construct a virtual ID if not available
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

def main():
    print("="*60)
    print("🚀 CITY CYCLE PRODUCT HARVESTER STARTING")
    print("="*60)
    
    # 1. Read discovered URLs
    if not os.path.exists(DISCOVERY_FILE):
        print(f"[!] Discovery file not found: {DISCOVERY_FILE}")
        sys.exit(1)
        
    with open(DISCOVERY_FILE, "r", encoding="utf-8") as f:
        discovery_data = json.load(f)
        
    all_urls = []
    url_to_cat = {}
    for cat_name, urls in discovery_data.items():
        for u in urls:
            if u not in all_urls:
                all_urls.append(u)
                url_to_cat[u] = cat_name
                
    print(f"[*] Found {len(all_urls)} product URLs to harvest across {len(discovery_data)} categories.")
    
    # 2. Load existing harvested data to support resume
    harvested_products = []
    seen_pdp_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
                seen_pdp_urls = {p["url"] for p in harvested_products}
            print(f"[*] Loaded {len(harvested_products)} existing harvested products. Skipping already scraped URLs.")
        except Exception as e:
            print(f"[!] Warning reading existing harvested output: {e}. Starting fresh.")
            
    # Harvest details
    new_products = []
    start_time = time.time()
    
    for idx, u in enumerate(all_urls):
        if u in seen_pdp_urls:
            continue
            
        cat_name = url_to_cat[u]
        print(f"[{idx+1}/{len(all_urls)}] Harvesting: {u} ({cat_name})")
        
        html = fetch_html(u)
        if not html:
            print(f"  [!] Failed to download PDP: {u}")
            continue
            
        try:
            parsed = parse_product_page(html, u, cat_name)
            # Check exclusions
            if is_excluded(parsed["title"]) or is_excluded(parsed["type"]):
                print(f"  [-] Skipping product based on exclusions: '{parsed['title']}'")
                continue
                
            new_products.append(parsed)
            harvested_products.append(parsed)
            seen_pdp_urls.add(u)
        except Exception as e:
            print(f"  [!] Error parsing {u}: {e}")
            import traceback
            traceback.print_exc()
            
        # Rate limit delay
        time.sleep(0.5)
        
        # Save incrementally every 10 products
        if len(new_products) > 0 and len(new_products) % 10 == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            print(f"  -> Saved incrementally. Total products: {len(harvested_products)}")
            
    # 3. Query stock counts for all variants in batch
    print("\n[*] Fetching live inventories for variants...")
    # Gather all variant IDs
    variant_ids = []
    variant_to_product = {} # maps variant ID to (product_idx, variant_idx)
    
    for p_idx, p in enumerate(harvested_products):
        for v_idx, v in enumerate(p.get("variants", [])):
            v_id = str(v["id"])
            if v_id and not v_id.startswith("http") and "-" not in v_id:
                variant_ids.append(v_id)
                variant_to_product[v_id] = (p_idx, v_idx)
                
    # Also add parent ID to get parent stock fallback if any
    for p_idx, p in enumerate(harvested_products):
        p_id = str(p["id"])
        if p_id and p_id not in variant_to_product:
            variant_ids.append(p_id)
            variant_to_product[p_id] = (p_idx, -1) # -1 maps to parent
            
    print(f"[*] Querying stock for {len(variant_ids)} IDs in batches...")
    
    # Query in batches of 50
    batch_size = 50
    inventory_map = {}
    for i in range(0, len(variant_ids), batch_size):
        batch = variant_ids[i:i+batch_size]
        print(f"  - Querying batch {i//batch_size + 1}... ")
        batch_inv = query_live_inventory(batch)
        inventory_map.update(batch_inv)
        time.sleep(0.5)
        
    print(f"[*] Received stock results for {len(inventory_map)} items.")
    
    # Update variant stock and availability
    for p_idx, p in enumerate(harvested_products):
        # We also check parent ID stock
        p_id = str(p["id"])
        parent_stock = inventory_map.get(p_id, 0)
        
        any_available = False
        for v in p.get("variants", []):
            v_id = str(v["id"])
            # Get specific variant stock or default to parent stock if it is the parent ID
            stock = inventory_map.get(v_id, 0)
            if v_id == p_id:
                stock = parent_stock
                
            v["inventory_quantity"] = stock
            v["available"] = stock > 0
            if v["available"]:
                any_available = True
                
        p["available"] = any_available
        
    # Save final output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(harvested_products, f, ensure_ascii=False, indent=2)
        
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "="*50)
    print("🏆 HARVESTER COMPLETED SUCCESSFULLY!")
    print(f"  Total unique products : {len(harvested_products)}")
    print(f"  Total variants        : {total_variants}")
    print(f"  Output saved to       : {OUTPUT_FILE}")
    print(f"  Time elapsed          : {time.time() - start_time:.1f} seconds")
    print("="*50)

if __name__ == "__main__":
    main()
