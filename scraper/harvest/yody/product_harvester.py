import os
import json
import sys
import re
import asyncio
import aiohttp
import html
from typing import Dict, List, Any

# Ensure output is UTF-8 on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Windows event loop policy for aiohttp compatibility
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/yody/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "yody_products_full.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def extract_pdp_data(html_content: str) -> dict:
    start_marker = 'self.PDPData = "'
    start_idx = html_content.find(start_marker)
    if start_idx == -1:
        start_marker = "self.PDPData = '"
        start_idx = html_content.find(start_marker)
        if start_idx == -1:
            return None
            
    start_idx += len(start_marker)
    end_idx = start_idx
    quote_char = html_content[start_idx - 1]
    
    while end_idx < len(html_content):
        if html_content[end_idx] == quote_char:
            bs_count = 0
            i = end_idx - 1
            while i >= start_idx and html_content[i] == '\\':
                bs_count += 1
                i -= 1
            if bs_count % 2 == 0:
                break
        end_idx += 1
        
    raw_str = html_content[start_idx:end_idx]
    prepared_str = raw_str.replace('\n', '\\n').replace('\r', '\\r')
    
    try:
        decoded_str = json.loads(f'"{prepared_str}"')
        return json.loads(decoded_str)
    except Exception as e:
        # Fallback manual cleaning if double JSON load fails
        try:
            # Replace escaped quotes and backslashes
            cleaned = raw_str.replace('\\"', '"').replace('\\\\', '\\')
            cleaned = cleaned.replace('\\n', '\n').replace('\\r', '\r')
            return json.loads(cleaned)
        except Exception as ex:
            print(f"[!] PDPData parsing failed: {ex}")
            return None

def transform_yody_product(pdp_data: dict, product_url: str, scraped_category: str) -> dict:
    p_id = pdp_data.get('id')
    handle = pdp_data.get('url_handle')
    title = pdp_data.get('name', '')
    
    # Exclusions check
    kids_pattern = re.compile(r'\b(?:bé trai|bé gái|trẻ em|sơ sinh|em bé|kids?|bab[yy])\b|be-trai|be-gai|tre-em|so-sinh', re.IGNORECASE)
    underwear_pattern = re.compile(r'\b(?:đồ lót|quần lót|áo lót|sịp|quần sịp|áo ngực|bras?|boxers?|panties)\b|do-lot|quan-lot|ao-lot|boxer|panties', re.IGNORECASE)
    shoes_pattern = re.compile(r'\b(?:giày|dép|sandal|sneaker|guốc|derby)\b|giay|dep|sandal|sneaker|guoc|derby', re.IGNORECASE)
    cosmetics_pattern = re.compile(r'\b(?:mỹ phẩm|son môi|kem dưỡng|sữa tắm|dầu gội)\b|my-pham|son-moi|kem-duong|sua-tam|dau-goi', re.IGNORECASE)
    
    is_kid = bool(kids_pattern.search(title) or kids_pattern.search(product_url) or kids_pattern.search(scraped_category))
    is_underwear = bool(underwear_pattern.search(title) or underwear_pattern.search(product_url) or underwear_pattern.search(scraped_category))
    is_shoe = bool(shoes_pattern.search(title) or shoes_pattern.search(product_url) or shoes_pattern.search(scraped_category))
    is_cosmetic = bool(cosmetics_pattern.search(title) or cosmetics_pattern.search(product_url) or cosmetics_pattern.search(scraped_category))
    
    is_swimwear = any(x in title.lower() or x in product_url.lower() for x in ["bơi", "swim"])
    is_socks = any(x in title.lower() or x in product_url.lower() for x in ["tất", "vớ", "socks"])
    
    if is_kid:
        print(f"[*] Skipping kid product: '{title}'")
        return None
    if is_underwear and not (is_swimwear or is_socks):
        print(f"[*] Skipping underwear product: '{title}'")
        return None
    if is_shoe:
        print(f"[*] Skipping shoe product: '{title}'")
        return None
    if is_cosmetic:
        print(f"[*] Skipping cosmetic product: '{title}'")
        return None
        
    desc_html = pdp_data.get('description', '')
    desc_clean = re.sub(r'<[^>]*>', '', desc_html).strip()
    desc_clean = html.unescape(desc_clean)
    
    specifications = {
        "Chất liệu": "",
        "Hướng dẫn sử dụng": ""
    }
    
    # Try parsing components from HTML description
    material_match = re.search(r'(?:Vải chính|Thành phần|Chất liệu).*?:\s*([^<>\n]+)', desc_html, re.IGNORECASE)
    if material_match:
        specifications["Chất liệu"] = material_match.group(1).strip()
    else:
        mat_obj = pdp_data.get('material') or {}
        if isinstance(mat_obj, dict) and mat_obj.get('name'):
            specifications["Chất liệu"] = mat_obj.get('name')
            
    preserve_match = re.search(r'(?:Khuyến cáo|Hướng dẫn sử dụng|Bảo quản).*?<ul>(.*?)</ul>', desc_html, re.DOTALL | re.IGNORECASE)
    if preserve_match:
        li_items = re.findall(r'<li>(.*?)</li>', preserve_match.group(1), re.DOTALL)
        clean_lis = [re.sub(r'<[^>]*>', '', li).strip() for li in li_items]
        specifications["Hướng dẫn sử dụng"] = "\n".join([html.unescape(li) for li in clean_lis if li])
        
    tags = ["Yody"]
    cat_obj = pdp_data.get('category') or {}
    if isinstance(cat_obj, dict) and cat_obj.get('name'):
        tags.append(cat_obj.get('name'))
        
    # Images - collect unique absolute URLs
    images = []
    for v in pdp_data.get('variants', []):
        for img in v.get('images', []):
            img_url = img.get('image_url')
            if img_url and img_url not in images:
                images.append(img_url)
                
    if not images:
        for f in pdp_data.get('highlight_media_files', []):
            if isinstance(f, dict) and f.get('url'):
                images.append(f.get('url'))
                
    featured_image = images[0] if images else ""
    
    prices = []
    compare_prices = []
    available = False
    
    variants = []
    for v in pdp_data.get('variants', []):
        v_id = v.get('id')
        sku = v.get('sku')
        
        color_name = v.get('color', {}).get('name', 'Màu sắc')
        size_name = v.get('size', {}).get('name', 'Kích thước')
        v_title = f"{color_name} / {size_name}"
        
        v_price = float(v.get('sale_price', 0))
        v_orig = float(v.get('original_price', 0))
        v_compare = v_orig if v_orig > v_price else None
        
        prices.append(v_price)
        if v_compare:
            compare_prices.append(v_compare)
            
        v_avail = v.get('in_stock', True)
        if v_avail:
            available = True
            
        v_qty = float(v.get('inventory', 0))
        
        v_img = ""
        v_images = v.get('images', [])
        if v_images and isinstance(v_images, list):
            v_img = v_images[0].get('image_url', '')
        if not v_img:
            v_img = featured_image
            
        v_data = {
            "id": int(v_id),
            "sku": sku,
            "title": v_title,
            "option1": color_name,
            "option2": size_name,
            "price": v_price,
            "compare_at_price": v_compare,
            "available": v_avail,
            "inventory_quantity": v_qty,
            "featured_image": v_img,
            "specifications": specifications
        }
        variants.append(v_data)
        
    parent_price = prices[0] if prices else 0.0
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0
    compare_at_price = compare_prices[0] if compare_prices else None
    
    transformed = {
        "id": int(p_id) if p_id else None,
        "handle": handle,
        "title": title,
        "vendor": "Yody",
        "type": cat_obj.get('name') or scraped_category,
        "description": desc_clean,
        "description_html": desc_html,
        "available": available,
        "tags": tags,
        "url": product_url,
        "_scraped_category": scraped_category,
        "_scraped_url": product_url,
        "price": parent_price,
        "price_min": price_min,
        "price_max": price_max,
        "compare_at_price": compare_at_price,
        "images": images,
        "featured_image": featured_image,
        "options": ["Màu sắc", "Kích thước"],
        "specifications": specifications,
        "variants": variants
    }
    return transformed

