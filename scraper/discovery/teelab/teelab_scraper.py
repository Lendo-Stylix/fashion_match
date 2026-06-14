import os
import json
import sys
import urllib.request
import ssl
import time

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://teelab.vn"

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
    
    # Exceptions (e.g. baby tee, baby pink)
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
    
    # Map Teelab product types to standard project categories
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

def fetch_products_page(page, limit=250):
    url = f"{SITE_BASE}/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8')).get("products", [])
                elif resp.status == 429:
                    wait_t = 2 ** attempt + 1
                    print(f"  [!] HTTP 429 Rate Limited. Waiting {wait_t}s...")
                    time.sleep(wait_t)
                else:
                    time.sleep(2)
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 TEELAB DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    total_discovered = 0
    seen_urls = set()
    
    # Resume from existing if file exists
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
            for cat, urls in results.items():
                for u in urls:
                    seen_urls.add(u)
            print(f"[*] Loaded existing output file with {len(results)} categories and {len(seen_urls)} product URLs.")
        except Exception as e:
            print(f"[!] Error loading existing output: {e}. Starting fresh.")
            
    page = 1
    limit = 250
    
    while True:
        print(f"[*] Fetching page {page}...")
        products = fetch_products_page(page, limit)
        if not products:
            print(f"[*] No more products returned at page {page}. Stopping.")
            break
            
        print(f"  - Page {page}: Received {len(products)} products")
        
        page_added = 0
        for p in products:
            title = p.get("name", "")
            tags = p.get("tags", [])
            p_type = p.get("product_type") or ""
            alias = p.get("alias", "")
            
            if not alias:
                continue
                
            p_url = f"{SITE_BASE}/{alias}"
            
            # Apply filters
            if is_kid(title, tags):
                print(f"    [Skip] Kid: '{title}'")
                continue
            if is_underwear(title, tags, p_type):
                print(f"    [Skip] Underwear: '{title}'")
                continue
            if is_footwear(title, tags, p_type):
                print(f"    [Skip] Footwear: '{title}'")
                continue
            if is_cosmetic(title, tags, p_type):
                print(f"    [Skip] Cosmetic: '{title}'")
                continue
                
            category = classify_product(p)
            if category not in results:
                results[category] = []
                
            if p_url not in seen_urls:
                results[category].append(p_url)
                seen_urls.add(p_url)
                page_added += 1
                total_discovered += 1
                
        print(f"  - Page {page}: Added {page_added} new unique URLs.")
        
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        if len(products) < limit:
            print(f"[*] Less than limit ({limit}) products returned on page {page}. Crawl complete.")
            break
            
        page += 1
        time.sleep(0.5)
        
    print("\n" + "="*60)
    print("🏆 TEELAB DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*60)

if __name__ == "__main__":
    main()
