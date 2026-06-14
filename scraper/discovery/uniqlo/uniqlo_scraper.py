import os
import json
import sys
import re
import urllib.request
import ssl
import time
from datetime import datetime

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://www.uniqlo.com/vn/vi"
API_BASE = "https://www.uniqlo.com/vn/api/commerce/v5/vi"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "x-fr-clientid": "uq.vn.web-spa",
    "x-fr-client-version": "3.2506.1"
}

# Standard exclusions keywords
EXCLUDE_KEYWORDS = [
    "bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "infant", "toddler",
    "giày", "dép", "sandal", "sneaker", "guốc", "derby", "shoes", "slides", "boots", "loafer",
    "đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "boxer", "panties", "bra", "underwear",
    "mỹ phẩm", "trang điểm", "makeup", "cosmetics", "dưỡng da", "son môi", "pajamas", "pyjama"
]

# Standard category map based on Uniqlo category keys
CATEGORY_MAP = {
    # Áo Thun
    "t-shirts": "Áo Thun",
    "ut-graphic-tees": "Áo Thun",
    "peace-for-all": "Áo Thun",
    # Áo Polo
    "polo-shirts": "Áo Polo",
    # Áo Sơ Mi
    "dress-shirts": "Áo Sơ Mi",
    "casual-shirts": "Áo Sơ Mi",
    "shirts-and-blouses": "Áo Sơ Mi",
    "shirts": "Áo Sơ Mi",
    # Áo Hoodie & Nỉ & Len
    "sweatshirts-and-hoodies": "Áo Hoodie & Nỉ & Len",
    "sweaters-and-knitwear": "Áo Hoodie & Nỉ & Len",
    "cardigans": "Áo Hoodie & Nỉ & Len",
    # Áo Khoác
    "jackets": "Áo Khoác",
    "blouson-and-parkas": "Áo Khoác",
    "ultra-light-down": "Áo Khoác",
    "miracle-air-jackets": "Áo Khoác",
    "outerwear": "Áo Khoác",
    "coats": "Áo Khoác",
    "fleece": "Áo Khoác",
    "pufftech": "Áo Khoác",
    # Quần Shorts
    "shorts": "Quần Shorts",
    # Quần Dài
    "wide-leg-pants": "Quần Dài",
    "chinos": "Quần Dài",
    "jeans": "Quần Dài",
    "easy-pants": "Quần Dài",
    "sweat-pants": "Quần Dài",
    "ankle-pants": "Quần Dài",
    "trousers": "Quần Dài",
    "warm-pants": "Quần Dài",
    "bottoms": "Quần Dài",
    "leggings": "Quần Dài",
    # Balo & Túi
    "bags": "Balo & Túi",
    # Phụ Kiện
    "socks": "Phụ Kiện",
    "fashion-glasses": "Phụ Kiện",
    "hats-and-caps": "Phụ Kiện",
    "neck-warmers": "Phụ Kiện",
    "belts": "Phụ Kiện",
    "umbrellas": "Phụ Kiện",
    "gloves": "Phụ Kiện",
    "accessories": "Phụ Kiện",
    "sunglasses": "Phụ Kiện",
    "scarves": "Phụ Kiện",
    "tights": "Phụ Kiện",
    "hats": "Phụ Kiện",
    "caps": "Phụ Kiện"
}

def clean_title(title):
    return title.lower().strip()

