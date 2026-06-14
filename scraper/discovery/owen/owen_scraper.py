"""
Owen.vn Discovery Scraper
=========================
Platform: Magento 2 (GraphQL API)
Endpoint: https://owen.vn/graphql

This script fetches product URLs for target categories on Owen.vn.
It applies filters to exclude kids items, underwear, footwear, and cosmetics.

Output: discovery/owen/output/scraped_products.json
"""

import os
import sys
import json
import time
import ssl
import re
import urllib.request
import urllib.error
from datetime import datetime

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://owen.vn"
API_ENDPOINT = f"{SITE_BASE}/graphql"
PAGE_SIZE = 50
DELAY = 0.5

# Exclude list settings
EXCLUDE_KEYWORDS = [
    "giày", "dép", "sandal", "sneaker", "guốc", "derby", "slippers", "giày dép", "sandals", "shoes", "footwear",
    "đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer", "panties", "underwear", "innerwear",
    "trẻ em", "bé trai", "bé gái", "trẻ sơ sinh", "kids", "baby", "boy", "girl", "child", "children", "em bé",
    "mỹ phẩm", "trang điểm", "son môi", "makeup", "cosmetics", "dưỡng da", "sữa tắm", "dầu gội"
]

CATEGORIES = [
    # Áo (Parent Nam)
    {"id": "59", "name": "Áo Polo", "parent": "Nam"},
    {"id": "60", "name": "Áo Sơ Mi", "parent": "Nam"},
    {"id": "56", "name": "Áo T-Shirt", "parent": "Nam"},
    {"id": "58", "name": "Áo Veston", "parent": "Nam"},
    {"id": "62", "name": "Áo Jacket", "parent": "Nam"},
    {"id": "57", "name": "Áo Len", "parent": "Nam"},
    {"id": "2472", "name": "Bộ đồ", "parent": "Nam"},
    {"id": "2743", "name": "Áo Blazer", "parent": "Nam"},
    {"id": "3471", "name": "Áo Nỉ", "parent": "Nam"},
    
    # Quần (Parent Nam)
    {"id": "54", "name": "Quần Tây", "parent": "Nam"},
    {"id": "52", "name": "Quần Short", "parent": "Nam"},
    {"id": "55", "name": "Quần Khaki", "parent": "Nam"},
    {"id": "53", "name": "Quần Jeans", "parent": "Nam"},
    {"id": "101", "name": "Quần Jogger", "parent": "Nam"},
    {"id": "3470", "name": "Quần Nỉ", "parent": "Nam"},
    
    # Phụ Kiện (Parent Phụ Kiện)
    {"id": "100", "name": "Tất", "parent": "Phụ Kiện"},
    {"id": "64", "name": "Dây Lưng", "parent": "Phụ Kiện"},
    {"id": "65", "name": "Ví Da", "parent": "Phụ Kiện"},
    {"id": "66", "name": "Cà Vạt", "parent": "Phụ Kiện"}
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json"
}

def is_excluded(title: str) -> bool:
    title_l = title.lower()
    
    # Keep exceptions first
    # 1. Swimwear exception
    if "bơi" in title_l or "swim" in title_l:
        return False
    # 2. Socks exception (Tất/Vớ)
    if "tất" in title_l or "vớ" in title_l or "socks" in title_l:
        return False
    # 3. Belts/Wallets/Ties exceptions are under Accessories, keep them
    if any(kw in title_l for kw in ["dây lưng", "thắt lưng", "belt", "ví", "wallet", "cà vạt", "tie"]):
        return False
        
    for kw in EXCLUDE_KEYWORDS:
        # Use simple substring match for safety
        if kw in title_l:
            # Check for baby tee or baby pink exceptions
            if kw == "baby" and ("baby tee" in title_l or "baby-tee" in title_l or "baby pink" in title_l or "baby blue" in title_l):
                continue
            return True
    return False

def query_graphql(query_str: str, variables: dict) -> dict:
    payload = json.dumps({"query": query_str, "variables": variables}).encode('utf-8')
    req = urllib.request.Request(API_ENDPOINT, data=payload, headers=HEADERS, method='POST')
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
                elif resp.status == 429:
                    wait_t = 2 ** attempt + 1
                    print(f"    [!] HTTP 429 Rate Limited. Waiting {wait_t}s...")
                    time.sleep(wait_t)
                else:
                    time.sleep(2)
        except Exception as e:
            print(f"    [!] Attempt {attempt+1} failed: {e}. Retrying...")
            time.sleep(2 * (attempt + 1))
    return {}

PRODUCTS_QUERY = """
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      name
      url_key
    }
  }
}
"""

def main():
    print("=" * 60)
    print("🏆 OWEN DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    total_discovered = 0
    seen_urls = set()
    
    # Load existing to resume
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
            
    for cat in CATEGORIES:
        cat_id = cat["id"]
        cat_name = cat["name"]
        print(f"\n[*] Fetching category ID {cat_id} ({cat_name})...")
        
        if cat_name not in results:
            results[cat_name] = []
            
        page = 1
        cat_discovered = 0
        
        while True:
            variables = {
                "catId": cat_id,
                "pageSize": PAGE_SIZE,
                "page": page
            }
            
            data = query_graphql(PRODUCTS_QUERY, variables)
            if not data or "data" not in data:
                print(f"  [!] Failed to get page {page}")
                break
                
            products_data = data.get("data", {}).get("products", {})
            items = products_data.get("items") or []
            if not items:
                break
                
            print(f"  Page {page} — fetched {len(items)} products")
            
            page_added = 0
            for item in items:
                name = item.get("name", "")
                url_key = item.get("url_key", "")
                if not url_key:
                    continue
                    
                p_url = f"{SITE_BASE}/{url_key}.html"
                
                # Check exclusions
                if is_excluded(name):
                    print(f"    [Skip] Excluded: '{name}'")
                    continue
                    
                if p_url not in seen_urls:
                    results[cat_name].append(p_url)
                    seen_urls.add(p_url)
                    page_added += 1
                    cat_discovered += 1
                    total_discovered += 1
                    
            print(f"  → Added {page_added} new URLs in page {page}")
            
            total_count = products_data.get("total_count", 0)
            if page * PAGE_SIZE >= total_count:
                break
                
            page += 1
            time.sleep(DELAY)
            
        print(f"[*] Completed category {cat_name}: {cat_discovered} URLs added.")
        
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    print("\n" + "=" * 60)
    print("🏆 OWEN DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
