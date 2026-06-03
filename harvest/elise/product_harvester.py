import os
import json
import re
import sys
import html
import asyncio
import aiohttp
from typing import Dict, List, Any

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/elise/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "elise_products_full.json")

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def fetch_product_data(session: aiohttp.ClientSession, url: str, category: str, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    max_retries = 5
    for attempt in range(max_retries):
        async with semaphore:
            try:
                # Add delay between requests
                await asyncio.sleep(0.5)
                async with session.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept-Encoding': 'gzip, deflate'}) as response:
                    if response.status == 429:
                        wait_time = (2 ** attempt) + 1
                        print(f"[!] Rate limited (429) for {url}. Waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status != 200:
                        print(f"[!] HTTP {response.status} for: {url}")
                        return {"url": url, "category": category, "error": f"HTTP {response.status}"}
                        
                    html_content = await response.text()
                    
                    # 1. Title
                    title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html_content)
                    title = html.unescape(title_match.group(1).strip()) if title_match else ""
                    
                    # 2. Description
                    desc_match = re.search(r'<div class="product attribute description">[\s\S]*?<div class="value">([\s\S]*?)</div>', html_content)
                    description = desc_match.group(1).strip() if desc_match else ""
                    
                    # 3. Base SKU
                    sku_match = re.search(r'data-product-sku="([^"]+)"', html_content)
                    base_sku = sku_match.group(1).strip() if sku_match else ""
                    
                    # 4. Images
                    images = re.findall(r'data-big="([^"]+)"', html_content)
                    seen_img = set()
                    images = [img for img in images if not (img in seen_img or seen_img.add(img))]
                    featured_image = images[0] if images else ""
                    
                    # 5. Config/Variants
                    mage_inits = re.findall(r'<script[^>]*type="text/x-magento-init"[^>]*>([\s\S]*?)</script>', html_content)
                    
                    variants = []
                    
                    for script in mage_inits:
                        script = script.strip()
                        if "[data-role=swatch-options]" in script or "Magento_Swatches/js/swatch-renderer" in script:
                            try:
                                parsed = json.loads(script)
                                swatch_conf = parsed["[data-role=swatch-options]"]["Magento_Swatches/js/swatch-renderer"]["jsonConfig"]
                                
                                # Sizes map
                                size_options = {}
                                attrs = swatch_conf.get("attributes", {})
                                for attr_id, attr_val in attrs.items():
                                    if attr_val.get("code") == "size" or attr_val.get("label") == "Kích cỡ":
                                        for opt in attr_val.get("options", []):
                                            size_options[str(opt.get("id"))] = opt.get("label")
                                            
                                option_prices = swatch_conf.get("optionPrices", {})
                                index = swatch_conf.get("index", {})
                                stock_qty = swatch_conf.get("stockQty", {})
                                
                                for sim_id, combo in index.items():
                                    size_name = ""
                                    for attr_id, opt_id in combo.items():
                                        if str(opt_id) in size_options:
                                            size_name = size_options[str(opt_id)]
                                            break
                                            
                                    prices = option_prices.get(sim_id, {})
                                    price = prices.get("finalPrice", {}).get("amount", 0)
                                    old_price = prices.get("oldPrice", {}).get("amount", 0)
                                    
                                    stock_val = stock_qty.get(sim_id, "0")
                                    available = float(stock_val) > 0
                                    
                                    variant_sku = base_sku + "_" + size_name if size_name else base_sku
                                    
                                    variants.append({
                                        "id": int(sim_id) if sim_id.isdigit() else sim_id,
                                        "sku": variant_sku,
                                        "title": size_name,
                                        "option1": size_name,
                                        "price": price,
                                        "compare_at_price": old_price if old_price > price else None,
                                        "available": available,
                                        "inventory_quantity": float(stock_val)
                                    })
                            except Exception as e:
                                pass
                                
                    if not variants:
                        # Fallback for simple product
                        price_match = re.search(r'<meta property="product:price:amount" content="([^"]+)"', html_content)
                        price = float(price_match.group(1)) if price_match else 0.0
                        variants.append({
                            "id": base_sku,
                            "sku": base_sku,
                            "title": "Default",
                            "price": price,
                            "available": True,
                            "inventory_quantity": 1.0
                        })
                        
                    product_data = {
                        "id": base_sku,
                        "handle": url.split("/")[-1].replace(".html", ""),
                        "title": title,
                        "vendor": "Elise",
                        "type": category,
                        "description": description,
                        "available": any(v["available"] for v in variants),
                        "tags": [],
                        "images": images,
                        "featured_image": featured_image,
                        "options": ["Kích thước"] if variants and variants[0]["title"] != "Default" else [],
                        "url": url,
                        "_scraped_category": category,
                        "_scraped_url": url,
                        "variants": variants,
                        "price": variants[0]["price"] if variants else 0.0,
                        "compare_at_price": variants[0]["compare_at_price"] if variants else None
                    }
                    
                    return product_data
                    
            except Exception as e:
                print(f"[!] Error for {url} (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"url": url, "category": category, "error": str(e)}
                
    return {"url": url, "category": category, "error": "Max retries exceeded"}

async def main():
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Input file not found: {DISCOVERY_INPUT_FILE}")
        return

    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        category_map = json.load(f)
        
    existing_urls = set()
    existing_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for item in existing_data:
                    if "_scraped_url" in item:
                        existing_urls.add(item["_scraped_url"])
            print(f"[*] Loaded {len(existing_urls)} products from previous run.")
        except json.JSONDecodeError:
            pass

    # Concurrency control
    semaphore = asyncio.Semaphore(5)
    
    items_to_scrape = []
    for category, urls in category_map.items():
        for url in urls:
            if url not in existing_urls:
                items_to_scrape.append({"category": category, "url": url})
                
    # Crawl all discovered products from Elise to ensure full brand coverage
    print(f"[*] Target items to harvest: {len(items_to_scrape)}")
    if not items_to_scrape:
        print("[*] No new items to harvest.")
        return
        
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_product_data(session, item["url"], item["category"], semaphore) for item in items_to_scrape]
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if "error" not in r]
    error_results = [r for r in results if "error" in r]
    
    print(f"[*] Harvest completed! Success: {len(valid_results)}, Errors: {len(error_results)}")
    
    existing_data.extend(valid_results)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Saved total {len(existing_data)} products to {OUTPUT_FILE}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
