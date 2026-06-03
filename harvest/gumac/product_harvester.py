import os
import json
import sys
import asyncio
import aiohttp
import re
import html
from typing import Dict, List, Any

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/gumac/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "gumac_products_full.json")

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Helper function to prepends domain to relative image paths
def clean_image_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/"):
        return "https://cms.gumac.vn" + path
    return "https://cms.gumac.vn/" + path

def clean_description_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    # Remove style blocks
    clean_text = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL)
    # Remove script blocks
    clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.DOTALL)
    # Replace common block elements with newlines
    clean_text = re.sub(r'</?(p|div|br|h\d)[^>]*>', '\n', clean_text)
    # Strip all other HTML tags
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    # Unescape HTML entities
    clean_text = html.unescape(clean_text)
    # Normalize whitespaces/newlines
    lines = [line.strip() for line in clean_text.split('\n')]
    clean_lines = []
    for line in lines:
        if line:
            clean_lines.append(line)
    return '\n'.join(clean_lines)

def extract_size_guide(raw_data: Dict[str, Any], description_html: str) -> str:
    # 1. Check category sizeGuideImage
    category_obj = raw_data.get("category")
    cat_img_path = None
    if category_obj and isinstance(category_obj, dict):
        size_guide_image = category_obj.get("sizeGuideImage")
        if size_guide_image and isinstance(size_guide_image, dict):
            cat_img_path = size_guide_image.get("path")
            
    if cat_img_path:
        return clean_image_path(cat_img_path)
    
    # 2. Search in description HTML for images containing bang-size or size
    if description_html:
        img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', description_html, re.IGNORECASE)
        for src in img_srcs:
            if any(term in src.lower() for term in ["bang-size", "size-guide", "sizeguide", "bangsize"]):
                return clean_image_path(src)
                
    return ""

