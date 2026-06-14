import os
import json
import sys
import re
import urllib.request
import ssl
import time
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://4men.com.vn"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

CATEGORIES = [
    {"name": "Áo Sơ Mi Nam", "slug": "ao-so-mi-nam"},
    {"name": "Áo Polo Nam", "slug": "ao-polo-nam"},
    {"name": "Áo Thun Nam", "slug": "ao-thun-nam"},
    {"name": "Áo Khoác Nam", "slug": "ao-khoac-nam"},
    {"name": "Áo Hoodie & Sweatshirt", "slug": "ao-hoodie-sweatshirt-nam"},
    {"name": "Áo Vest & Ghi Lê", "slug": "ao-vest-ghi-le-nam"},
    {"name": "Áo Len Nam", "slug": "ao-len-nam"},
    {"name": "Quần Tây Nam", "slug": "quan-tay-nam"},
    {"name": "Quần Jeans Nam", "slug": "quan-jean-nam"},
    {"name": "Quần Kaki Nam", "slug": "quan-kaki-nam"},
    {"name": "Quần Jogger Nam", "slug": "quan-jogger-nam"},
    {"name": "Quần Shorts Nam", "slug": "quan-short-nam"},
    {"name": "Quần Thể Thao Nam", "slug": "quan-the-thao-nam"},
    {"name": "Thắt Lưng Nam", "slug": "that-lung-nam"},
    {"name": "Ví Da Nam", "slug": "vi-da-nam"},
    {"name": "Cà Vạt & Nơ", "slug": "ca-vat-no"},
    {"name": "Vớ Nam", "slug": "vo-nam"},
    {"name": "Mũ Nón", "slug": "non-nam"},
    {"name": "Balo & Túi Xách", "slug": "tui-xach-nam"}
]

# Exclusion patterns
EXCLUDE_KEYWORDS = [
    # Kids
    "bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "boy", "girl",
    # Footwear
    "giày", "dép", "sandal", "sneaker", "boots", "loafer", "shoes", "slipon",
    # Underwear (except socks/vớ and swimwear)
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp", "sịp", "boxer", "panties", "bra", "underwear",
    # Cosmetics
    "mỹ phẩm", "trang điểm", "makeup", "cosmetics", "son môi", "kem dưỡng", "sữa tắm", "dầu gội", "nước hoa"
]

def is_excluded(title: str, url: str) -> bool:
    title_l = title.lower()
    url_l = url.lower()
    
    # Exceptions to keep: swimwear/đồ bơi, socks/tất/vớ
    if "bơi" in title_l or "swim" in title_l or "vớ" in title_l or "tất" in title_l or "socks" in title_l or "vo-nam" in url_l:
        return False
        
    for kw in EXCLUDE_KEYWORDS:
        if kw in title_l or kw in url_l:
            if kw in ["baby", "boy", "girl", "kids", "bra"]:
                if re.search(r'\b' + kw + r'\b', title_l) or re.search(r'\b' + kw + r'\b', url_l):
                    return True
            else:
                return True
    return False

def fetch_category_page(slug: str, page: int):
    if page == 1:
        url = f"{SITE_BASE}/{slug}.html"
    else:
        url = f"{SITE_BASE}/{slug}/trang-{page}.html"
        
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 404:
                    return None
                return resp.read().decode('utf-8')
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return None
            print(f"  [!] HTTP Error {he.code} fetching {url}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            print(f"  [!] Error fetching {url}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 4MEN DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    total_urls = 0
    seen_urls = set()
    
    # Load existing if available to preserve/resume
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
                for cat, urls in results.items():
                    for u in urls:
                        seen_urls.add(u)
                        total_urls += 1
            print(f"[*] Loaded {total_urls} existing URLs from scraped_products.json.")
        except Exception:
            pass

    for cat in CATEGORIES:
        name = cat["name"]
        slug = cat["slug"]
        print(f"\n[*] Scanning Category: {name} ({slug})...")
        
        if name not in results:
            results[name] = []
            
        page = 1
        
        while True:
            html_content = fetch_category_page(slug, page)
            if not html_content:
                print(f"  - Page {page} not found (404) or empty response. Ending pagination.")
                break
                
            soup = BeautifulSoup(html_content, "html.parser")
            pros = soup.select(".pro")
            
            if not pros:
                print(f"  - Page {page} contains no products. Ending pagination.")
                break
                
            print(f"  - Page {page}: Found {len(pros)} product cards...")
            
            page_added = 0
            for pro in pros:
                var_links = pro.select(".item-thumbs .pc-wrap a")
                product_urls = []
                
                if var_links:
                    for val in var_links:
                        v_href = val.get("href")
                        v_title = val.get("title") or ""
                        if v_href:
                            if v_href.startswith("/"):
                                v_href = SITE_BASE + v_href
                            v_href = v_href.split("?")[0]
                            
                            if not is_excluded(v_title, v_href):
                                product_urls.append((v_title, v_href))
                else:
                    base_a = pro.select_one("h4 a")
                    if base_a:
                        b_href = base_a.get("href")
                        b_title = base_a.text.strip()
                        if b_href:
                            if b_href.startswith("/"):
                                b_href = SITE_BASE + b_href
                            b_href = b_href.split("?")[0]
                            
                            if not is_excluded(b_title, b_href):
                                product_urls.append((b_title, b_href))
                                
                for title, url in product_urls:
                    if url not in seen_urls:
                        results[name].append(url)
                        seen_urls.add(url)
                        page_added += 1
                        total_urls += 1
                        
            print(f"    -> Added {page_added} new unique URLs.")
            
            if len(pros) < 24:
                print(f"  - Page {page} contains less than 24 products ({len(pros)}). Crawl complete for category.")
                break
                
            page += 1
            time.sleep(0.5)
            
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    print("\n" + "=" * 60)
    print("🏆 4MEN DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_urls}")
    print("=" * 60)

if __name__ == "__main__":
    main()
