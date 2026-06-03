import os
import json
import asyncio
import aiohttp
from urllib.parse import urlparse
import sys

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "output", "single_product_sample.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "output", "single_product_sample_local.json")
IMAGE_DIR = os.path.join(BASE_DIR, "output", "images")

os.makedirs(IMAGE_DIR, exist_ok=True)

# Lấy extension từ url
def get_ext(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    return ext if ext else ".jpg"

# Fix URL //product.hstatic.net... -> https://product.hstatic.net...
def fix_url(url):
    if url and url.startswith("//"):
        return "https:" + url
    return url

async def download_image(session, url, save_path, semaphore):
    if not url: return False
    url = fix_url(url)
    if os.path.exists(save_path):
        return True # already downloaded
        
    async with semaphore:
        for attempt in range(3):
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(save_path, "wb") as f:
                            f.write(content)
                        return True
            except Exception as e:
                pass
            await asyncio.sleep(1)
    return False

async def process_product(product, session, semaphore):
    pid = product.get("handle", product.get("id", "unknown"))
    urls_to_download = set()
    
    if product.get("featured_image"):
        urls_to_download.add(product["featured_image"])
    
    if product.get("images"):
        for img in product["images"]:
            urls_to_download.add(img)
            
    if product.get("variants"):
        for var in product["variants"]:
            img_obj = var.get("featured_image")
            if img_obj and isinstance(img_obj, dict) and img_obj.get("src"):
                urls_to_download.add(img_obj["src"])
                
    tasks = []
    idx = 0
    url_to_rel_path = {}
    for url in urls_to_download:
        ext = get_ext(url)
        filename = f"{pid}_{idx}{ext}"
        save_path = os.path.join(IMAGE_DIR, filename)
        rel_path = f"images/{filename}"
        url_to_rel_path[url] = rel_path
        idx += 1
        tasks.append(download_image(session, url, save_path, semaphore))
        
    if tasks:
        await asyncio.gather(*tasks)
        
    if product.get("featured_image") in url_to_rel_path:
        product["featured_image"] = url_to_rel_path[product["featured_image"]]
        
    if product.get("images"):
        new_images = []
        for img in product["images"]:
            if img in url_to_rel_path:
                new_images.append(url_to_rel_path[img])
            else:
                new_images.append(img)
        product["images"] = new_images
        
    if product.get("variants"):
        for var in product["variants"]:
            img_obj = var.get("featured_image")
            if img_obj and isinstance(img_obj, dict) and img_obj.get("src") in url_to_rel_path:
                var["featured_image"]["src"] = url_to_rel_path[img_obj["src"]]

async def main():
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.replace(".json", "_local.json")
    else:
        input_path = INPUT_FILE
        output_path = OUTPUT_FILE
        
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    is_list = isinstance(data, list)
    products = data if is_list else [data]
    
    semaphore = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        tasks = [process_product(p, session, semaphore) for p in products]
        print(f"[*] Bắt đầu tải ảnh cho {len(tasks)} sản phẩm...")
        await asyncio.gather(*tasks)
        
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(products if is_list else products[0], f, ensure_ascii=False, indent=4)
    print(f"[*] Hoàn tất thay thế URL ảnh. Đã lưu tại: {output_path}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
