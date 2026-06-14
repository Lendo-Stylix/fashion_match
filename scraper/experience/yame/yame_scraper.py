import os
import json
import sys
import re
import urllib.request
import ssl
import time

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://yame.vn"

# SSL Context to bypass certification issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*"
}

def is_kid(title, tags):
    title_l = title.lower()
    tags_l = tags.lower()
    
    # Exceptions
    if "baby tee" in title_l or "baby-tee" in title_l:
        return False
    if "baby pink" in title_l or "baby blue" in title_l:
        return False
        
    kid_kws = ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé"]
    if any(kw in title_l for kw in kid_kws):
        return True
    if any(kw in tags_l for kw in kid_kws):
        return True
        
    en_kid_kws = [r'\bkids\b', r'\bboy\b', r'\bgirl\b', r'\bchild\b', r'\bchildren\b']
    if any(re.search(kw, title_l) for kw in en_kid_kws):
        return True
    if any(re.search(kw, tags_l) for kw in en_kid_kws):
        return True
    return False

def is_underwear(title, tags, product_type):
    title_l = title.lower()
    tags_l = tags.lower()
    type_l = product_type.lower()
    
    # Exceptions: Keep swimwear (đồ bơi) and socks/stockings (tất, vớ)
    if any(kw in title_l or kw in tags_l for kw in ["bơi", "swim", "tất", "vớ", "socks"]):
        return False
        
    under_kws = ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "boxer", "panties"]
    if any(kw in title_l for kw in under_kws):
        return True
    if any(kw in tags_l for kw in under_kws):
        return True
        
    en_under_kws = [r'\bbra\b', r'\bunderwear\b', r'\binnerwear\b']
    if any(re.search(kw, title_l) for kw in en_under_kws):
        return True
    if any(re.search(kw, tags_l) for kw in en_under_kws):
        return True
        
    if type_l == "innerwear":
        return True
    return False

def is_footwear(title, tags, product_type):
    title_l = title.lower()
    tags_l = tags.lower()
    type_l = product_type.lower()
    
    if type_l in ["slides", "footwear"]:
        return True
        
    foot_kws = ["giày", "dép", "sandal", "sneaker", "guốc", "derby", "giày dép", "lót giày"]
    if any(kw in title_l for kw in foot_kws):
        return True
    if any(kw in tags_l for kw in foot_kws):
        return True
        
    en_foot_kws = [r'\bboots\b', r'\bloafer\b', r'\bslippers\b', r'\bslides\b']
    if any(re.search(kw, title_l) for kw in en_foot_kws):
        return True
    if any(re.search(kw, tags_l) for kw in en_foot_kws):
        return True
    return False

def is_cosmetic(title, tags, product_type):
    title_l = title.lower()
    tags_l = tags.lower()
    
    cosm_kws = ["mỹ phẩm", "trang điểm", "son môi", "dưỡng da", "sữa tắm", "dầu gội", "nước hoa"]
    if any(kw in title_l for kw in cosm_kws):
        return True
    if any(kw in tags_l for kw in cosm_kws):
        return True
        
    en_cosm_kws = [r'\bmakeup\b', r'\bcosmetics\b']
    if any(re.search(kw, title_l) for kw in en_cosm_kws):
        return True
    if any(re.search(kw, tags_l) for kw in en_cosm_kws):
        return True
    return False

