import os
import json
import sys
import re
import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
from datetime import datetime

# Windows event loop policy
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/5sfashion/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "5sfashion_products_full.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SITE_BASE = "https://5sfashion.vn"
VENDOR = "5S Fashion"
CONCURRENCY_LIMIT = 5
DELAY_BETWEEN_REQUESTS = 0.3

# SSL Context to bypass certification issues
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

def clean_price(price_str):
    if not price_str:
        return 0.0
    clean = re.sub(r'\D', '', price_str)
    return float(clean) if clean else 0.0

async def harvest_url(session, url, category_name, variant_sku_map, sem):
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
            
            # 1. Title and base SKU
            title_el = soup.find("h1")
            if not title_el:
                return None
            title = title_el.text.strip()
            handle = url.split("/")[-1].replace(".html", "")
            
            base_sku = ""
            words = title.split()
            if words:
                last_word = words[-1]
                if re.search(r'[a-zA-Z0-9]+', last_word):
                    base_sku = last_word
            
            # 2. Options (Colors & Sizes)
            colors = []
            color_images = {}
            color_container = soup.find(class_="variant-color")
            if color_container:
                for li in color_container.find_all("li"):
                    c_name = li.get("data-color")
                    c_id = li.get("data-product-color-id")
                    img_el = li.find("img")
                    img_url = ""
                    if img_el:
                        img_url = img_el.get("data-src") or img_el.get("src")
                        if img_url:
                            if img_url.startswith("//"):
                                img_url = "https:" + img_url
                            elif img_url.startswith("/"):
                                img_url = SITE_BASE + img_url
                            # Normalize to high resolution
                            img_url = img_url.replace("/fast/69x0/", "/fast/1325x0/").replace("/fast/180x0/", "/fast/1325x0/")
                    
                    if c_name and c_id:
                        colors.append({"name": c_name, "id": c_id, "image": img_url})
                        color_images[c_name] = img_url
                        
            sizes = []
            size_container = soup.find(class_="variant-size")
            if size_container:
                for li in size_container.find_all("li"):
                    s_name = li.get("data-size")
                    s_id = li.get("data-size-id")
                    if s_name and s_id:
                        sizes.append({"name": s_name, "id": s_id})
                        
            # 3. Variants Construction using hidden inputs
            variants = []
            prices = []
            compare_prices = []
            
            for c in colors:
                color_prefix = c["id"]
                for s in sizes:
                    size_id = s["id"]
                    cls_name = f"{color_prefix}-{size_id}"
                    inp = soup.find("input", class_=cls_name)
                    
                    if inp:
                        v_id = inp.get("data-id")
                        inv = int(inp.get("data-inventory", 0))
                        
                        price_val = clean_price(inp.get("data-price-promotion") or inp.get("data-price"))
                        comp_val = clean_price(inp.get("data-price"))
                        
                        if price_val:
                            prices.append(price_val)
                        if comp_val and comp_val > price_val:
                            compare_prices.append(comp_val)
                            
                        # Lookup SKU from discovery map
                        sku_val = variant_sku_map.get(str(v_id))
                        if not sku_val:
                            # Dynamic fallback
                            sku_val = f"{base_sku}-{c['name']}-{s['name']}"
                            
                        variants.append({
                            "id": str(v_id),
                            "sku": sku_val,
                            "title": f"{title} - {c['name']} - Size {s['name']}",
                            "option1": c["name"],
                            "option2": s["name"],
                            "price": price_val,
                            "compare_at_price": comp_val if comp_val > price_val else None,
                            "available": inv > 0,
                            "inventory_quantity": inv,
                            "images": [c["image"]] if c["image"] else []
                        })
                        
            if not variants:
                # Fallback if no variants parsed (e.g. single variant product)
                default_price = clean_price(soup.select_one(".price-current").text if soup.select_one(".price-current") else "")
                default_comp = clean_price(soup.select_one(".price-old").text if soup.select_one(".price-old") else "")
                variants.append({
                    "id": handle,
                    "sku": base_sku,
                    "title": title,
                    "option1": None,
                    "option2": None,
                    "price": default_price,
                    "compare_at_price": default_comp if default_comp > default_price else None,
                    "available": True,
                    "inventory_quantity": 1,
                    "images": []
                })
                prices.append(default_price)
                if default_comp > default_price:
                    compare_prices.append(default_comp)
                    
            price_min = min(prices) if prices else 0.0
            price_max = max(prices) if prices else 0.0
            compare_at_price = max(compare_prices) if compare_prices else None
            discount_pct = 0
            if compare_at_price and price_min and compare_at_price > price_min:
                discount_pct = int(round((compare_at_price - price_min) / compare_at_price * 100))
                
            # 4. Specifications & Description
            specs = {
                "Mã sản phẩm": base_sku,
                "Chất liệu": "",
                "Form dáng": "",
                "Họa tiết": "",
                "Màu sắc": ", ".join([c["name"] for c in colors]),
                "Xuất xứ": "Việt Nam"
            }
            
            content_desc = soup.select_one(".content-desc")
            description = ""
            if content_desc:
                description = content_desc.text.strip()
                lines = [l.strip() for l in description.split("\n") if l.strip()]
                
                materials_list = []
                fits_list = []
                designs_list = []
                
                for line in lines:
                    line_clean = re.sub(r'^[-*•\s]+', '', line).strip()
                    line_lower = line_clean.lower()
                    
                    if line.startswith(('-', '*', '•')) or '%' in line:
                        if ('%' in line or any(x in line_lower for x in ["cotton", "spandex", "polyester", "bamboo", "bông", "modal", "viscose"])) and not any(x in line_lower for x in ["phom dáng", "kiểu dáng", "dáng", "thiết kế"]):
                            if len(line_clean) < 150:
                                materials_list.append(line_clean)
                            elif '%' in line_clean and len(line_clean) < 250:
                                parts = line_clean.split(":")
                                materials_list.append(parts[0].strip())
                                
                    if any(x in line_lower for x in ["phom dáng", "form dáng", "slimfit", "regular", "relaxed", "dáng ôm", "dáng rộng"]):
                        if len(line_clean) < 200:
                            fits_list.append(line_clean)
                            
                    if line.startswith(('-', '*', '•')):
                        if any(x in line_lower for x in ["thiết kế", "họa tiết", "trơn basic", "in logo", "in hình", "thêu"]):
                            if len(line_clean) < 200:
                                designs_list.append(line_clean)
                                
                if materials_list:
                    specs["Chất liệu"] = "; ".join(materials_list[:3])
                if fits_list:
                    specs["Form dáng"] = fits_list[0]
                if designs_list:
                    specs["Họa tiết"] = designs_list[0]
                    
            # 5. Global Slider Images
            slider_images = []
            slider_main = soup.select_one(".slider-main") or soup.select_one(".slider-thumb")
            if slider_main:
                for img in slider_main.find_all("img"):
                    src = img.get("data-src") or img.get("src")
                    if src and not src.startswith("data:"):
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = SITE_BASE + src
                        src = src.replace("/fast/69x0/", "/fast/1325x0/").replace("/fast/180x0/", "/fast/1325x0/")
                        if src not in slider_images:
                            slider_images.append(src)
                            
            featured_image = slider_images[0] if slider_images else (colors[0]["image"] if colors else "")
            
            parent_category = "Nam"
            if "nữ" in category_name.lower():
                parent_category = "Nữ"
                
            return {
                "id": str(variants[0]["id"]) if variants else handle,
                "handle": handle,
                "title": title,
                "vendor": VENDOR,
                "type": category_name,
                "parent_category": parent_category,
                "description": description,
                "available": any(v["available"] for v in variants),
                "url": url,
                "_scraped_category": category_name,
                "_scraped_url": url,
                "price": price_min,
                "price_min": price_min,
                "price_max": price_max,
                "compare_at_price": compare_at_price,
                "discount_percent": discount_pct,
                "images": slider_images,
                "featured_image": featured_image,
                "options": {
                    "colors": [c["name"] for c in colors],
                    "sizes": [s["name"] for s in sizes]
                },
                "specifications": specs,
                "tags": [category_name, VENDOR],
                "variants": variants,
                "_scraped_at": datetime.now().isoformat()
            }
            
        except Exception as ex:
            print(f"  [Error] Parsing error on {url}: {ex}")
            import traceback
            traceback.print_exc()
            return None

