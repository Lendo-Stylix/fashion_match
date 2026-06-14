"""
H&M Vietnam Product Scraper
==========================
Platform: Next.js (SSR)
Anti-Bot: Akamai (Bypassed via Playwright CDP)
Discovery: Crawls master Men & Women category list pages page-by-page.
Harvest: Groups product codes by Style ID, fetches PDP Next JSON state,
         and queries global availability API VN gateway inside the page.

Output: harvest/hm/output/hm_products_full.json
"""

import os
import json
import sys
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "../../harvest/hm/output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "hm_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CATEGORIES = [
    {"name": "Nam", "url": "https://www2.hm.com/vi_vn/nam/san-pham/xem-tat-ca.html", "parent": "Nam"},
    {"name": "Nữ", "url": "https://www2.hm.com/vi_vn/nu/goi-y-san-pham/xem-tat-ca.html", "parent": "Nữ"}
]

EXCLUDE_KEYWORDS = [
    "bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "infant", "toddler",
    "giày", "dép", "sandal", "sneaker", "guốc", "derby", "shoes", "slides", "boots", "loafer",
    "đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "boxer", "panties", "bra", "underwear",
    "mỹ phẩm", "trang điểm", "makeup", "cosmetics", "dưỡng da", "son môi", "nước hoa"
]

