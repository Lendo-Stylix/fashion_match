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

# Ensure UTF-8 output for Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://citycycle.store"

# SSL context to bypass verification errors
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
}

# Exclusions based on system instructions
EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker", "guốc", "boot",
    "đồ lót", "sịp", "boxer", "quần lót", "áo lót", "bra", "panties",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh", "em bé", "kids", "baby"
]

def is_excluded_text(text: str) -> bool:
    text_l = text.lower()
    # Check underwear exception: keep swimwear (đồ bơi, áo bơi, áo tắm) and socks (tất, vớ)
    is_swimwear = "bơi" in text_l or "swim" in text_l
    is_socks = "tất" in text_l or "vớ" in text_l or "socks" in text_l
    
    # Check basic exclusions
    for kw in EXCLUDE_KEYWORDS:
        if kw in text_l:
            if kw in ["đồ lót", "quần lót", "áo lót", "boxer", "bra", "sịp"] and (is_swimwear or is_socks):
                continue
            return True
    return False

def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return resp.read().decode('utf-8')
        except Exception as e:
            print(f"  [!] Error fetching {url}: {e}. Retrying {attempt+1}/5...")
            time.sleep(1.5 * (attempt + 1))
    return ""

def get_categories():
    print("[*] Loading homepage to extract categories...")
    html = fetch_html(SITE_BASE)
    if not html:
        print("[!] Failed to load homepage.")
        return []
        
    soup = BeautifulSoup(html, "html.parser")
    categories = []
    
    # We inspect standard a tags on homepage that point to category pages (-pcXXXXXX.html)
    menu_links = soup.find_all("a", href=re.compile(r"-pc\d+\.html"))
    print(f"[*] Found {len(menu_links)} potential category links in HTML.")
    
    seen_hrefs = set()
    for a in menu_links:
        href = a.get("href")
        text = a.text.strip()
        
        # Standardize href
        if href.startswith("/"):
            href = SITE_BASE + href
        elif not href.startswith("http"):
            href = SITE_BASE + "/" + href
            
        if href in seen_hrefs:
            continue
            
        # Clean query strings
        href_clean = href.split("?")[0]
        
        # Categorize
        if is_excluded_text(text) or is_excluded_text(href_clean):
            print(f"  [-] Skipping category due to rules: '{text}' ({href_clean})")
            continue
            
        # Standardize names and keep
        if text:
            seen_hrefs.add(href)
            categories.append({
                "name": text.upper(),
                "url": href_clean
            })
            
    # If standard parse yielded too few, use a default fallback matching known menu URLs
    if len(categories) < 3:
        print("[*] Few categories parsed dynamically. Using pre-defined list from reconnaissance...")
        fallback = [
            {"name": "T-SHIRT", "url": f"{SITE_BASE}/tshirt-pc185564.html"},
            {"name": "POLO", "url": f"{SITE_BASE}/polo-pc189422.html"},
            {"name": "TANK TOP", "url": f"{SITE_BASE}/tank-top-pc192102.html"},
            {"name": "SHIRT", "url": f"{SITE_BASE}/shirt-pc185577.html"},
            {"name": "SWEATER", "url": f"{SITE_BASE}/sweater-pc185574.html"},
            {"name": "HOODIE", "url": f"{SITE_BASE}/hoodie-pc185565.html"},
            {"name": "HOODIE ZIP", "url": f"{SITE_BASE}/hoodie-zip-pc507303.html"},
            {"name": "JACKET", "url": f"{SITE_BASE}/jacket-pc185573.html"},
            {"name": "SHORTS", "url": f"{SITE_BASE}/shorts-pc185568.html"},
            {"name": "PANTS", "url": f"{SITE_BASE}/pants-pc185579.html"},
            {"name": "JEANS", "url": f"{SITE_BASE}/jeans-pc185578.html"},
            {"name": "SET", "url": f"{SITE_BASE}/set-pc507300.html"},
            {"name": "ACCESSORY", "url": f"{SITE_BASE}/accessory-pc185569.html"}
        ]
        return fallback
        
    return categories

