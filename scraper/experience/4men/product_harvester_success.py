import os
import json
import sys
import re
import asyncio
import aiohttp
import ssl
import time
from datetime import datetime
from bs4 import BeautifulSoup

# Windows-specific: Event Loop Policy
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "4men_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://4men.com.vn"
VENDOR = "4MEN"
CONCURRENCY_LIMIT = 5
DELAY_BETWEEN_REQUESTS = 0.3  # Rate limit

# SSL Context to bypass certification issues
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

def clean_html(raw_html):
    if not raw_html:
        return ""
    clean = re.sub(r'<[^>]*>', ' ', raw_html)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def parse_gtm_details(html_text):
    match = re.search(r"dataLayer\.push\(\{\s*['\"]event['\"]\s*:\s*['\"]productDetail['\"].*?['\"]products['\"]\s*:\s*\[\s*\{(.*?)\}\]", html_text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"['\"]event['\"]\s*:\s*['\"]productDetail['\"].*?['\"]products['\"]\s*:\s*\[\s*\{(.*?)\}\]", html_text, re.DOTALL | re.IGNORECASE)
        
    gtm_data = {}
    if match:
        block = match.group(1)
        for field in ["name", "id", "price", "brand", "category", "SKU"]:
            f_match = re.search(rf"['\"]{field}['\"]\s*:\s*['\"]([^'\"]*)['\"]", block, re.IGNORECASE)
            if f_match:
                gtm_data[field] = f_match.group(1)
    return gtm_data

def extract_specs(soup):
    specs = {
        "Mã sản phẩm": "",
        "Chất liệu": "",
        "Họa tiết": "",
        "Form dáng": "",
        "Màu sắc": "",
        "Xuất xứ": "Việt Nam"
    }
    desc_text = ""
    detail_div = soup.select_one(".details-box.html-content") or soup.select_one(".accordion-content")
    if not detail_div:
        for div in soup.find_all("div"):
            if "chất liệu" in div.text.lower() and len(div.text) < 1500 and len(div.find_all("div")) < 3:
                detail_div = div
                break
                
    if detail_div:
        html_desc = str(detail_div)
        desc_text = re.sub(r'<(?:br|p|div|li)[^>]*>', '\n', html_desc)
        desc_text = clean_html(desc_text)
        
        lines = [line.strip() for line in re.split(r'[\n\r]+', re.sub(r'<(?:br|p|div|li)[^>]*>', '\n', html_desc)) if line.strip()]
        for line in lines:
            line_clean = clean_html(line)
            m = re.match(r'^[-*•]\s*([^:]+):\s*(.*)', line_clean)
            if not m:
                m = re.match(r'^\s*([^:]+):\s*(.*)', line_clean)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                key_l = key.lower()
                if "mã sản phẩm" in key_l or "mã" in key_l:
                    specs["Mã sản phẩm"] = val
                elif "chất liệu" in key_l:
                    specs["Chất liệu"] = val
                elif "họa tiết" in key_l:
                    specs["Họa tiết"] = val
                elif "form" in key_l or "phom" in key_l:
                    specs["Form dáng"] = val
                elif "màu" in key_l:
                    specs["Màu sắc"] = val
    return specs, desc_text

def extract_sizes(soup):
    sizes = []
    select = soup.find(id="sizeSelect")
    if select:
        options = select.find_all("option")
        for opt in options:
            val = opt.get("value") or opt.text.strip()
            if val and val.lower() not in ["chọn size", ""]:
                sizes.append(val)
    return sizes

def extract_colors_from_thumbs(soup):
    colors = []
    container = soup.find(class_="shop-detail-color-container")
    if container:
        links = container.find_all("a")
        for a in links:
            title = a.get("title") or ""
            color_match = re.search(r'Màu\s+(.*)', title, re.IGNORECASE)
            if color_match:
                colors.append(color_match.group(1).strip())
            else:
                img = a.find("img")
                if img and img.get("alt"):
                    color_match = re.search(r'Màu\s+(.*)', img.get("alt"), re.IGNORECASE)
                    if color_match:
                        colors.append(color_match.group(1).strip())
    return colors

def extract_images(soup):
    images = []
    gal_imgs = soup.select(".prod-slider.sync1 img") or soup.select(".prod-slider img") or soup.select(".owl-carousel img")
    for img in gal_imgs:
        src = img.get("src") or img.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = SITE_BASE + src
            if src not in images and ("slide-products" in src or "thumbs" in src):
                images.append(src)
                
    if not images:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = SITE_BASE + src
                if "thumbs" in src and "product-color" not in src and src not in images:
                    images.append(src)
    return images

def get_page_color(title: str) -> str:
    color_match = re.search(r'Màu\s+(.*)', title, re.IGNORECASE)
    if color_match:
        return color_match.group(1).strip()
    return "N/A"