def is_excluded(title):
    t_clean = clean_title(title)
    
    # Exceptions: Keep swimwear (đồ bơi, swim) and socks/stockings (tất, vớ, socks)
    if any(kw in t_clean for kw in ["bơi", "swim", "tất", "vớ", "socks"]):
        # But still exclude if it says "giày vớ" or "giày tất" or something kid related
        if any(kw in t_clean for kw in ["trẻ em", "bé trai", "bé gái", "kids", "baby"]):
            return True
        return False
        
    for kw in EXCLUDE_KEYWORDS:
        if kw in t_clean:
            return True
    return False

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[!] Error fetching URL (attempt {attempt+1}/5): {e}")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 UNIQLO DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    # 1. Fetch Taxonomies
    print("[*] Fetching taxonomy data...")
    tax_url = f"{API_BASE}/products/taxonomies?withSubcategories=true"
    tax_data = fetch_json(tax_url)
    if not tax_data or "result" not in tax_data:
        print("[!] Failed to fetch taxonomies. Exiting.")
        return
        
    result = tax_data["result"]
    categories = result.get("categories", [])
    classes = result.get("classes", [])
    
    print(f"[*] Loaded {len(categories)} categories, {len(classes)} classes.")
    
    # Genders of interest: Men (17246) and Women (17011)
    target_genders = {
        17246: "Nam",
        17011: "Nữ"
    }
    
    # Extract query paths
    query_categories = [] # list of dict: {gender_id, class_id, category_id, name, mapped_cat}
    
    for cat in categories:
        cat_id = cat.get("id")
        cat_name = cat.get("name")
        cat_key = cat.get("key")
        parents = cat.get("parents", [])
        
        # Check gender and class parents
        gender_id = None
        class_id = None
        
        for p in parents:
            p_id = p.get("id")
            if p_id in target_genders:
                gender_id = p_id
            elif p_id in [c.get("id") for c in classes]:
                class_id = p_id
                
        if gender_id and class_id:
            # Map category key to project categories
            mapped_cat = CATEGORY_MAP.get(cat_key)
            if not mapped_cat:
                # Fallback check on name
                name_l = cat_name.lower()
                for key, val in CATEGORY_MAP.items():
                    if key in name_l:
                        mapped_cat = val
                        break
                        
            # Exclude category if it is explicitly under underwear or shoes
            is_under_or_shoe = False
            for parent in parents:
                pk = parent.get("key", "").lower()
                if "underwear" in pk or "bra" in pk or "shoes" in pk or "innerwear" in pk:
                    # Keep socks as exception
                    if cat_key != "socks":
                        is_under_or_shoe = True
                        
            if cat_key in ["underwear", "bra", "shoes", "innerwear", "loungewear"]:
                if cat_key != "socks":
                    is_under_or_shoe = True
                    
            if is_under_or_shoe:
                continue
                
            if mapped_cat:
                query_categories.append({
                    "gender_id": gender_id,
                    "class_id": class_id,
                    "category_id": cat_id,
                    "name": cat_name,
                    "key": cat_key,
                    "mapped_category": mapped_cat,
                    "gender_name": target_genders[gender_id]
                })

    print(f"[*] Identified {len(query_categories)} queryable categories.")
    
    results = {}
    seen_urls = set()
    total_discovered = 0
    
    # 2. Query products for each mapped category
    for q_idx, q in enumerate(query_categories):
        g_id = q["gender_id"]
        cl_id = q["class_id"]
        c_id = q["category_id"]
        mapped_cat = q["mapped_category"]
        g_name = q["gender_name"]
        
        print(f"[{q_idx+1}/{len(query_categories)}] Querying category: {g_name} -> {q['name']} (Mapped to: {mapped_cat})")
        
        offset = 0
        limit = 100
        
        while True:
            # Construct path as gender_id,class_id,category_id
            path = f"{g_id},{cl_id},{c_id}"
            url = f"{API_BASE}/products?path={path}&genderId={g_id}&offset={offset}&limit={limit}&imageRatio=3x4&httpFailure=true"
            
            data = fetch_json(url)
            if not data or "result" not in data:
                break
                
            res = data["result"]
            items = res.get("items", [])
            pagination = res.get("pagination", {})
            total = pagination.get("total", 0)
            
            if not items:
                break
                
            added_this_page = 0
            for item in items:
                title = item.get("name", "")
                p_id = item.get("productId", "")
                if not p_id:
                    continue
                    
                # Exclude based on keyword filters
                if is_excluded(title):
                    continue
                    
                p_url = f"{SITE_BASE}/products/{p_id}"
                
                if p_url not in seen_urls:
                    seen_urls.add(p_url)
                    if mapped_cat not in results:
                        results[mapped_cat] = []
                    results[mapped_cat].append(p_url)
                    added_this_page += 1
                    total_discovered += 1
                    
            print(f"  Offset {offset}/{total} — Added {added_this_page} unique products.")
            
            if offset + limit >= total or len(items) < limit:
                break
            offset += limit
            time.sleep(0.3)
            
    # Save output
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print("🏆 UNIQLO DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
