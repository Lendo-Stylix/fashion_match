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

SITE_BASE = "https://levents.asia"
API_URL = f"{SITE_BASE}/view/products"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*"
}

EXCLUDE_KEYWORDS_KIDS = ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "boy", "child", "children"]
EXCLUDE_KEYWORDS_UNDERWEAR = ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer", "panties", "underwear", "innerwear"]
EXCLUDE_KEYWORDS_FOOTWEAR = ["giày", "dép", "sandal", "sneaker", "slides", "slide", "shoes", "footwear", "guốc"]
EXCLUDE_KEYWORDS_COSMETIC = ["mỹ phẩm", "trang điểm", "makeup", "cosmetics", "son môi", "dưỡng da", "sữa tắm", "dầu gội"]

def is_excluded(name, tags_list):
    name_l = name.lower()
    tags_l = " ".join([t.lower() for t in tags_list])
    
    # Check gift items
    if "hàng tặng" in name_l or "quà tặng" in name_l or name_l.startswith("[hàng tặng"):
        return True, "Gift Item"
        
    # Kids
    # Exception for "girl tee" or "regular girl" which is adult female fit
    is_kid = False
    if not ("girl tee" in name_l or "regular girl" in name_l):
        if any(kw in name_l for kw in EXCLUDE_KEYWORDS_KIDS) or any(kw in tags_l for kw in EXCLUDE_KEYWORDS_KIDS):
            is_kid = True
    if is_kid:
        return True, "Kids"
        
    # Underwear
    # Exception for socks/stockings (tất, vớ) and swimwear (đồ bơi)
    is_underwear = False
    if not any(kw in name_l or kw in tags_l for kw in ["bơi", "swim", "tất", "vớ", "socks", "sock"]):
        if any(kw in name_l for kw in EXCLUDE_KEYWORDS_UNDERWEAR) or any(kw in tags_l for kw in EXCLUDE_KEYWORDS_UNDERWEAR):
            is_underwear = True
    if is_underwear:
        return True, "Underwear"
        
    # Footwear
    if any(kw in name_l for kw in EXCLUDE_KEYWORDS_FOOTWEAR) or any(kw in tags_l for kw in EXCLUDE_KEYWORDS_FOOTWEAR):
        return True, "Footwear"
        
    # Cosmetic
    if any(kw in name_l for kw in EXCLUDE_KEYWORDS_COSMETIC) or any(kw in tags_l for kw in EXCLUDE_KEYWORDS_COSMETIC):
        return True, "Cosmetics"
        
    return False, None

def classify_product(name):
    name_l = name.lower()
    if "shorts" in name_l or "jorts" in name_l or "shortpants" in name_l:
        return "Quần Shorts"
    elif "tee" in name_l or "t-shirt" in name_l or "tanktop" in name_l or "jersey" in name_l or "long sleeve" in name_l:
        if "polo" in name_l:
            return "Áo Polo"
        return "Áo Thun"
    elif "polo" in name_l:
        return "Áo Polo"
    elif "shirt" in name_l:
        return "Áo Sơ Mi"
    elif "jacket" in name_l:
        return "Áo Khoác"
    elif "hoodie" in name_l or "sweater" in name_l or "cardigan" in name_l:
        return "Áo Hoodie & Nỉ & Len"
    elif "pants" in name_l or "jeans" in name_l or "sweatpants" in name_l:
        return "Quần Dài"
    elif "backpack" in name_l or "bag" in name_l:
        return "Balo & Túi"
    elif "cap" in name_l or "socks" in name_l or "sock" in name_l or "scarf" in name_l or "wallet" in name_l or "holder" in name_l:
        return "Phụ Kiện"
    else:
        return "Khác"

def fetch_products_page(page, limit=100):
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
        "page": page,
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
    
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), headers=HEADERS, method="POST")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                if resp_data.get("success"):
                    return resp_data.get("data", [])
                print(f"[!] API success was False: {resp_data}")
                return None
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 LEVENTS DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    total_discovered = 0
    seen_urls = set()
    
    # Load existing if file exists
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
    limit = 100
    
    while True:
        print(f"[*] Fetching products page {page}...")
        products = fetch_products_page(page, limit)
        if not products:
            print(f"[*] No more products returned at page {page}. Stopping.")
            break
            
        print(f"  - Page {page}: Received {len(products)} products")
        
        page_added = 0
        for p in products:
            name = p.get("name", "")
            tags = p.get("tags") or []
            slug = p.get("slug", "")
            
            if not slug:
                continue
                
            p_url = f"{SITE_BASE}/{slug}" if not slug.startswith("http") else slug
            
            # Apply filters
            excluded, reason = is_excluded(name, tags)
            if excluded:
                print(f"    [Skip] {reason}: '{name}'")
                continue
                
            category = classify_product(name)
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
    print("🏆 LEVENTS DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
