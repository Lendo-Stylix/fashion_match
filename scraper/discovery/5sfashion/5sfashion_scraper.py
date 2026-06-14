import os
import json
import sys
import re
import urllib.request
import urllib.error
import ssl
import time
from bs4 import BeautifulSoup
from datetime import datetime

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://5sfashion.vn"
DELAY_BETWEEN_REQUESTS = 0.5  # Polite scraper delay

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

# The category mapping we successfully resolved
CATEGORIES = [
    {"id": "11", "name": "Áo Thun Nam", "parent": "Nam"},
    {"id": "12", "name": "Áo Polo Nam", "parent": "Nam"},
    {"id": "13", "name": "Áo Sơ Mi Nam", "parent": "Nam"},
    {"id": "15", "name": "Áo Chống Nắng Nam", "parent": "Nam"},
    {"id": "16", "name": "Áo Thun Dài Tay Nam", "parent": "Nam"},
    {"id": "17", "name": "Áo Nỉ Nam", "parent": "Nam"},
    {"id": "19", "name": "Áo Len Nam", "parent": "Nam"},
    {"id": "21", "name": "Áo Bomber Nam", "parent": "Nam"},
    {"id": "69", "name": "Áo Khoác Gió Nam", "parent": "Nam"},
    {"id": "70", "name": "Áo Phao Nam", "parent": "Nam"},
    {"id": "61", "name": "Áo Vest - Áo Blazer Nam", "parent": "Nam"},
    {"id": "18", "name": "Áo Khoác Nam", "parent": "Nam"},
    {"id": "24", "name": "Quần Short Thể Thao Nam", "parent": "Nam"},
    {"id": "25", "name": "Quần Short Kaki Nam", "parent": "Nam"},
    {"id": "26", "name": "Quần Short Tây Nam", "parent": "Nam"},
    {"id": "55", "name": "Quần Short Casual Nam", "parent": "Nam"},
    {"id": "27", "name": "Quần Dài Thể Thao Nam", "parent": "Nam"},
    {"id": "28", "name": "Quần Dài Kaki Nam", "parent": "Nam"},
    {"id": "29", "name": "Quần Tây Nam", "parent": "Nam"},
    {"id": "30", "name": "Quần Jeans Nam", "parent": "Nam"},
    {"id": "33", "name": "Tất Nam", "parent": "Nam"},
    {"id": "72", "name": "Bộ Nỉ Nam", "parent": "Nam"},
    {"id": "73", "name": "Bộ Thể Thao Nam", "parent": "Nam"},
    {"id": "74", "name": "Bộ Vest Nam", "parent": "Nam"},
    {"id": "185", "name": "Bộ Đồ Polo Nam", "parent": "Nam"},
    {"id": "186", "name": "Bộ Đồ T-shirt Nam", "parent": "Nam"},
    {"id": "187", "name": "Bộ Sơ Mi Cộc Tay Nam", "parent": "Nam"},
    
    {"id": "101", "name": "Áo Thun Nữ", "parent": "Nữ"},
    {"id": "102", "name": "Áo Sơ Mi Nữ", "parent": "Nữ"},
    {"id": "103", "name": "Áo Len Nữ", "parent": "Nữ"},
    {"id": "104", "name": "Áo Nỉ Nữ", "parent": "Nữ"},
    {"id": "105", "name": "Áo Giữ Nhiệt Nữ", "parent": "Nữ"},
    {"id": "107", "name": "Áo Phao Nữ", "parent": "Nữ"},
    {"id": "168", "name": "Áo Gió Nữ", "parent": "Nữ"},
    {"id": "109", "name": "Áo Bomber Nữ", "parent": "Nữ"},
    {"id": "108", "name": "Áo Khoác Thời Trang Nữ", "parent": "Nữ"},
    {"id": "174", "name": "Áo Chống Nắng Nữ", "parent": "Nữ"},
    {"id": "172", "name": "Áo Polo Nữ", "parent": "Nữ"},
    {"id": "183", "name": "Áo Tank Top Nữ", "parent": "Nữ"},
    {"id": "111", "name": "Quần Âu Nữ", "parent": "Nữ"},
    {"id": "112", "name": "Quần Jeans Nữ", "parent": "Nữ"},
    {"id": "113", "name": "Quần Khác Nữ", "parent": "Nữ"},
    {"id": "180", "name": "Quần Short Nữ", "parent": "Nữ"},
    {"id": "115", "name": "Chân Váy Nữ", "parent": "Nữ"},
    {"id": "114", "name": "Váy Nữ", "parent": "Nữ"},
    {"id": "117", "name": "Tất Chân Nữ", "parent": "Nữ"},
    {"id": "119", "name": "Bộ Đồ Gió Nữ", "parent": "Nữ"},
    {"id": "120", "name": "Bộ Mặc Nhà Nữ", "parent": "Nữ"},
    {"id": "121", "name": "Bộ Nỉ Nữ", "parent": "Nữ"},
    {"id": "173", "name": "Bộ Đồ Mùa Hè Nữ", "parent": "Nữ"}
]

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
    
    # Exceptions: socks/tất/vớ, swimwear/đồ bơi
    if "bơi" in title_l or "swim" in title_l or "vớ" in title_l or "tất" in title_l or "socks" in title_l:
        return False
        
    for kw in EXCLUDE_KEYWORDS:
        if kw in title_l or kw in url_l:
            if kw in ["baby", "boy", "girl", "kids", "bra"]:
                if re.search(r'\b' + kw + r'\b', title_l) or re.search(r'\b' + kw + r'\b', url_l):
                    return True
            else:
                return True
    return False