def should_exclude(title: str, category_key: str = "") -> bool:
    t_clean = title.lower()
    cat_clean = category_key.lower() if category_key else ""
    
    # Exception: Keep Swimwear and Socks
    is_swim_or_socks = any(kw in t_clean or kw in cat_clean for kw in ["bơi", "swim", "tất", "vớ", "socks"])
    
    # Always exclude kids/baby even if swimwear or socks
    is_kids = any(kw in t_clean or kw in cat_clean for kw in ["bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "infant", "toddler"])
    if is_kids:
        return True
        
    if is_swim_or_socks:
        return False
        
    # Check general exclusion list
    return any(kw in t_clean or kw in cat_clean for kw in EXCLUDE_KEYWORDS)

def map_product_type(category_key: str, title: str, parent: str) -> str:
    t_clean = title.lower()
    cat_clean = category_key.lower() if category_key else ""
    
    p_type = "General"
    if "tshirt" in cat_clean or "ao-thun" in cat_clean or "áo thun" in t_clean or "áo phông" in t_clean:
        p_type = "Áo Thun"
    elif "polo" in cat_clean or "polo" in t_clean:
        p_type = "Áo Polo"
    elif "shirt" in cat_clean or "sơ mi" in t_clean:
        p_type = "Áo Sơ Mi"
    elif "sweatshirt" in cat_clean or "hoodie" in cat_clean or "len" in t_clean or "cardigan" in t_clean:
        p_type = "Áo Hoodie & Nỉ & Len"
    elif "jacket" in cat_clean or "coat" in cat_clean or "áo khoác" in t_clean or "blazer" in t_clean:
        p_type = "Áo Khoác"
    elif "short" in cat_clean or "quần short" in t_clean or "quần đùi" in t_clean:
        p_type = "Quần Shorts"
    elif "jeans" in cat_clean or "denim" in cat_clean or "quần jean" in t_clean:
        p_type = "Quần Jeans"
    elif "trouser" in cat_clean or "pant" in cat_clean or "quần dài" in t_clean or "quần tây" in t_clean or "khaki" in t_clean:
        p_type = "Quần Dài"
    elif "skirt" in cat_clean or "váy" in t_clean:
        p_type = "Chân Váy"
    elif "dress" in cat_clean or "đầm" in t_clean:
        p_type = "Váy Đầm"
    elif "swim" in cat_clean or "bơi" in t_clean:
        p_type = "Đồ Bơi"
    elif "socks" in cat_clean or "tất" in t_clean or "vớ" in t_clean:
        p_type = "Tất Vớ"
        
    return f"{p_type} {parent}"

async def main():
    print("=" * 65)
    print("  🚀 H&M VIETNAM CATALOG SCRAPER")
    print("=" * 65)
    
    async with async_playwright() as p:
        print("\nConnecting to Chrome via CDP...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        # 1. DISCOVERY PHASE
        print("\n--- PHASE 1: DISCOVERY ---")
        discovered_styles = {} # style_id (7 digits) -> dict info
        
        for cat in CATEGORIES:
            cat_name = cat["name"]
            base_url = cat["url"]
            parent = cat["parent"]
            
            print(f"\n[*] Crawling category [{cat_name}]...")
            page_num = 1
            
            while True:
                url = f"{base_url}?page={page_num}"
                print(f"  Page {page_num}: Navigating to {url}...")
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2500)
                    
                    next_data_str = await page.evaluate("() => document.getElementById('__NEXT_DATA__').textContent")
                    if not next_data_str:
                        print("    [!] Error: No __NEXT_DATA__ block found. Retrying page...")
                        await page.wait_for_timeout(2000)
                        continue
                        
                    data = json.loads(next_data_str)
                    page_props = data.get("props", {}).get("pageProps", {})
                    plp_props = page_props.get("plpProps", {})
                    
                    if not isinstance(plp_props, dict):
                        print("    [!] No PLP Props in JSON. Ending pagination.")
                        break
                        
                    listing_section = plp_props.get("productListingSectionProps", {})
                    listing_data = listing_section.get("productListingData", {})
                    hits = listing_data.get("hits", [])
                    pagination = listing_data.get("pagination", {})
                    
                    if not hits:
                        print("    [*] No products found on this page. Ending category.")
                        break
                        
                    print(f"    - Found {len(hits)} hits on this page.")
                    
                    new_styles = 0
                    for hit in hits:
                        title = hit.get("title", "")
                        category_key = hit.get("category", "")
                        
                        if should_exclude(title, category_key):
                            continue
                            
                        article_code = hit.get("articleCode")
                        if not article_code:
                            continue
                            
                        style_id = article_code[:7]
                        pdp_path = hit.get("pdpUrl")
                        if not pdp_path:
                            continue
                            
                        pdp_url = "https://www2.hm.com" + pdp_path if pdp_path.startswith("/") else pdp_path
                        
                        # Store first active variant of this style
                        if style_id not in discovered_styles:
                            discovered_styles[style_id] = {
                                "article_code": article_code,
                                "pdp_url": pdp_url,
                                "title": title,
                                "category": category_key,
                                "parent_category": parent
                            }
                            new_styles += 1
                            
                    print(f"    - Discovered {new_styles} new style IDs.")
                    
                    total_pages = pagination.get("totalPages", 1)
                    if page_num >= total_pages:
                        print(f"    [*] Reached last page ({total_pages}). Category complete.")
                        break
                        
                    page_num += 1
                    
                except Exception as e:
                    print(f"    [!] Error on Page {page_num}: {e}. Skipping category.")
                    break
                    
        print(f"\n🏆 Discovery complete! Found {len(discovered_styles)} unique product styles.")
        
        # 2. HARVEST PHASE
        print("\n--- PHASE 2: HARVEST ---")
        harvested_products = []
        seen_ids = set()
        
        # Load existing if available to resume
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    harvested_products = json.load(f)
                seen_ids = {str(p["id"]) for p in harvested_products}
                print(f"[*] Loaded {len(harvested_products)} existing products. Resuming...")
            except Exception:
                pass
                
        style_ids = list(discovered_styles.keys())
        total_styles = len(style_ids)
        print(f"[*] Total unique Style IDs to process: {total_styles}")
        
        style_counter = 0
        for style_id in style_ids:
            style_counter += 1
            style_info = discovered_styles[style_id]
            pdp_url = style_info["pdp_url"]
            parent_cat = style_info["parent_category"]
            cat_key = style_info["category"]
            
            print(f"\n[{style_counter}/{total_styles}] Harvesting Style ID: {style_id} | PDP: {pdp_url}")
            
            try:
                # Navigate to PDP
                await page.goto(pdp_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
                
                next_data_str = await page.evaluate("() => document.getElementById('__NEXT_DATA__').textContent")
                if not next_data_str:
                    print(f"  [!] Missing detail next_data block. Skipping.")
                    continue
                    
                data = json.loads(next_data_str)
                page_props = data.get("props", {}).get("pageProps", {})
                variations = page_props.get("productPageProps", {}).get("aemData", {}).get("productArticleDetails", {}).get("variations", {})
                
                if not variations:
                    print(f"  [!] No variations found in PDP. Skipping.")
                    continue
                    
                # Fetch live stock availability inside the page context (shares cookies & credentials)
                avail_url = f"https://ofg.hm.com/pdh-availability/v1/product/vn/availability/{style_id}"
                avail_list = await page.evaluate(f"""
                    fetch('{avail_url}')
                        .then(r => r.json())
                        .then(d => d.availability || [])
                        .catch(e => [])
                """)
                
                print(f"  - Fetched active VN stock list: {len(avail_list)} in-stock size codes.")
                
                # Parse details for ALL variations of this style
                var_count = 0
                for var_code, var_data in variations.items():
                    if not isinstance(var_data, dict):
                        continue
                        
                    # Skip if already in database (deduplication)
                    if var_code in seen_ids:
                        continue
                        
                    # Check exclusions for variations (e.g. if title/name changed)
                    var_title = var_data.get("name") or style_info["title"]
                    if should_exclude(var_title, cat_key):
                        continue
                        
                    # Pricing
                    base_price = float(var_data.get("whitePriceValue") or 0.0)
                    promo_price = float(var_data.get("redPriceValue") or var_data.get("yellowPriceValue") or 0.0)
                    
                    price_val = promo_price if (promo_price > 0.0 and promo_price < base_price) else base_price
                    comp_val = base_price if (promo_price > 0.0 and promo_price < base_price) else None
                    
                    discount_percent = 0
                    if comp_val and price_val and comp_val > price_val:
                        discount_percent = int(round((comp_val - price_val) / comp_val * 100))
                        
                    # Images
                    images = []
                    for img_obj in var_data.get("images", []):
                        img_url = img_obj.get("baseUrl")
                        if img_url:
                            # Cleanup relative slashes
                            if img_url.startswith("//"):
                                img_url = "https:" + img_url
                            if img_url not in images:
                                images.append(img_url)
                                
                    featured_image = images[0] if images else ""
                    
                    # Specifications Mapping
                    specifications = {}
                    
                    # 1. Composition
                    comp_strs = []
                    for comp_item in var_data.get("composition", []):
                        materials = comp_item.get("materials", [])
                        for mat in materials:
                            m_name = mat.get("name", "")
                            m_amount = mat.get("amount", "")
                            if m_name and m_amount:
                                comp_strs.append(f"{m_name} {m_amount}")
                            elif m_name:
                                comp_strs.append(m_name)
                    if comp_strs:
                        specifications["Chất liệu"] = "; ".join(comp_strs)
                        
                    # 2. Care instructions
                    care_instructions = var_data.get("careInstructions", [])
                    if care_instructions:
                        specifications["Lưu ý giặt ủi"] = "; ".join(care_instructions)
                        
                    # 3. Product attributes
                    attrs_desc = var_data.get("productAttributes", {}).get("description", [])
                    for attr in attrs_desc:
                        title = attr.get("title", "")
                        vals = attr.get("values", [])
                        val_str = ", ".join(vals) if isinstance(vals, list) else str(vals)
                        
                        t_lower = title.lower()
                        if "fits" in t_lower or "phom" in t_lower or "form" in t_lower:
                            specifications["Form dáng"] = val_str
                        elif "length" in t_lower or "chiều dài" in t_lower:
                            specifications["Chiều dài"] = val_str
                        elif "sleeve" in t_lower or "tay áo" in t_lower:
                            specifications["Tay áo"] = val_str
                        elif "neck" in t_lower or "cổ" in t_lower:
                            specifications["Cổ áo"] = val_str
                        else:
                            specifications[title] = val_str
                            
                    # Mapped type
                    mapped_type = map_product_type(cat_key, var_title, parent_cat)
                    
                    # Options lists
                    colors_list = [var_data.get("name")] if var_data.get("name") else []
                    sizes_list = [size.get("name") for size in var_data.get("sizes", []) if size.get("name")]
                    
                    # Variants mapping
                    variants_list = []
                    for size in var_data.get("sizes", []):
                        size_code = size.get("sizeCode")
                        size_name = size.get("name")
                        if not size_code or not size_name:
                            continue
                            
                        is_avail = size_code in avail_list
                        qty = 1 if is_avail else 0
                        
                        variants_list.append({
                            "id": size_code,
                            "sku": size_code,
                            "title": f"{var_data.get('name')} / {size_name}",
                            "option1": var_data.get("name"),
                            "option2": size_name,
                            "price": price_val,
                            "compare_at_price": comp_val,
                            "available": is_avail,
                            "inventory_quantity": qty,
                            "featured_image": featured_image
                        })
                        
                    p_available = any(v["available"] for v in variants_list) if variants_list else False
                    
                    product_data = {
                        "id": var_code,
                        "handle": var_code,
                        "title": var_title,
                        "vendor": "H&M",
                        "type": mapped_type,
                        "parent_category": parent_cat,
                        "description": var_data.get("description") or "",
                        "description_html": var_data.get("description") or "",
                        "available": p_available,
                        "url": f"https://www2.hm.com/vi_vn/productpage.{var_code}.html",
                        "_scraped_category": mapped_type,
                        "_scraped_url": f"https://www2.hm.com/vi_vn/productpage.{var_code}.html",
                        "price": price_val,
                        "price_min": price_val,
                        "price_max": price_val,
                        "compare_at_price": comp_val,
                        "discount_percent": discount_percent,
                        "images": images,
                        "featured_image": featured_image,
                        "options": {
                            "colors": colors_list,
                            "sizes": sizes_list
                        },
                        "specifications": specifications,
                        "tags": [cat_key] if cat_key else [],
                        "variants": variants_list,
                        "_scraped_at": datetime.now().isoformat()
                    }
                    
                    harvested_products.append(product_data)
                    seen_ids.add(var_code)
                    var_count += 1
                    
                print(f"  - Harvested {var_count} active color variations for this style.")
                
                # Save incrementally every style processed
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(harvested_products, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                print(f"  [!] Error harvesting style {style_id}: {e}")
                
        # Final output save
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
        total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
        print("\n" + "=" * 65)
        print("  ✅ H&M SCRAPE COMPLETED SUCCESSFULLY!")
        print(f"  Total unique products : {len(harvested_products)}")
        print(f"  Total variants        : {total_variants}")
        print(f"  Output file           : {OUTPUT_FILE}")
        print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
