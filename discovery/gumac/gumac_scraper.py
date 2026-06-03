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

CATEGORIES = {
    # Main GUMAC Subcategories (Prioritizing subcategories over roots)
    "Váy Đầm Công Sở": "vay-dam-cong-so",
    "Váy Đầm Form A": "vay-dam-form-a",
    "Váy Đầm Sơ Mi": "vay-dam-so-mi",
    "Váy Đầm Xòe": "vay-dam-xoe",
    "Váy Đầm Xếp Ly": "dam-xep-ly",
    "Váy Đầm Dự Tiệc": "vay-dam-du-tiec",
    "Áo Thun Nữ Cổ Tròn": "ao-thun-nu-co-tron",
    "Áo Thun Nữ Polo": "ao-thun-nu-polo",
    "Áo Sơ Mi Tay Dài": "ao-so-mi-nu-tay-dai",
    "Áo Sơ Mi Tay Ngắn": "ao-so-mi-nu-tay-ngan",
    "Áo Sơ Mi Họa Tiết": "ao-so-mi-nu-hoa-tiet",
    "Áo Sơ Mi Kiểu": "ao-so-mi-nu-kieu",
    "Quần Tây Ống Suông": "quan-tay-nu-ong-suong",
    "Quần Tây Ống Rộng": "quan-tay-nu-ong-rong",
    "Quần Tây Ống Đứng": "quan-tay-nu-ong-dung",
    "Quần Jeans": "quan-dai-jean",
    "Chân Váy Bút Chì": "chan-vay-but-chi",
    "Chân Váy Xòe": "chan-vay-xoe",
    "Chân Váy Xếp Ly": "chan-vay-xep-ly",
    "Chân Váy Chữ A": "chan-vay-chu-a",
    
    # Standalone Main Categories
    "Áo Dài": "ao-dai",
    "Áo Khoác": "ao-khoac-nu",
    "Áo Blazer & Vest": "ao-vest",
    "Áo Kiểu": "ao-kieu",
    "Quần Short": "quan-short",
    "Áo Len": "ao-len",
    "Giày Dép Nữ": "giay-dep-nu",
    "Phụ Kiện Nữ": "phu-kien-nu",
    
    # Men's Clothing (Subcategories only, parent "Sản Phẩm Đồ Nam" excluded)
    "Áo Sơ Mi Nam": "ao-so-mi-nam",
    "Áo Thun Nam": "ao-thun-nam",
    "Quần Short Nam": "quan-short-nam",

    # Kids Clothing
    "Sản Phẩm Trẻ Em": "san-pham-tre-em",

    # GMORNING Line (Subcategories only, parent "Gmorning" excluded)
    "Váy Đầm Gmorning": "vay-dam-gmorning",
    "Áo Thun Gmorning": "ao-thun-gmorning",
    "Quần Dài Gmorning": "quan-dai-gmorning",
    "Áo Sơ Mi Gmorning": "ao-so-mi-gmorning",
    "Chân Váy Gmorning": "chan-vay-gmorning",
    "Áo Khoác Gmorning": "ao-khoac-gmorning",
    "Quần Short Gmorning": "quan-short-gmorning",

    # ALEEVA Line (Subcategories only, parent "Aleeva" excluded)
    "Váy Đầm Aleeva": "vay-dam-aleeva",
    "Quần Dài Aleeva": "quan-dai-aleeva",
    "Chân Váy Aleeva": "chan-vay-aleeva",
    "Quần Short Aleeva": "quan-short-aleeva",
    "Áo Sơ Mi Aleeva": "ao-so-mi-aleeva",
    "Áo Kiểu Aleeva": "ao-kieu-aleeva",
    "Áo Khoác Aleeva": "ao-khoac-aleeva",

    # GMC Online Exclusive Line (Subcategories only, parent "GMC" excluded)
    "Váy Đầm Độc Quyền Online": "vay-dam-doc-quyen-online",
    "Chân Váy Độc Quyền Online": "chan-vay-doc-quyen-online",
    "Áo Thun Độc Quyền Online": "ao-thun-doc-quyen-online",
    "Quần Dài Độc Quyền Online": "quan-dai-doc-quyen-online",
    "Quần Jeans Độc Quyền Online": "quan-jeans-doc-quyen-online",
    "Quần Short Độc Quyền Online": "quan-short-doc-quyen-online",
    "Áo Sơ Mi Độc Quyền Online": "ao-so-mi-doc-quyen-online",

    # Standalone Others
    "Đồ ngủ & Mặc nhà": "do-ngu-mac-nha"
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"[!] Error fetching {url}: {e}. Retrying ({attempt+1}/3)...")
            time.sleep(2)
    return None

def main():
    print("=" * 60)
    print("[GUMAC] DISCOVERY SCRAPER STARTING")
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

    for cat_name, cat_slug in CATEGORIES.items():
        print(f"\n🚀 Scanning Category: {cat_name} ({cat_slug})")
        product_urls = set()
        page = 1
        limit = 40
        
        while True:
            url = f"https://cms.gumac.vn/api/v1/products?page={page}&limit={limit}&category={cat_slug}"
            data = fetch_json(url)
            if not data or "data" not in data or len(data["data"]) == 0:
                print(f"[*] No more products for {cat_name} at page {page}")
                break
                
            products = data["data"]
            for p in products:
                slug = p.get("slug")
                # Get category slug of the product itself or fall back to main category slug
                p_cat_slug = p.get("category", {}).get("slug", cat_slug)
                if slug and p_cat_slug:
                    product_url = f"https://gumac.vn/{p_cat_slug}/{slug}"
                    product_urls.add(product_url)
            
            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            print(f"  - Page {page}/{total_pages}: Found {len(products)} products (Total accumulated: {len(product_urls)})")
            
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5) # Politeness delay
            
        results[cat_name] = list(product_urls)
        
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved category '{cat_name}' products to: {OUTPUT_JSON_PATH}")

    total_all = sum(len(v) for v in results.values())
    print("\n" + "="*50)
    print("🏆 GUMAC DISCOVERY COMPLETED!")
    print(f"Total products discovered: {total_all}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