def extract_products_from_page(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    # Nhanh product link cards typically have class nameBlockText tp_product_name, or end in -pXXXX.html
    links = soup.find_all("a", href=re.compile(r"-p\d+\.html"))
    for a in links:
        href = a.get("href")
        text = a.text.strip()
        
        # Standardize href
        if href.startswith("/"):
            href = SITE_BASE + href
        elif not href.startswith("http"):
            href = SITE_BASE + "/" + href
            
        href_clean = href.split("?")[0]
        
        # Exclude footwear/kids/underwear products if text matches
        if is_excluded_text(text) or is_excluded_text(href_clean):
            continue
            
        products.append(href_clean)
        
    return list(set(products))

def parse_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    # Paginator layout: <a class="totalPages">4</a> or matching text
    tp_el = soup.find(class_="totalPages")
    if tp_el:
        try:
            return int(tp_el.text.strip())
        except:
            pass
            
    # Or parse labelPages: "1 - 24 / 84"
    lbl_el = soup.find(class_="labelPages")
    if lbl_el:
        text = lbl_el.text.strip()
        # Find count numbers
        match = re.search(r'\d+\s*-\s*(\d+)\s*/\s*(\d+)', text)
        if match:
            limit = int(match.group(1))
            total = int(match.group(2))
            if limit > 0:
                import math
                return math.ceil(total / limit)
                
    return 1

def main():
    print("="*60)
    print("🚀 CITY CYCLE DISCOVERY SCRAPER STARTING")
    print("="*60)
    
    categories = get_categories()
    print(f"[*] Found {len(categories)} categories to process:")
    for c in categories:
        print(f"  - {c['name']}: {c['url']}")
        
    results = {}
    seen_urls = set()
    
    # Load existing if available to preserve progress (resume)
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
            for cat, urls in results.items():
                for u in urls:
                    seen_urls.add(u)
            print(f"[*] Loaded existing progress: {len(seen_urls)} unique product URLs.")
        except Exception as e:
            print(f"[!] Warning reading existing output: {e}. Starting fresh.")
            
    for idx, cat in enumerate(categories):
        name = cat["name"]
        url = cat["url"]
        
        # Skip if already done
        if name in results and results[name]:
            print(f"\n[{idx+1}/{len(categories)}] Skipping category: {name} (already has {len(results[name])} products)")
            continue
            
        print(f"\n[{idx+1}/{len(categories)}] Processing category: {name} ({url})")
        results[name] = []
        
        # Fetch page 1 HTML
        html = fetch_html(url)
        if not html:
            print(f"  [!] Failed to load HTML for {url}")
            continue
            
        p1_urls = extract_products_from_page(html)
        total_pages = parse_total_pages(html)
        print(f"  - Page 1: parsed {len(p1_urls)} products. Total pages count: {total_pages}")
        
        for p_url in p1_urls:
            if p_url not in seen_urls:
                results[name].append(p_url)
                seen_urls.add(p_url)
                
        # Parse subsequent pages
        for page in range(2, total_pages + 1):
            page_url = f"{url}?page={page}"
            print(f"  - Fetching page {page}: {page_url}")
            p_html = fetch_html(page_url)
            if not p_html:
                print(f"    [!] Failed to load page {page}")
                continue
                
            p_urls = extract_products_from_page(p_html)
            print(f"    - Page {page}: parsed {len(p_urls)} products.")
            
            added_on_page = 0
            for p_url in p_urls:
                if p_url not in seen_urls:
                    results[name].append(p_url)
                    seen_urls.add(p_url)
                    added_on_page += 1
            print(f"    - Added {added_on_page} new product URLs.")
            time.sleep(1.0) # rate limit delay
            
        print(f"  -> Category {name} finished. Total URLs: {len(results[name])}")
        
        # Save incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        time.sleep(1.0)
        
    print("\n" + "="*50)
    print("🏆 CITY CYCLE DISCOVERY COMPLETE!")
    print(f"  Total categories scraped : {len(results)}")
    print(f"  Total unique URLs found  : {len(seen_urls)}")
    print(f"  Output saved to          : {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
