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
        
    # 3. Check Towels (khăn mặt, khăn tắm) to skip
    is_towel = False
    if any(x in name for x in ["khăn mặt", "khăn tắm", "khăn lau", "tắm", "khăn bông"]):
        if not any(y in name for y in ["quàng", "choàng", "cổ"]):
            is_towel = True
    if any(x in url_key for x in ["khan-mat", "khan-tam", "khan-lau", "khan-bong"]):
        if not any(y in url_key for y in ["quang", "choang", "co"]):
            is_towel = True
    if any("khăn tắm" in c or "khăn mặt" in c for c in cat_names):
        is_towel = True
        
    if is_towel:
        return True
        
    return False

def classify_product(p):
    categories = p.get("categories_map") or []
    cat_names = [c.get("name", "").lower() for c in categories if isinstance(c, dict)]
    sku = (p.get("sku") or "").lower()
    url_key = (p.get("url_key") or "").lower()
    name = (p.get("name") or "").lower()
    
    # 1. Determine Gender: Nam, Nữ, Unisex
    def clean_and_tokenize(text):
        if not text:
            return []
        t = text.lower()
        t = t.replace("việt nam", " ").replace("viet nam", " ").replace("vietnam", " ")
        cleaned = "".join([c if (c.isalnum() or c.isspace()) else " " for c in t])
        return cleaned.split()

    all_tokens = set()
    for c in cat_names:
        all_tokens.update(clean_and_tokenize(c))
    all_tokens.update(clean_and_tokenize(url_key))
    all_tokens.update(clean_and_tokenize(name))
    
    is_unisex = "unisex" in url_key or "unisex" in name or any("unisex" in c for c in cat_names)
    
    if is_unisex:
        gender = "Unisex"
    else:
        has_men = ("nam" in all_tokens) or ("men" in all_tokens)
        has_women = ("nữ" in all_tokens) or ("nu" in all_tokens) or ("women" in all_tokens)
        
        if has_men and has_women:
            gender = "Unisex"
        elif has_men:
            gender = "Nam"
        elif has_women:
            gender = "Nữ"
        else:
            gender = "Unisex"
        
    # 2. Determine Product Type
    p_type = "General"
    
    # Check towels first just in case they slipped through
    if any(x in name or x in url_key for x in ["khăn mặt", "khăn tắm", "khan-mat", "khan-tam"]):
        if not any(y in name or y in url_key for y in ["quàng", "choàng", "co", "quang"]):
            return "General"
            
    text_to_check = f"{name} {url_key} " + " ".join(cat_names)
    
    # CLOTHES Evaluation First
    # Tất Vớ
    if any(w in all_tokens for w in ["tất", "vớ", "tat", "vo"]):
        p_type = "Tất Vớ"
    # Đồ Mặc Nhà
    elif any(phrase in text_to_check for phrase in ["mặc nhà", "mac-nha", "pyjama", "pijama"]):
        p_type = "Đồ Mặc Nhà"
    # Váy Đầm
    elif any(phrase in text_to_check for phrase in ["chân váy", "chan-vay", "váy liền", "vay-lien"]) or any(w in all_tokens for w in ["váy", "đầm", "vay", "dam"]):
        p_type = "Váy Đầm"
    # Chống Nắng
    elif any(phrase in text_to_check for phrase in ["chống nắng", "chong-nang"]):
        p_type = "Chống Nắng"
    # Đồ Nỉ
    elif any(w in all_tokens for w in ["nỉ", "ni", "hoodie", "sweater", "sweatshirt"]) or "ao-ni" in url_key or "quan-ni" in url_key:
        p_type = "Đồ Nỉ"
    # Áo Polo
    elif "polo" in text_to_check:
        p_type = "Áo Polo"
    # Áo Sơ Mi
    elif any(phrase in text_to_check for phrase in ["sơ mi", "so-mi", "somi"]):
        p_type = "Áo Sơ Mi"
    # Áo Len
    elif any(phrase in text_to_check for phrase in ["áo len", "ao-len"]) or "len" in all_tokens:
        p_type = "Áo Len"
    # Áo Thun
    elif any(phrase in text_to_check for phrase in ["áo phông", "ao-phong", "áo thun", "ao-thun", "t-shirt", "tshirt", "ao phong", "ao thun"]):
        p_type = "Áo Thun"
    # Quần Shorts
    elif any(phrase in text_to_check for phrase in ["quần shorts", "quan-shorts", "quan-sooc", "quần soóc", "quần sooc"]) or any(w in all_tokens for w in ["short", "shorts", "sooc", "soóc"]):
        p_type = "Quần Shorts"
    # Quần Dài & Jeans
    elif any(phrase in text_to_check for phrase in ["quần dài", "quan-dai", "quan-jeans", "quần jeans", "quần bò", "quan-vai", "quần tây", "quần vải"]) or any(w in all_tokens for w in ["jeans", "jean", "khaki", "kaki"]):
        p_type = "Quần Dài & Jeans"
    # General Áo
    elif "áo" in all_tokens or "ao" in all_tokens or "ao-" in url_key:
        p_type = "Áo"
    # General Quần
    elif "quần" in all_tokens or "quan" in all_tokens or "quan-" in url_key:
        p_type = "Quần"
        
    # ACCESSORIES Evaluation Second (Only if still General)
    if p_type == "General":
        if any(phrase in text_to_check for phrase in ["khẩu trang", "khau-trang"]):
            p_type = "Khẩu Trang"
        elif any(phrase in text_to_check for phrase in ["khăn quàng", "khăn choàng", "khan-quang", "khan-choang"]):
            p_type = "Khăn Quàng Cổ"
        elif any(phrase in text_to_check for phrase in ["mũ", "nón", "cap", "hat"]) or "mu-" in url_key or "no-" in url_key or any(w in all_tokens for w in ["mũ", "nón"]):
            p_type = "Mũ"
        elif any(phrase in text_to_check for phrase in ["túi", "balo", "ba lô", "bag", "tote", "backpack"]):
            p_type = "Túi Xách"
            
    # Fallback if still General
    if p_type == "General":
        p_type = "Phụ Kiện"
            
    return f"{p_type} {gender}"


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
                
        # Save sorted incrementally
        type_order = [
            "Áo Thun", "Áo Polo", "Áo Sơ Mi", "Áo Len", "Đồ Nỉ", 
            "Chống Nắng", "Áo Khoác", "Áo", 
            "Quần Shorts", "Quần Dài & Jeans", "Váy Đầm", "Quần", 
            "Đồ Mặc Nhà", "Tất Vớ", 
            "Khẩu Trang", "Khăn Quàng Cổ", "Mũ", "Túi Xách", 
            "Phụ Kiện", "General"
        ]
        type_weights = {name: idx for idx, name in enumerate(type_order)}

        def get_sort_key(k):
            gender = "Unisex"
            p_type = k
            for g in ["Nam", "Nữ", "Unisex"]:
                if k.endswith(g):
                    gender = g
                    p_type = k[:-len(g)].strip()
                    break
            gender_weight = {"Nam": 1, "Nữ": 2, "Unisex": 3}.get(gender, 4)
            type_weight = type_weights.get(p_type, 99)
            return (gender_weight, type_weight, k)

        sorted_results = {k: results[k] for k in sorted(results.keys(), key=get_sort_key)}
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted_results, f, ensure_ascii=False, indent=2)
            
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
