import json
import os
import sys
import urllib.request
import ssl
import time

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HARVEST_FILE = os.path.join(BASE_DIR, "../../harvest/aristino/output/aristino_products_full.json")
SITE_BASE = "https://aristino.com"
PAGE_SIZE = 250

EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker",
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh", "kids"
]

def is_excluded(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in EXCLUDE_KEYWORDS)

def main():
    print("=" * 60)
    print("[ARISTINO] DISCOVERY SCRAPER STARTING")
    print("=" * 60)

    # 1. Try local rebuild
    if os.path.exists(HARVEST_FILE):
        print(f"[*] Found local harvest file: {HARVEST_FILE}")
        print("[*] Rebuilding discovery scraped_products.json from harvest dataset...")
        try:
            with open(HARVEST_FILE, "r", encoding="utf-8") as f:
                harvest_data = json.load(f)
            
            results = {}
            total = 0
            for item in harvest_data:
                url = item.get("url")
                cat_name = item.get("type") or "General"
                if url:
                    if cat_name not in results:
                        results[cat_name] = []
                    if url not in results[cat_name]:
                        results[cat_name].append(url)
                        total += 1
            
            with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            print(f"✅ Rebuilt {total} URLs across {len(results)} categories.")
            print(f"Saved to: {OUTPUT_JSON_PATH}")
            return
        except Exception as e:
            print(f"[!] Error parsing local harvest file: {e}. Falling back to live scrape...")

    # 2. Live Scrape
    print("[*] Performing live discovery scrape from Shopify API...")
    results = {}
    total_discovered = 0
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, */*",
    }

    page = 1
    while True:
        url = f"{SITE_BASE}/collections/all/products.json?limit={PAGE_SIZE}&page={page}"
        req = urllib.request.Request(url, headers=headers)
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    break
            except Exception:
                time.sleep(2)
        if not data or "products" not in data:
            break
        
        products = data.get("products", [])
        if not products:
            break
            
        print(f"  Page {page} — Found {len(products)} products...")
        
        for p in products:
            title = p.get("title", "")
            if is_excluded(title):
                continue
                
            handle = p.get("handle")
            p_type = p.get("product_type") or "General"
            
            if handle:
                p_url = f"{SITE_BASE}/products/{handle}"
                if p_type not in results:
                    results[p_type] = []
                if p_url not in results[p_type]:
                    results[p_type].append(p_url)
                    total_discovered += 1
                    
        page += 1
        time.sleep(0.7)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Live discovery completed. Found {total_discovered} products.")
    print(f"Saved to: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()
