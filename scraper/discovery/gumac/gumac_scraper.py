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

HARVEST_FILE = os.path.join(BASE_DIR, "../../harvest/gumac/output/gumac_products_full.json")
API_BASE = "https://cms.gumac.vn/api/v1"
SITE_BASE = "https://gumac.vn"
PAGE_SIZE = 20

EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker",
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh",
    "mỹ phẩm", "son môi", "kem dưỡng",
]

def is_excluded(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in EXCLUDE_KEYWORDS)

def main():
    print("=" * 60)
    print("[GUMAC] DISCOVERY SCRAPER STARTING")
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
    print("[*] Performing live discovery scrape from GUMAC CMS API...")
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
    total_pages = 1
    while page <= total_pages:
        url = f"{API_BASE}/products?page={page}&limit={PAGE_SIZE}"
        req = urllib.request.Request(url, headers=headers)
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    break
            except Exception:
                time.sleep(2)
        if not data or "data" not in data:
            break
        
        products = data.get("data", {}).get("data", [])
        if page == 1:
            total_pages = data.get("data", {}).get("last_page", 1)
            
        print(f"  Page {page}/{total_pages} — Found {len(products)} items...")
        
        for item in products:
            name = item.get("name", "")
            if is_excluded(name):
                continue
                
            slug = item.get("slug")
            code = item.get("code")
            cat_name = (item.get("category") or {}).get("name") or "General"
            
            p_slug = slug or (code.lower() if code else None)
            if p_slug:
                p_url = f"{SITE_BASE}/{p_slug}"
                if cat_name not in results:
                    results[cat_name] = []
                if p_url not in results[cat_name]:
                    results[cat_name].append(p_url)
                    total_discovered += 1
                    
        page += 1
        time.sleep(0.5)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Live discovery completed. Found {total_discovered} products.")
    print(f"Saved to: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()