def classify_product(p):
    p_type = (p.get("product_type") or "").upper()
    title = p.get("title", "")
    title_l = title.lower()
    
    # Map types to project standard categories
    if "áo thun cổ polo" in title_l or "polo" in title_l or p_type == "ÁO THUN CỔ POLO TAY NGẮN":
        return "Áo Polo"
    elif "áo thun" in title_l or p_type in ["ÁO THUN CỔ TRÒN TAY NGẮN", "ÁO THUN 3 LỖ"]:
        return "Áo Thun"
    elif "sơ mi" in title_l or "sơmi" in title_l or "shirt" in title_l or "shirting" in title_l or p_type in ["ÁO SƠ MI TAY NGẮN", "ÁO SƠ MI TAY DÀI", "ÁO SƠ MI KHOÁC"]:
        return "Áo Sơ Mi"
    elif "hoodie" in title_l or "sweater" in title_l or "len" in title_l or "nỉ" in title_l or p_type in ["ÁO HOODIE", "ÁO SWEATER", "ÁO LEN"]:
        return "Áo Hoodie & Nỉ & Len"
    elif "áo khoác" in title_l or "blazer" in title_l or "gile" in title_l or "bomber" in title_l or "jacket" in title_l or p_type in ["ÁO KHOÁC", "ÁO KHOÁC BLAZER", "ÁO KHOÁC GILE", "ÁO KHOÁC BOMBER", "ÁO KHOÁC KAKI"]:
        return "Áo Khoác"
    elif "quần đùi" in title_l or "quần short" in title_l or "short" in title_l or "quần lửng" in title_l or "short" in p_type.lower():
        return "Quần Shorts"
    elif "quần dài" in title_l or "quần jeans" in title_l or "quần tây" in title_l or "jogger" in title_l or "jean" in title_l or "kaki" in title_l or "quần dù" in title_l or "jean" in p_type.lower() or "jogger" in p_type.lower() or "kaki" in p_type.lower():
        return "Quần Dài"
    elif "balo" in title_l or "túi" in title_l or "messenger" in title_l or "backpack" in title_l or "ví" in title_l or "cardholder" in title_l or "túi" in p_type.lower() or "ví" in p_type.lower() or "balo" in p_type.lower():
        return "Balo & Túi"
    elif "nón" in title_l or "dây nịt" in title_l or "thắt lưng" in title_l or "vớ" in title_l or "tất" in title_l or "socks" in title_l or "khăn" in title_l or "băng" in title_l or p_type in ["PHỤ KIỆN", "VỚ CÔNG THÁI HỌC", "NÓN FITTED CAP", "DÂY NỊT DA BÒ Ý", "DÂY NỊT DA TRÂU"]:
        return "Phụ Kiện"
    else:
        return "Khác"

def fetch_products_page(page, limit=250):
    url = f"{SITE_BASE}/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8')).get("products", [])
        except Exception as e:
            print(f"[!] Error fetching page {page}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def main():
    print("=" * 60)
    print("🏆 YAME DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    total_discovered = 0
    seen_urls = set()
    
    page = 1
    limit = 250
    
    while True:
        print(f"[*] Fetching page {page}...")
        products = fetch_products_page(page, limit)
        if not products:
            print(f"[*] No more products returned at page {page}. Stopping.")
            break
            
        print(f"  - Page {page}: Received {len(products)} products")
        
        page_added = 0
        for p in products:
            title = p.get("title", "")
            tags = p.get("tags") or []
            if isinstance(tags, list):
                tags_str = ", ".join(tags)
            else:
                tags_str = str(tags)
                
            p_type = p.get("product_type") or ""
            handle = p.get("handle", "")
            
            if not handle:
                continue
                
            p_url = f"{SITE_BASE}/products/{handle}"
            
            # Apply filters
            if is_kid(title, tags_str):
                continue
            if is_underwear(title, tags_str, p_type):
                continue
            if is_footwear(title, tags_str, p_type):
                continue
            if is_cosmetic(title, tags_str, p_type):
                continue
                
            category = classify_product(p)
            if category not in results:
                results[category] = []
                
            if p_url not in seen_urls:
                results[category].append(p_url)
                seen_urls.add(p_url)
                page_added += 1
                total_discovered += 1
                
        print(f"  - Page {page}: Added {page_added} new unique URLs.")
        
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        if len(products) < limit:
            print(f"[*] Less than limit ({limit}) products returned on page {page}. Crawl complete.")
            break
            
        page += 1
        time.sleep(0.5)
        
    print("\n" + "="*50)
    print("🏆 YAME DISCOVERY COMPLETED!")
    print(f"Total unique product URLs discovered: {total_discovered}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