def fetch_category_page_ajax(category_id: str, page: int):
    url = f"{SITE_BASE}/filter?category={category_id}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    return data
                elif resp.status == 429:
                    wait_t = 2 ** attempt + 1
                    print(f"  [!] HTTP 429 Rate Limited. Waiting {wait_t}s...")
                    time.sleep(wait_t)
                else:
                    print(f"  [!] HTTP Code {resp.status}. Retrying...")
                    time.sleep(2)
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return None
            wait_t = 2 ** attempt + 1
            print(f"  [!] HTTP Error {he.code}. Retrying in {wait_t}s...")
            time.sleep(wait_t)
        except Exception as e:
            print(f"  [!] Connection error: {e}. Retrying...")
            time.sleep(2)
    return None

def main():
    print("=" * 60)
    print("🏆 5S FASHION DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    variant_sku_map = {}
    
    total_urls = 0
    seen_urls = set()
    
    # Load existing if available
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
                if "categories" in results:
                    results = results["categories"]
                for cat, urls in results.items():
                    for u in urls:
                        seen_urls.add(u)
                        total_urls += 1
            print(f"[*] Loaded {total_urls} existing product URLs from scraped_products.json")
        except Exception:
            pass

    SKU_MAP_PATH = os.path.join(OUTPUT_DIR, "variant_sku_map.json")
    if os.path.exists(SKU_MAP_PATH):
        try:
            with open(SKU_MAP_PATH, "r", encoding="utf-8") as f:
                variant_sku_map = json.load(f)
            print(f"[*] Loaded {len(variant_sku_map)} existing variant SKUs from variant_sku_map.json")
        except Exception:
            pass

    for idx, cat in enumerate(CATEGORIES):
        name = cat["name"]
        cat_id = cat["id"]
        print(f"\n[{idx+1}/{len(CATEGORIES)}] Scanning Category: {name} (ID: {cat_id})...")
        
        if name not in results:
            results[name] = []
            
        page = 1
        consecutive_empty = 0
        
        while True:
            ajax_data = fetch_category_page_ajax(cat_id, page)
            if not ajax_data or "content" not in ajax_data:
                print(f"  - Page {page}: Empty response or error. Stopping category.")
                break
                
            content = ajax_data["content"]
            soup = BeautifulSoup(content, "html.parser")
            
            # Look for product cards
            product_cards = soup.select(".item-product")
            if not product_cards:
                print(f"  - Page {page}: No product cards found. Stopping category.")
                break
                
            print(f"  - Page {page}: Found {len(product_cards)} product cards...")
            
            page_added = 0
            for card in product_cards:
                # 1. Parse URLs
                a_link = card.select_one("a[href*='/san-pham/']")
                if not a_link:
                    continue
                    
                href = a_link["href"]
                if href.startswith("/"):
                    href = SITE_BASE + href
                href = href.split("?")[0]
                
                # Title
                title_el = card.select_one(".name-product") or card.select_one(".name")
                title = title_el.text.strip() if title_el else ""
                if not title and a_link.get("title"):
                    title = a_link["title"].strip()
                if not title:
                    title = href.split("/")[-1].replace("-", " ")
                    
                # Exclude check
                if is_excluded(title, href):
                    continue
                    
                # Store
                if href not in seen_urls:
                    results[name].append(href)
                    seen_urls.add(href)
                    page_added += 1
                    total_urls += 1
                    
                # 2. Extract variant SKU mappings
                # Each card has inputs: <input type="hidden" data-sku="..." data-id="..." class="group-color-size" />
                for inp in card.find_all("input", type="hidden"):
                    v_id = inp.get("data-id")
                    v_sku = inp.get("data-sku")
                    if v_id and v_sku:
                        variant_sku_map[str(v_id)] = v_sku
                        
            print(f"    -> Added {page_added} new unique product URLs.")
            
            # If the category has total products returned by AJAX and we have already covered all, or card count < 10
            if len(product_cards) < 12:
                print(f"  - Page {page} has less than 12 cards. Last page reached.")
                break
                
            page += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
        # Save incrementally after each category to support resume
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        with open(SKU_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(variant_sku_map, f, ensure_ascii=False, indent=2)
            
    print("\n" + "=" * 60)
    print("🏆 5S FASHION DISCOVERY COMPLETED!")
    print(f"Total unique URLs discovered   : {total_urls}")
    print(f"Total variant SKUs mapped      : {len(variant_sku_map)}")
    print(f"Output saved to                : {OUTPUT_JSON_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
