import json
import os
import sys
import urllib.request
import ssl
import time
import re
import math

# Ensure UTF-8 output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_JSON_PATH = os.path.join(OUTPUT_DIR, "scraped_products.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# SSL context to bypass validation errors
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/html, */*'
}

def fetch_url(url, is_json=False):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                content = response.read().decode('utf-8')
                if is_json:
                    return json.loads(content)
                return content
        except Exception as e:
            print(f"[!] Error fetching {url}: {e}. Retrying ({attempt+1}/5)...")
            time.sleep(2 * (attempt + 1))
    return None

def extract_js_var(html, var_name, end_var_name=None):
    # Regex to find self.var_name = ...
    if end_var_name:
        pattern = rf'self\.{var_name}\s*=\s*(.*?)\s*;?\s*self\.{end_var_name}\s*='
    else:
        pattern = rf'self\.{var_name}\s*=\s*"(.*?)"\s*;?\s*(?:self\.|$)'
        
    match = re.search(pattern, html, re.DOTALL)
    if match:
        val_str = match.group(1).strip()
        if val_str.endswith(';'):
            val_str = val_str[:-1].strip()
        return val_str
    return None

def should_skip_category(name, slug):
    name_l = name.lower()
    slug_l = slug.lower()
    
    # 1. Check Kids (Bé trai, Bé gái, Trẻ em, sơ sinh)
    if any(x in name_l for x in ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé"]):
        return True
    if any(x in slug_l for x in ["be-trai", "be-gai", "tre-em", "so-sinh", "boy", "girl"]):
        return True
        
    # 2. Check Underwear (Đồ lót)
    is_underwear = False
    if any(x in name_l for x in ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer"]):
        is_underwear = True
    if any(x in slug_l for x in ["do-lot", "quan-lot", "ao-lot", "sip", "sịp", "boxer", "panties", "bra"]):
        is_underwear = True
        
    # Exceptions to Keep: Đồ bơi (swimwear), Tất, Vớ (socks)
    is_swimwear = "bơi" in name_l or "swim" in name_l or "bơi" in slug_l or "swim" in slug_l
    is_socks = "tất" in name_l or "vớ" in name_l or "tat" in slug_l or "vo" in slug_l
    
    if is_underwear and not (is_swimwear or is_socks):
        return True

    # 3. Check Shoes & Sandals (Giày dép)
    if any(x in name_l for x in ["giày", "dép", "sandal", "sneaker", "guốc", "derby"]):
        return True
    if any(x in slug_l for x in ["giay", "dep", "sandal", "sneaker", "guoc", "derby"]):
        return True

    # 4. Check Cosmetics & Beauty (Mỹ phẩm)
    if any(x in name_l for x in ["mỹ phẩm", "son môi", "kem dưỡng", "sữa tắm", "dầu gội"]):
        return True
    if any(x in slug_l for x in ["my-pham", "son-moi", "kem-duong", "sua-tam", "dau-goi"]):
        return True
        
    return False

def get_leaf_categories():
    print("[*] Fetching category tree dynamically from Yody...")
    # Fetch a representative category page to parse self.categories
    sample_html = fetch_url("https://yody.vn/category/ao-polo-nam")
    if not sample_html:
        print("[!] Failed to fetch sample category page.")
        return []
        
    cat_tree_str = extract_js_var(sample_html, "categories", "currentCategory")
    if not cat_tree_str:
        print("[!] Failed to extract self.categories JS variable.")
        return []
        
    try:
        categories = json.loads(cat_tree_str)
    except Exception as e:
        print(f"[!] Failed to parse categories JSON: {e}")
        return []
        
    leaf_categories = []
    
    def traverse(cat, parent_path=""):
        name = cat.get("name", "")
        slug = cat.get("slug", "")
        cat_id = cat.get("id")
        
        if should_skip_category(name, slug):
            return
            
        current_path = f"{parent_path} > {name}" if parent_path else name
        children = cat.get("children")
        
        if children:
            for child in children:
                traverse(child, current_path)
        else:
            leaf_categories.append({
                "id": cat_id,
                "name": name,
                "slug": slug,
                "path": current_path
            })
            
    # Traverse only Root Nam (id: 93) and Root Nữ (id: 94)
    for root in categories:
        if root.get("id") in [93, 94]:
            traverse(root)
            
    return leaf_categories

def main():
    print("=" * 60)
    print("🏆 YODY DISCOVERY SCRAPER STARTING")
    print("=" * 60)
    
    results = {}
    seen_urls = set()
    
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
            for cat_name, urls in results.items():
                for u in urls:
                    seen_urls.add(u)
            print(f"[*] Loaded existing output file with {len(results)} categories and {len(seen_urls)} unique products.")
        except Exception as e:
            print(f"[!] Error loading existing output file: {e}. Starting fresh.")
            
    leaf_categories = get_leaf_categories()
    if not leaf_categories:
        print("[!] No leaf categories found. Exiting.")
        return
        
    print(f"[*] Found {len(leaf_categories)} leaf categories to process.")
    
    for idx, cat in enumerate(leaf_categories):
        cat_name = cat["name"]
        cat_slug = cat["slug"]
        cat_path = cat["path"]
        
        print(f"\n[{idx+1}/{len(leaf_categories)}] Processing Category: {cat_name} ({cat_path})")
        
        # If already scraped in this run (resume capability)
        if cat_name in results and results[cat_name]:
            print(f"  -> Skipping category (already contains {len(results[cat_name])} URLs).")
            continue
            
        results[cat_name] = []
        
        # Fetch the category HTML page to get page 1 products and metadata
        cat_url = f"https://yody.vn/category/{cat_slug}"
        print(f"  - Fetching page 1: {cat_url}")
        html = fetch_url(cat_url)
        if not html:
            print(f"  [!] Failed to load HTML for {cat_url}")
            continue
            
        # Extract self.products
        products_str = extract_js_var(html, "products", "metadata")
        if not products_str:
            print(f"  [!] No self.products found in HTML for category {cat_slug}.")
            continue
            
        # Extract self.metadata
        metadata_str = extract_js_var(html, "metadata", "filter")
        if not metadata_str:
            print(f"  [!] No self.metadata found in HTML for category {cat_slug}.")
            continue
            
        try:
            products_p1 = json.loads(products_str)
            metadata = json.loads(metadata_str)
        except Exception as e:
            print(f"  [!] Error parsing JSON variables: {e}")
            continue
            
        # Get category ID dynamically (from HTML)
        current_cat_str = extract_js_var(html, "currentCategory", "/script")
        # Wait, self.currentCategory is the last assignment, it ends before </script>
        if not current_cat_str:
            current_cat_str = extract_js_var(html, "currentCategory")
            
        cat_id = None
        if current_cat_str:
            try:
                # Strip trailing javascript blocks if any
                if "</script>" in current_cat_str:
                    current_cat_str = current_cat_str.split("</script>")[0].strip()
                if current_cat_str.endswith(';'):
                    current_cat_str = current_cat_str[:-1].strip()
                curr_cat = json.loads(current_cat_str)
                cat_id = curr_cat.get("id")
            except Exception as e:
                print(f"  [!] Error parsing currentCategory JSON: {e}")
                
        if not cat_id:
            cat_id = cat["id"] # Fallback to tree ID
            
        total = metadata.get("total", 0)
        limit = metadata.get("limit", 24)
        print(f"  - Category ID: {cat_id} | Total Products: {total} | Page Limit: {limit}")
        
        # Process Page 1 Products
        page1_added = 0
        for p in products_p1:
            slug = p.get("select_variant", {}).get("slug")
            if slug:
                clean_slug = slug.split("?")[0]
                p_url = f"https://yody.vn/product/{clean_slug}"
                if p_url not in seen_urls:
                    results[cat_name].append(p_url)
                    seen_urls.add(p_url)
                    page1_added += 1
                    
        print(f"  - Page 1: Processed {len(products_p1)} products, added {page1_added} unique URLs.")
        
        # Process Page 2+ if total > limit
        if total > limit:
            total_pages = math.ceil(total / limit)
            print(f"  - Category requires pagination. Total pages: {total_pages}")
            for page in range(2, total_pages + 1):
                api_url = f"https://yody.vn/api/products?category_id={cat_id}&limit={limit}&page={page}&product_sort_by=created_at&product_sort_direction=desc"
                print(f"    - Fetching Page {page}: {api_url}")
                
                # Fetch page data
                api_data = fetch_url(api_url, is_json=True)
                if not api_data or "items" not in api_data:
                    print(f"    [!] Failed to fetch page {page} API.")
                    continue
                    
                items = api_data.get("items", [])
                page_added = 0
                for p in items:
                    slug = p.get("select_variant", {}).get("slug")
                    if slug:
                        clean_slug = slug.split("?")[0]
                        p_url = f"https://yody.vn/product/{clean_slug}"
                        if p_url not in seen_urls:
                            results[cat_name].append(p_url)
                            seen_urls.add(p_url)
                            page_added += 1
                            
                print(f"    - Page {page}: Processed {len(items)} products, added {page_added} unique URLs.")
                time.sleep(1.0)
                
        # Save incrementally
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"  - Category {cat_name} completed. Cumulative unique URLs: {len(results[cat_name])}")
        time.sleep(1.0)
        
    print("\n" + "="*50)
    print("🏆 YODY DISCOVERY COMPLETED!")
    print(f"Total categories scraped: {len(results)}")
    print(f"Total unique product URLs discovered: {len(seen_urls)}")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
