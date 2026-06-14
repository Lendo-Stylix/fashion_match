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

SITE_BASE = "https://dirtycoins.vn"

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
    tags_l = tags.lower()
    
    # Exceptions
    if "baby tee" in title_l or "baby-tee" in title_l:
        return False
    if "baby pink" in title_l or "baby blue" in title_l:
        return False
        
    kid_kws = ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "boy", "girl", "child", "children"]
    if any(kw in title_l for kw in kid_kws):
        return True
    if any(kw in tags_l for kw in kid_kws):
        return True
    return False

def is_underwear(title, tags, product_type):
    title_l = title.lower()
    tags_l = tags.lower()
    type_l = product_type.lower()
    
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
    tags_l = tags.lower()
    type_l = product_type.lower()
    
    if type_l in ["slides", "footwear"]:
        return True
        
    foot_kws = ["giày", "dép", "sandal", "sneaker", "guốc", "derby", "slippers", "giày dép"]
    if any(kw in title_l for kw in foot_kws):
        return True
    if any(kw in tags_l for kw in foot_kws):
        return True
    return False

def is_cosmetic(title, tags, product_type):
    title_l = title.lower()
    tags_l = tags.lower()
    
    cosm_kws = ["mỹ phẩm", "trang điểm", "son môi", "makeup", "cosmetics", "dưỡng da", "sữa tắm", "dầu gội"]
    if any(kw in title_l for kw in cosm_kws):
        return True
    if any(kw in tags_l for kw in cosm_kws):
        return True
    return False

def classify_product(p):
    p_type = (p.get("product_type") or "").upper()
    title = p.get("title", "")
    title_l = title.lower()
    
    # Map types to project standard categories
    if p_type in ["T-SHIRT", "T-SHIRTS", "LONGSLEEVES", "JERSEY", "TANK TOP"]:
        return "Áo Thun"
    elif p_type == "POLOS":
        return "Áo Polo"
    elif p_type == "SHIRT":
        return "Áo Sơ Mi"
    elif p_type in ["HOODIES", "SWEATSHIRT", "SWEATSHIRTS", "FLANNEL", "CARDIGANS", "SWEATERS"]:
        return "Áo Hoodie & Nỉ & Len"
    elif p_type == "JACKETS":
        return "Áo Khoác"
    elif p_type == "PANTS":
        return "Quần Dài"
    elif p_type == "SHORTS":
        return "Quần Shorts"
    elif p_type in ["BOWLER BAGS", "BACKPACKS", "CROSSBODY BAGS", "MINI POUCH"]:
        return "Balo & Túi"
    elif p_type in ["CAPS", "ACCESSORIES", "PHONE CASES", "JEWELRY", "SOCKS"] or "tất" in title_l or "vớ" in title_l or "socks" in title_l:
        return "Phụ Kiện"
    else:
        return "Khác"

def fetch_products_page(page, limit=50):
    url = f"{SITE_BASE}/collections/all/products.json?limit={limit}&page={page}"
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
    print("🏆 DIRTYCOINS DISCOVERY SCRAPER STARTING")
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
    limit = 50
    
    while True:
        print(f"[*] Fetching page {page}...")
        products = fetch_products_page(page, limit)
        if not products:
            print(f"[*] No more products returned at page {page}. Stopping.")
            break
            
        print(f"  - Page {page}: Received {len(products)} products")
        
        page_added = 0
        for p in products:
            title = p.get("title", "")
            tags = p.get("tags", "") or ""
            p_type = p.get("product_type") or ""
            handle = p.get("handle", "")
            
            if not handle:
                continue
                
            p_url = f"{SITE_BASE}/products/{handle}"
            
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
        
    print("\n" + "="*50)
    print("🏆 DIRTYCOINS DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
