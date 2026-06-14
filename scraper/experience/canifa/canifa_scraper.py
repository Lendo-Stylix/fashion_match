import json
import os
import sys
import urllib.request
import ssl
import time

# Ensure output is UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_products(offset, size=100):
    url = "https://canifa.com/v1/middleware/search_product"
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    payload = {
        "indexName": "vue_storefront_catalog_2",
        "query": {
            "query": {
                "bool": {
                    "filter": {
                        "bool": {
                            "must": [
                                {"terms": {"visibility": [2, 3, 4]}},
                                {"terms": {"status": [0, 1]}}
                            ]
                        }
                    }
                }
            }
        },
        "groupToken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJncm91cF9pZCI6MSwiaWQiOjMsInVzZXIiOiJ2YW5kQGdtYWlsLmNvbSJ9.VMNebCbNSLF8xlyoG4qcaWlP21OFgcXJR3Ak2C0Oyac",
        "queryParams": {"from": offset, "size": size, "sort": ""}
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"[!] Error fetching offset {offset}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def should_skip_product(p):
    categories = p.get("categories_map") or []
    cat_names = [c.get("name", "").lower() for c in categories if isinstance(c, dict)]
    sku = (p.get("sku") or "").lower()
    url_key = (p.get("url_key") or "").lower()
    name = (p.get("name") or "").lower()
    
    # 1. Check Kids (Bé trai, Bé gái, Trẻ em, sơ sinh)
    is_kid = False
    if any(x in url_key for x in ["be-trai", "be-gai", "tre-em", "so-sinh", "boy", "girl"]):
        is_kid = True
    if any(x in name for x in ["bé trai", "bé gái", "trẻ em", "sơ sinh"]):
        is_kid = True
    if any(x in c for c in cat_names for x in ["bé trai", "bé gái", "trẻ em", "sơ sinh", "boy", "girl"]):
        is_kid = True
    if sku.startswith("2") or sku.startswith("7"): # Kids SKUs start with 2 or 7 (e.g. 2BK22W001, 2US19A005, 2BS23S004)
        is_kid = True
        
    if is_kid:
        return True
        
    # 2. Check Underwear (Đồ lót)
    is_underwear = False
    if any(x in url_key for x in ["do-lot", "quan-lot", "ao-lot", "sip", "sịp", "boxer", "panties", "bra"]):
        is_underwear = True
    if any(x in name for x in ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer"]):
        is_underwear = True
    if any(x in c for c in cat_names for x in ["đồ lót", "quần lót", "áo lót", "sịp", "bra"]):
        is_underwear = True
        
    # Exceptions to Keep: Đồ bơi (swimwear), Tất, Vớ (socks)
    is_swimwear = "bơi" in name or "swim" in name or "bơi" in url_key or "swim" in url_key or any("bơi" in c or "swim" in c for c in cat_names)
    is_socks = "tất" in name or "vớ" in name or "tat" in url_key or "vo" in url_key or any("tất" in c or "vớ" in c or "tat" in c for c in cat_names)
    
    if is_underwear and not (is_swimwear or is_socks):
        return True
        
    return False

def classify_product(p):
    categories = p.get("categories_map") or []
    cat_names = [c.get("name", "").lower() for c in categories if isinstance(c, dict)]
    sku = (p.get("sku") or "").lower()
    url_key = (p.get("url_key") or "").lower()
    name = (p.get("name") or "").lower()
    
    gender = "General"
    is_kid = False
    
    has_boy = any("bé trai" in c or "boy" in c for c in cat_names) or "be-trai" in url_key or "boy" in url_key
    has_girl = any("bé gái" in c or "girl" in c for c in cat_names) or "be-gai" in url_key or "girl" in url_key
    has_men = any("nam" in c or "men" in c for c in cat_names) or "nam" in url_key
    has_women = any("nữ" in c or "women" in c for c in cat_names) or "nu" in url_key
    
    if has_boy:
        gender = "Bé Trai"
        is_kid = True
    elif has_girl:
        gender = "Bé Gái"
        is_kid = True
    elif has_men:
        gender = "Nam"
    elif has_women:
        gender = "Nữ"
    elif "tre-em" in url_key or "trẻ em" in name:
        gender = "Trẻ Em"
        is_kid = True
        
    if gender == "General":
        if "nam" in name and "nữ" not in name:
            gender = "Nam"
        elif "nữ" in name:
            gender = "Nữ"
        elif "bé trai" in name:
            gender = "Bé Trai"
            is_kid = True
        elif "bé gái" in name:
            gender = "Bé Gái"
            is_kid = True
            
    p_type = "General"
    
    if any("áo phông" in c or "áo thun" in c or "t-shirt" in c for c in cat_names) or "ao-phong" in url_key or "ao-thun" in url_key or "tshirt" in name or "ao phong" in name or "áo phông" in name or "áo thun" in name:
        p_type = "Áo Thun"
    elif any("polo" in c for c in cat_names) or "polo" in url_key or "polo" in name:
        p_type = "Áo Polo"
    elif any("sơ mi" in c or "so-mi" in c for c in cat_names) or "so-mi" in url_key or "sơ mi" in name:
        p_type = "Áo Sơ Mi"
    elif any("áo len" in c or "ao-len" in c for c in cat_names) or "ao-len" in url_key or "áo len" in name:
        p_type = "Áo Len"
    elif any("nỉ" in c for c in cat_names) or "ao-ni" in url_key or "quần-ni" in url_key or "nỉ" in name:
        p_type = "Đồ Nỉ"
    elif any("chống nắng" in c or "chong-nang" in c for c in cat_names) or "chong-nang" in url_key or "chống nắng" in name:
        p_type = "Chống Nắng"
    elif any("áo khoác" in c or "ao-khoac" in c for c in cat_names) or "ao-khoac" in url_key or "áo khoác" in name:
        p_type = "Áo Khoác"
    elif any("quần shorts" in c or "quan-shorts" in c or "short" in c for c in cat_names) or "quan-shorts" in url_key or "short" in name:
        p_type = "Quần Shorts"
    elif any("quần dài" in c or "jeans" in c or "khaki" in c or "quan-vai" in c or "quần kaki" in c for c in cat_names) or "quan-jeans" in url_key or "quan-dai" in url_key or "quần dài" in name or "jeans" in name or "quần bò" in name:
        p_type = "Quần Dài & Jeans"
    elif any("váy" in c or "đầm" in c or "vay" in c or "dam" in c for c in cat_names) or "vay" in url_key or "dam" in url_key or "váy" in name or "đầm" in name:
        p_type = "Váy Đầm"
    elif any("bộ mặc nhà" in c or "đồ mặc nhà" in c or "do-mac-nha" in c or "pyjama" in c for c in cat_names) or "do-mac-nha" in url_key or "mặc nhà" in name or "pyjama" in name:
        p_type = "Đồ Mặc Nhà"
    elif any("đồ lót" in c or "quan-lot" in c or "do-lot" in c for c in cat_names) or "do-lot" in url_key or "đồ lót" in name or "quần lót" in name:
        p_type = "Đồ Lót"
    elif any("tất" in c or "vớ" in c or "tat" in c for c in cat_names) or "tat-vo" in url_key or "tất" in name or "vớ" in name:
        p_type = "Tất Vớ"
    elif any("phụ kiện" in c or "phu-kien" in c or "chăn" in c or "khăn" in c or "mũ" in c or "túi" in c for c in cat_names) or "phu-kien" in url_key or "phụ kiện" in name:
        p_type = "Phụ Kiện"
        
    if gender != "General" and p_type != "General":
        return f"{p_type} {gender}"
    elif gender != "General":
        return gender
    elif p_type != "General":
        return p_type
    else:
        return "General"

def main():
    print("=" * 60)
    print("[CANIFA] DISCOVERY SCRAPER STARTING (WITH FILTERS)")
    print("=" * 60)
    
    results = {}
    print("[*] Rebuilding discovery scraped_products.json with filtered products only...")

    offset = 0
    size = 100
    total_discovered = 0
    all_seen_urls = set()
    
    while True:
        data = fetch_products(offset, size)
        if not data or "hits" not in data or "hits" not in data["hits"]:
            print(f"[!] No response or empty data at offset {offset}")
            break
            
        hits_obj = data["hits"]
        total_count = hits_obj.get("total", {}).get("value", 0)
        products = hits_obj.get("hits", [])
        
        if not products:
            print(f"[*] No more products found at offset {offset}")
            break
            
        print(f"  - Offset {offset}: Found {len(products)} products (Total in store: {total_count})")
        
        for p_hit in products:
            p = p_hit.get("_source")
            if not p:
                continue
                
            # Filter out kids' products and underwear (except swimwear and socks)
            if should_skip_product(p):
                continue
                
            url_key = p.get("url_key")
            if not url_key:
                continue
                
            product_url = f"https://canifa.com/{url_key}"
            category_group = classify_product(p)
            
            if category_group not in results:
                results[category_group] = []
                
            if product_url not in all_seen_urls:
                results[category_group].append(product_url)
                all_seen_urls.add(product_url)
                total_discovered += 1
                
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        if len(products) < size:
            break
            
        offset += size
        time.sleep(0.5)
        
    print("\n" + "="*50)
    print("🏆 CANIFA DISCOVERY COMPLETED!")
    print(f"Total unique products found in this run: {total_discovered}")
    print(f"Total accumulated products: {len(all_seen_urls)}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