async def fetch_product_data(session: aiohttp.ClientSession, url: str, category: str, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    # Extract code from URL (last path segment)
    parts = url.rstrip("/").split("/")
    code = parts[-1]
    
    api_url = f"https://cms.gumac.vn/api/v1/products/{code}"
    max_retries = 5
    
    for attempt in range(max_retries):
        async with semaphore:
            try:
                # Add delay between requests
                await asyncio.sleep(0.5)
                async with session.get(api_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as response:
                    if response.status == 429:
                        wait_time = (2 ** attempt) + 1
                        print(f"[!] Rate limited (429) for {code}. Waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status != 200:
                        print(f"[!] HTTP {response.status} for {code}")
                        return {"url": url, "category": category, "error": f"HTTP {response.status}"}
                        
                    res_json = await response.json()
                    raw_data = res_json.get("data")
                    if not raw_data:
                        print(f"[!] No data field in response for {code}")
                        return {"url": url, "category": category, "error": "Empty data"}
                        
                    # Structure data to match standard format
                    desc_html = raw_data.get("description", "")
                    clean_desc = clean_description_html(desc_html)
                    size_guide = extract_size_guide(raw_data, desc_html)

                    category_obj = raw_data.get("category")
                    category_name = category_obj.get("name") if category_obj and isinstance(category_obj, dict) else None

                    product_data = {
                        "id": raw_data.get("id"),
                        "handle": raw_data.get("slug"),
                        "title": raw_data.get("name"),
                        "vendor": "Gumac",
                        "type": category_name,
                        "description": clean_desc,
                        "description_html": desc_html,
                        "size_guide_image": size_guide,
                        "available": raw_data.get("inventory", 0) > 0,
                        "tags": raw_data.get("hashtags", []),
                        "url": url,
                        "_scraped_category": category,
                        "_scraped_url": url,
                        "material": raw_data.get("material"),
                        "features": [f.get("label") for f in raw_data.get("outstandingFeatures", []) if f.get("label")],
                    }
                    
                    # Clean and format images
                    images = []
                    featured_image = ""
                    colors_data = raw_data.get("colors", [])
                    for color in colors_data:
                        if color and isinstance(color, dict):
                            media = color.get("media")
                            if media and isinstance(media, dict):
                                gallery = media.get("gallery") or []
                                for g in gallery:
                                    if g and isinstance(g, dict):
                                        img_url = clean_image_path(g.get("path"))
                                        if img_url and img_url not in images:
                                            images.append(img_url)
                                
                    if images:
                        featured_image = images[0]
                    product_data["images"] = images
                    product_data["featured_image"] = featured_image
                    
                    # Process variants
                    variants = []
                    skus = raw_data.get("sku", [])
                    for s in skus:
                        if not s or not isinstance(s, dict):
                            continue
                        # Extract variant specific details
                        variant_price = s.get("salePrice", s.get("price", 0))
                        compare_price = s.get("price") if s.get("salePrice") else None
                        
                        # Process variant options
                        color_obj = s.get("color")
                        opt1 = color_obj.get("name") if color_obj and isinstance(color_obj, dict) else None
                        
                        size_obj = s.get("size")
                        opt2 = size_obj.get("name") if size_obj and isinstance(size_obj, dict) else None
                        
                        variant_images = []
                        if color_obj and isinstance(color_obj, dict):
                            media_obj = color_obj.get("media")
                            if media_obj and isinstance(media_obj, dict):
                                var_gallery = media_obj.get("gallery") or []
                                for vg in var_gallery:
                                    if vg and isinstance(vg, dict):
                                        img_path = clean_image_path(vg.get("path"))
                                        if img_path:
                                            variant_images.append(img_path)
                                
                        # Map variant attributes/specs
                        attrs = {}
                        for attr in s.get("attributes", []):
                            if attr and isinstance(attr, dict):
                                lbl = attr.get("label")
                                val = attr.get("value")
                                if lbl and val:
                                    attrs[lbl] = val
                                
                        # Override size label to match variant's size code
                        # This fixes GUMAC backend returning static "S" for all sizes.
                        if opt2:
                            for k, v in list(attrs.items()):
                                if "size" in k.lower() and v == "S":
                                    attrs[k] = opt2
                                
                        featured_img = ""
                        if color_obj and isinstance(color_obj, dict):
                            media_obj = color_obj.get("media")
                            if media_obj and isinstance(media_obj, dict):
                                inner_color = media_obj.get("color")
                                if inner_color and isinstance(inner_color, dict):
                                    featured_img = clean_image_path(inner_color.get("path"))

                        variant_data = {
                            "id": s.get("id"),
                            "sku": s.get("code"),
                            "title": f"{opt1} / {opt2}" if opt1 and opt2 else (opt1 or opt2 or ""),
                            "option1": opt1,
                            "option2": opt2,
                            "price": variant_price,
                            "compare_at_price": compare_price,
                            "available": True, # GUMAC API doesn't show exact stock count for SKU in detail call
                            "featured_image": featured_img,
                            "gallery": variant_images,
                            "specifications": attrs
                        }
                        variants.append(variant_data)
                        
                    product_data["variants"] = variants
                    
                    # Store main price/compare price at product level
                    if skus:
                        product_data["price"] = skus[0].get("salePrice", skus[0].get("price", 0))
                        product_data["compare_at_price"] = skus[0].get("price") if skus[0].get("salePrice") else None
                    else:
                        product_data["price"] = 0
                        product_data["compare_at_price"] = None
                        
                    return product_data
                    
            except Exception as e:
                print(f"[!] Error fetching {code} (Attempt {attempt+1}/{max_retries}): {e}")
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
    seen_in_run = set()
    for category, urls in category_map.items():
        for url in urls:
            if url not in existing_urls and url not in seen_in_run:
                items_to_scrape.append({"category": category, "url": url})
                seen_in_run.add(url)
                
    # No crawl limit, harvest all discovered items
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
