import json
import os
import sys
import urllib.request
import ssl
import re
import time

# Ensure output is UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CATEGORIES = {
    "Đầm": "https://elise.vn/thoi-trang-nu/dam.html",
    "Áo": "https://elise.vn/thoi-trang-nu/ao.html",
    "Chân Váy": "https://elise.vn/thoi-trang-nu/chan-vay.html",
    "Quần": "https://elise.vn/thoi-trang-nu/quan.html"
}

def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"[!] Error fetching {url}: {e}. Retrying ({attempt+1}/3)...")
            time.sleep(2)
    return None

def main():
    print("=" * 60)
    print("[ELISE] DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    
    # Load existing if exists
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"[*] Loaded existing {sum(len(v) for v in results.values())} URLs from {OUTPUT_JSON_PATH}")
        except:
            pass

    # Ensure results only has the keys we want
    clean_results = {}
    for cat_name in CATEGORIES.keys():
        if cat_name in results:
            clean_results[cat_name] = results[cat_name]
        else:
            clean_results[cat_name] = []
    results = clean_results

    for cat_name, base_url in CATEGORIES.items():
        print(f"\n🚀 Scanning Category: {cat_name}")
        product_urls = set(results.get(cat_name, []))
        page = 1
        seen_page_signatures = set()
        
        while True:
            # Construct page URL
            page_url = base_url
            if page > 1:
                page_url = f"{base_url}?p={page}"
                
            html = fetch_html(page_url)
            if not html:
                print(f"[!] Failed to fetch HTML for {cat_name} at page {page}")
                break
                
            # Extract product links
            # Matches standard Magento product-item-link
            matches = re.findall(r'class="[^"]*product-item-link[^"]*"\s+href="([^"]+)"', html)
            if not matches:
                print(f"[*] No products found on page {page} for {cat_name}. Stopping.")
                break
                
            # Check if this set of products was already seen (redirection or loop)
            page_sig = tuple(sorted(matches))
            if page_sig in seen_page_signatures:
                print(f"[*] Page {page} matches a previously processed page signature (redirected/end of list). Stopping.")
                break
            seen_page_signatures.add(page_sig)
                
            # Deduplicate and clean URLs
            page_added = 0
            for m in matches:
                clean_url = m.split("?")[0]
                if clean_url.startswith("https://elise.vn") and clean_url.endswith(".html"):
                    if clean_url not in product_urls:
                        product_urls.add(clean_url)
                        page_added += 1
            
            print(f"  - Page {page}: Found {len(matches)} product links (added {page_added} unique, Total: {len(product_urls)})")
            
            page += 1
            time.sleep(0.5) # Politeness delay
            
        results[cat_name] = list(product_urls)
        
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved category '{cat_name}' products to: {OUTPUT_JSON_PATH}")

    total_all = sum(len(v) for v in results.values())
    print("\n" + "="*50)
    print("🏆 ELISE DISCOVERY COMPLETED!")
    print(f"Total products discovered: {total_all}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