async def main():
    print("=" * 60)
    print("🏆 5S FASHION PRODUCT HARVESTER STARTING")
    print("=" * 60)
    
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Discovery file not found at {DISCOVERY_INPUT_FILE}. Waiting...")
        for _ in range(30):
            if os.path.exists(DISCOVERY_INPUT_FILE):
                break
            await asyncio.sleep(2)
            
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[Error] Discovery file not found. Exiting.")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        if "categories" in discovery_map:
            discovery_map = discovery_map["categories"]
            
    variant_sku_map = {}
    sku_map_file = os.path.join(os.path.dirname(DISCOVERY_INPUT_FILE), "variant_sku_map.json")
    if os.path.exists(sku_map_file):
        try:
            with open(sku_map_file, "r", encoding="utf-8") as f:
                variant_sku_map = json.load(f)
        except Exception as e:
            print(f"[-] Error loading sku map: {e}")
        
    url_to_category = {}
    for category, urls in discovery_map.items():
        for url in urls:
            url_to_category[url] = category
            
    total_urls = len(url_to_category)
    print(f"[*] Total discovered URLs to harvest: {total_urls}")
    
    # Load existing harvested products to support resume
    harvested_products = []
    seen_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                harvested_products = json.load(f)
            for p in harvested_products:
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
            tasks.append(harvest_url(session, url, cat, variant_sku_map, sem))
            
        results = await asyncio.gather(*tasks)
        
        # Merge new products
        new_count = 0
        for item in results:
            if item:
                harvested_products.append(item)
                new_count += 1
                
        # Save results
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested_products, f, ensure_ascii=False, indent=2)
            
    total_variants = sum(len(p.get("variants", [])) for p in harvested_products)
    print("\n" + "=" * 60)
    print("🏆 5S FASHION HARVEST COMPLETED!")
    print(f"Harvested in this run    : {new_count} products")
    print(f"Total unique products    : {len(harvested_products)}")
    print(f"Total variants           : {total_variants}")
    print(f"Output saved to          : {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