async def fetch_product_page(session: aiohttp.ClientSession, url: str, scraped_category: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        for attempt in range(5):
            try:
                # Sleep a little to prevent hammering the server
                await asyncio.sleep(0.5)
                async with session.get(url, headers=HEADERS, ssl=False, timeout=15) as response:
                    if response.status == 200:
                        content = await response.text()
                        pdp_data = extract_pdp_data(content)
                        if pdp_data:
                            return transform_yody_product(pdp_data, url, scraped_category)
                        else:
                            print(f"[!] PDPData not found on page: {url}")
                            return None
                    elif response.status in [429, 503]:
                        backoff = 2 * (attempt + 1)
                        print(f"[!] Got status {response.status} for {url}. Backing off for {backoff}s...")
                        await asyncio.sleep(backoff)
                    else:
                        print(f"[!] Failed status {response.status} for {url}")
                        return None
            except Exception as e:
                print(f"[!] Exception fetching {url}: {e}. Retrying ({attempt+1}/5)...")
                await asyncio.sleep(2 * (attempt + 1))
        return None

async def main():
    print("=" * 60)
    print("🏆 YODY PRODUCT HARVESTER STARTING")
    print("=" * 60)
    
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Discovery input file not found: {DISCOVERY_INPUT_FILE}")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        
    url_to_category = {}
    for cat_group, urls in discovery_map.items():
        for url in urls:
            url_to_category[url] = cat_group
            
    total_urls = len(url_to_category)
    print(f"[*] Discovered product URLs to harvest: {total_urls}")
    
    existing_data = []
    existing_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            for p in existing_data:
                existing_urls.add(p["_scraped_url"])
            print(f"[*] Loaded existing output file with {len(existing_data)} harvested products.")
        except Exception as e:
            print(f"[!] Error loading existing output: {e}. Starting fresh.")
            
    urls_to_fetch = [url for url in url_to_category.keys() if url not in existing_urls]
    print(f"[*] Products remaining to harvest: {len(urls_to_fetch)}")
    
    if not urls_to_fetch:
        print("[*] All products have already been harvested!")
        return
        
    # Async loop
    sem = asyncio.Semaphore(5) # Max 5 concurrent requests
    
    # Process in batches of 50 to write incrementally
    batch_size = 50
    total_harvested = len(existing_data)
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(urls_to_fetch), batch_size):
            batch = urls_to_fetch[i:i+batch_size]
            print(f"\n[*] Harvesting batch {i // batch_size + 1} ({len(batch)} URLs)...")
            
            tasks = [
                fetch_product_page(session, url, url_to_category[url], sem)
                for url in batch
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Filter None and add to existing
            success_count = 0
            for r in results:
                if r:
                    existing_data.append(r)
                    success_count += 1
                    
            total_harvested += success_count
            print(f"[*] Batch completed: {success_count} / {len(batch)} successful. Cumulative harvested: {total_harvested}")
            
            # Save batch incrementally
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
                
    print("\n" + "="*50)
    print("🏆 YODY HARVEST COMPLETED!")
    print(f"Total unique products harvested: {total_harvested}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
