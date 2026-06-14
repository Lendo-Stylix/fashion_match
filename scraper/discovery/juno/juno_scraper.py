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

HARVEST_FILE = os.path.join(BASE_DIR, "../../harvest/juno/output/juno_products_full.json")

# Category tree to scrape
CATEGORIES_TO_SCRAPE = [
    {"slug": "giay-xang-dan",   "name": "Giày xăng đan"},
    {"slug": "giay-cao-got",    "name": "Giày cao gót"},
    {"slug": "giay-bup-be",     "name": "Giày búp bê"},
    {"slug": "giay-sneakers",   "name": "Giày Sneakers"},
    {"slug": "dep-guoc",        "name": "Dép guốc"},
    {"slug": "tui-co-nho",      "name": "Túi cỡ nhỏ"},
    {"slug": "tui-co-trung",    "name": "Túi cỡ trung"},
    {"slug": "tui-co-lon",      "name": "Túi cỡ lớn"},
    {"slug": "balo",            "name": "Balo"},
    {"slug": "vi-clutch",       "name": "Ví - Clutch"},
    {"slug": "mat-kinh",        "name": "Mắt kính"},
    {"slug": "non",             "name": "Nón"},
    {"slug": "moc-khoa",        "name": "Móc Khóa"},
    {"slug": "phu-kien-toc",    "name": "Phụ kiện tóc"},
    {"slug": "vo",              "name": "Vớ"},
    {"slug": "dam-jumpsuit",    "name": "Đầm & Jumpsuit"},
    {"slug": "ao",              "name": "Áo"},
    {"slug": "quan",            "name": "Quần"},
    {"slug": "vay",             "name": "Váy"},
    {"slug": "khoac",           "name": "Khoác"},
]

def main():
    print("=" * 60)
    print("[JUNO] DISCOVERY SCRAPER STARTING")
    print("=" * 60)

    # 1. Try to read from harvested data first for maximum speed & offline support
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
                cat_name = item.get("type") or item.get("category_slug") or "General"
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
    print("[*] Performing live discovery scrape from Juno OneLife API...")
    results = {}
    total_discovered = 0
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, */*",
    }

    for cat in CATEGORIES_TO_SCRAPE:
        slug = cat["slug"]
        name = cat["name"]
        results[name] = []
        page = 1
        print(f"Processing category: {name} ({slug})...")
        while True:
            url = f"https://onelife-api.juno.vn/v1/products/categories/{slug}/products?page={page}&limit=40&order=NEWEST&direction=DESC"
            req = urllib.request.Request(url, headers=headers)
            data = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        break
                except Exception as e:
                    time.sleep(2)
            if not data:
                break
            
            products = data.get("products", [])
            if not products:
                break
                
            for p in products:
                p_slug = p.get("slug")
                if p_slug:
                    p_url = f"https://juno.vn/products/{p_slug}"
                    if p_url not in results[name]:
                        results[name].append(p_url)
                        total_discovered += 1
            
            pagination = data.get("pagination", {})
            last_page = pagination.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(0.4)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Live discovery completed. Found {total_discovered} products.")
    print(f"Saved to: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()
