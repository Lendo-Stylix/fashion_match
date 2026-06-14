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

HARVEST_FILE = os.path.join(BASE_DIR, "../../harvest/elise/output/elise_products_full.json")
API_ENDPOINT = "https://elise.vn/graphql"
PAGE_SIZE = 20

# Category tree to crawl
CATEGORIES = [
    {"id": "40", "name": "Áo"},
    {"id": "41", "name": "Đầm"},
    {"id": "42", "name": "Chân Váy"},
    {"id": "43", "name": "Quần"},
    {"id": "165", "name": "Đầm Urban"},
    {"id": "166", "name": "Áo Urban"},
    {"id": "167", "name": "Chân Váy Urban"},
    {"id": "168", "name": "Quần Urban"},
    {"id": "127", "name": "Túi"},
    {"id": "160", "name": "Trang Sức"},
    {"id": "143", "name": "Đầm (Sale)"},
    {"id": "144", "name": "Chân Váy (Sale)"},
    {"id": "145", "name": "Áo (Sale)"},
    {"id": "147", "name": "Quần (Sale)"},
]

PRODUCTS_QUERY = """
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      sku
      url_key
    }
  }
}
"""

def main():
    print("=" * 60)
    print("[ELISE] DISCOVERY SCRAPER STARTING")
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
    print("[*] Performing live discovery scrape from GraphQL...")
    results = {}
    total_discovered = 0
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
    }

    for cat in CATEGORIES:
        cat_id = cat["id"]
        name = cat["name"]
        results[name] = []
        page = 1
        print(f"Processing category: {name} (ID: {cat_id})...")
        while True:
            payload = json.dumps({
                "query": PRODUCTS_QUERY,
                "variables": {"catId": cat_id, "pageSize": PAGE_SIZE, "page": page}
            }).encode('utf-8')
            req = urllib.request.Request(API_ENDPOINT, data=payload, headers=headers, method='POST')
            data = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        break
                except Exception:
                    time.sleep(2)
            if not data or "data" not in data or "products" not in data["data"]:
                break
                
            products_data = data["data"]["products"]
            items = products_data.get("items") or []
            if not items:
                break
                
            for item in items:
                url_key = item.get("url_key")
                sku = item.get("sku")
                p_slug = url_key or (sku.lower() if sku else None)
                if p_slug:
                    p_url = f"https://elise.vn/{p_slug}.html"
                    if p_url not in results[name]:
                        results[name].append(p_url)
                        total_discovered += 1
                        
            total_count = products_data.get("total_count", 0)
            if page * PAGE_SIZE >= total_count:
                break
            page += 1
            time.sleep(0.5)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Live discovery completed. Found {total_discovered} products.")
    print(f"Saved to: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()
