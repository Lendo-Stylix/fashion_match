import json
import os
import sys
import urllib.request
import ssl
import time
import re

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HARVEST_FILE = os.path.join(BASE_DIR, "../../harvest/coolmate/output/coolmate_products_full.json")
SITE_BASE = "https://www.coolmate.me"

CATEGORIES = [
    {"slug": "ao-thun-nam",          "name": "Áo Thun Nam"},
    {"slug": "ao-thun-nu",           "name": "Áo Thun Nữ"},
    {"slug": "ao-polo-nam",          "name": "Áo Polo Nam"},
    {"slug": "ao-polo-nu",           "name": "Áo Polo Nữ"},
    {"slug": "ao-so-mi-nam",         "name": "Áo Sơ Mi Nam"},
    {"slug": "ao-sweater-len-ni-nam","name": "Áo Sweater Nam"},
    {"slug": "ao-khoac-nam",         "name": "Áo Khoác Nam"},
    {"slug": "ao-khoac-nu",          "name": "Áo Khoác Nữ"},
    {"slug": "ao-ba-lo-tank-top-nam","name": "Áo Tank Top Nam"},
    {"slug": "ao-nam-dai-tay",       "name": "Áo Dài Tay Nam"},
    {"slug": "ao-dai-tay-nu",        "name": "Áo Dài Tay Nữ"},
    {"slug": "ao-cropped-top",       "name": "Áo Crop Top Nữ"},
    {"slug": "ao-nu",                "name": "Áo Nữ"},
    {"slug": "quan-short-nam",       "name": "Quần Short Nam"},
    {"slug": "quan-jogger-nam",      "name": "Quần Jogger Nam"},
    {"slug": "quan-dai-nam",         "name": "Quần Dài Nam"},
    {"slug": "quan-pants-nam",       "name": "Quần Pants Nam"},
    {"slug": "quan-jeans-nam",       "name": "Quần Jeans Nam"},
    {"slug": "quan-kaki-nam",        "name": "Quần Kaki Nam"},
    {"slug": "quan-legging",         "name": "Quần Legging Nữ"},
    {"slug": "quan-short-nu",        "name": "Quần Short Nữ"},
    {"slug": "quan-dai-nu",          "name": "Quần Dài Nữ"},
    {"slug": "vay-dam-nu",           "name": "Váy Đầm Nữ"},
    {"slug": "do-boi-nam",           "name": "Đồ Bơi Nam"},
    {"slug": "do-boi-nam-nu",        "name": "Đồ Bơi"},
    {"slug": "tat-coolmate",         "name": "Tất/Vớ"},
]

def extract_products_from_html(html: str) -> list:
    matches = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', html)
    if not matches:
        return []
    text = "\n".join(matches)
    unescaped = text.replace('\\"', '"').replace('\\\\', '\\')
    idx = unescaped.find('"serverData":')
    if idx == -1:
        return []
    start = unescaped.rfind('{', 0, idx)
    if start == -1:
        return []
    count = 0
    json_str = ""
    for i in range(start, len(unescaped)):
        c = unescaped[i]
        if c == '{':
            count += 1
        elif c == '}':
            count -= 1
        json_str += c
        if count == 0:
            break
    try:
        data = json.loads(json_str)
        return data.get("serverData", {}).get("products", [])
    except Exception:
        return []

def main():
    print("=" * 60)
    print("[COOLMATE] DISCOVERY SCRAPER STARTING")
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
                # Group by their type or general Category Name from CATEGORIES mapping
                cat_name = item.get("category_name") or item.get("parent_category") or "General"
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
    print("[*] Performing live discovery scrape...")
    results = {}
    total_discovered = 0
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    }

    for cat in CATEGORIES:
        slug = cat["slug"]
        name = cat["name"]
        results[name] = []
        page = 1
        print(f"Processing category: {name} ({slug})...")
        while True:
            url = f"{SITE_BASE}/collection/{slug}?page={page}"
            req = urllib.request.Request(url, headers=headers)
            html = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                        html = resp.read().decode('utf-8')
                        break
                except Exception:
                    time.sleep(2)
            if not html:
                break
            
            products = extract_products_from_html(html)
            if not products:
                break
                
            for item in products:
                href = item.get("href", "")
                if href:
                    p_url = f"https://www.coolmate.me/product/{href.strip('/')}"
                    if p_url not in results[name]:
                        results[name].append(p_url)
                        total_discovered += 1
                        
            page += 1
            time.sleep(0.6)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Live discovery completed. Found {total_discovered} products.")
    print(f"Saved to: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()