async def harvest_url(session, url, category, sem):
    async with sem:
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
        print(f"[*] Harvesting PDP: {url}")
        
        max_retries = 5
        html_text = None
        for attempt in range(max_retries):
            try:
                async with session.get(url, headers=HEADERS, ssl=ssl_ctx, timeout=15) as response:
                    if response.status == 200:
                        html_text = await response.text()
                        break
                    elif response.status == 429:
                        wait_t = 2 ** attempt + 1
                        print(f"  [!] HTTP 429 Rate Limited on {url}. Waiting {wait_t}s...")
                        await asyncio.sleep(wait_t)
                    else:
                        print(f"  [!] HTTP status {response.status} on {url}. Retrying...")
                        await asyncio.sleep(1)
            except Exception as e:
                print(f"  [!] Error fetching {url} (attempt {attempt+1}): {e}")
                await asyncio.sleep(1)
                
        if not html_text:
            print(f"  [Error] Failed to harvest URL: {url}")
            return None
            
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            h1 = soup.find("h1")
            title = h1.text.strip() if h1 else ""
            
            handle = url.split("/")[-1].replace(".html", "")
            
            gtm = parse_gtm_details(html_text)
            p_id = gtm.get("id")
            if not p_id:
                url_id_match = re.search(r'-(\d+)\.html$', url)
                p_id = url_id_match.group(1) if url_id_match else handle
                
            sku = gtm.get("SKU") or p_id
            
            raw_price = gtm.get("price")
            if raw_price:
                price = float(raw_price)
            else:
                price_el = soup.select_one(".price-current") or soup.select_one(".price")
                if price_el:
                    price_str = re.sub(r'\D', '', price_el.text)
                    price = float(price_str) if price_str else 0.0
                else:
                    price = 0.0
                    
            old_price_val = None
            discount_pct = 0
            old_price_el = soup.select_one(".price-old") or soup.select_one("del")
            if old_price_el:
                old_str = re.sub(r'\D', '', old_price_el.text)
                if old_str:
                    old_price_val = float(old_str)
                    if old_price_val > price:
                        discount_pct = int(round((old_price_val - price) / old_price_val * 100))
            
            page_color = get_page_color(title)
            if page_color == "N/A" and gtm.get("name"):
                page_color = get_page_color(gtm["name"])
                
            sizes = extract_sizes(soup)
            if not sizes:
                sizes = ["S", "M", "L", "XL", "XXL"]
                
            colors_swatch = extract_colors_from_thumbs(soup)
            if not colors_swatch:
                colors_swatch = [page_color] if page_color != "N/A" else []
                
            specs, description = extract_specs(soup)
            if not specs["Màu sắc"] and page_color != "N/A":
                specs["Màu sắc"] = page_color
            if not specs["Mã sản phẩm"]:
                specs["Mã sản phẩm"] = sku
                
            images = extract_images(soup)
            featured_image = images[0] if images else ""
            
            variants = []
            for sz in sizes:
                v_id = f"{p_id}_{sz}"
                variants.append({
                    "id": v_id,
                    "sku": f"{sku}-{sz}",
                    "title": f"{title} - Size {sz}",
                    "option1": page_color if page_color != "N/A" else None,
                    "option2": sz,
                    "price": price,
                    "compare_at_price": old_price_val,
                    "available": True,
                    "inventory_quantity": 1,
                    "featured_image": featured_image,
                    "specifications": specs
                })
                
            return {
                "id": p_id,
                "handle": handle,
                "title": title,
                "vendor": VENDOR,
                "type": category,
                "parent_category": "Nam",
                "description": description,
                "available": True,
                "url": url,
                "_scraped_category": category,
                "_scraped_url": url,
                "price": price,
                "price_min": price,
                "price_max": price,
                "compare_at_price": old_price_val,
                "discount_percent": discount_pct,
                "images": images,
                "featured_image": featured_image,
                "options": {
                    "colors": colors_swatch,
                    "sizes": sizes
                },
                "specifications": specs,
                "tags": [category, VENDOR],
                "variants": variants,
                "_scraped_at": datetime.now().isoformat()
            }
            
        except Exception as ex:
            print(f"  [Error] Parsing error on {url}: {ex}")
            return None

async def main():
    print("=" * 60)
    print("🏆 4MEN PRODUCT HARVESTER STARTING")
    print("=" * 60)
    
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Error: discovery input file not found at {DISCOVERY_INPUT_FILE}. Exiting.")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        
    url_to_category = {}
    for category, urls in discovery_map.items():
        for url in urls:
            url_to_category[url] = category
            
    total_urls = len(url_to_category)
    print(f"[*] Total discovered URLs to harvest: {total_urls}")
    
    harvested_products = []
    seen_ids = set()
    seen_urls = set()
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
            for p in harvested_products:
                seen_ids.add(p["id"])
                seen_urls.add(p["_scraped_url"])
            print(f"[*] Loaded {len(harvested_products)} existing harvested products. Resuming...")
        except Exception as e:
            print(f"[-] Error loading output file: {e}. Starting fresh.")
            
    urls_to_harvest = [url for url in url_to_category.keys() if url not in seen_urls]
    print(f"[*] Remaining URLs to harvest: {len(urls_to_harvest)}")
    
    if not urls_to_harvest:
        print("[*] All URLs already harvested. Complete!")
        return
        
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in urls_to_harvest:
            cat = url_to_category[url]
            tasks.append(harvest_url(session, url, cat, sem))
            
        results = await asyncio.gather(*tasks)
        
        new_count = 0
        for item in results:
            if item:
                harvested_products.append(item)
                new_count += 1
                
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "=" * 60)
    print("🏆 4MEN HARVEST COMPLETED!")
    print(f"Harvested in this run    : {new_count} products")
    print(f"Total unique products    : {len(harvested_products)}")
    print(f"Total variants           : {total_variants}")
    print(f"Output saved to          : {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
