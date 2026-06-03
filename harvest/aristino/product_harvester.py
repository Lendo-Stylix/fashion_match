import os
import json
import re
import sys
import asyncio
import aiohttp
from typing import Dict, List, Any

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/aristino/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "aristino_products_full.json")

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def fetch_product_data(session: aiohttp.ClientSession, url: str, category: str, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    max_retries = 5
    for attempt in range(max_retries):
        async with semaphore:
            try:
                # Add delay between requests
                await asyncio.sleep(0.5)
                async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    if response.status == 429:
                        wait_time = (2 ** attempt) + 1
                        print(f"[!] Lỗi 429 (Too Many Requests) khi tải {url}. Chờ {wait_time}s rồi thử lại (Lần {attempt+1}/{max_retries})...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status != 200:
                        print(f"[!] Lỗi {response.status} khi tải: {url}")
                        return {"url": url, "category": category, "error": f"HTTP {response.status}"}
                    
                    html = await response.text()
                    
                    # Extract the productDetail JSON data using regex
                    match = re.search(r'window\.productDetail\s*=\s*{\s*data:\s*({.*?})\s*,\s*id:', html, re.DOTALL)
                    
                    if not match:
                        match = re.search(r'productjson:\s*({.*?}),\n\s*template_suffix', html, re.DOTALL)
                        
                    if match:
                        try:
                            product_data = json.loads(match.group(1))
                            product_data['_scraped_category'] = category
                            product_data['_scraped_url'] = url
                            return product_data
                        except json.JSONDecodeError:
                            print(f"[!] Lỗi parse JSON cho URL: {url}")
                            return {"url": url, "category": category, "error": "JSONDecodeError"}
                    else:
                        print(f"[!] Không tìm thấy cấu trúc dữ liệu JSON cho URL: {url}")
                        return {"url": url, "category": category, "error": "No product data found in HTML"}
            except Exception as e:
                print(f"[!] Lỗi Exception {e} cho URL: {url}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"url": url, "category": category, "error": str(e)}
    
    return {"url": url, "category": category, "error": "Max retries exceeded for 429"}

async def main():
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Không tìm thấy file đầu vào: {DISCOVERY_INPUT_FILE}")
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
            print(f"[*] Đã tải {len(existing_urls)} sản phẩm từ lần chạy trước.")
        except json.JSONDecodeError:
            pass

    tasks = []
    # Limit concurrency to 5 to avoid being blocked
    semaphore = asyncio.Semaphore(5) 
    
    # Chuẩn bị danh sách URLs cần cào
    items_to_scrape = []
    for category, urls in category_map.items():
        for url in urls:
            if url not in existing_urls:
                items_to_scrape.append({"category": category, "url": url})
            
    print(f"[*] Tổng số sản phẩm cần thu thập thêm: {len(items_to_scrape)}")
    
    if len(items_to_scrape) == 0:
        print("[*] Không còn sản phẩm nào cần thu thập. Hoàn tất!")
        return

    async with aiohttp.ClientSession() as session:
        for item in items_to_scrape:
            tasks.append(fetch_product_data(session, item["url"], item["category"], semaphore))
            
        print("[*] Đang thu thập dữ liệu hàng loạt. Vui lòng đợi...")
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if "error" not in r]
    error_results = [r for r in results if "error" in r]
    
    print(f"[*] Thu thập hoàn tất đợt này! Thành công: {len(valid_results)}, Lỗi: {len(error_results)}")
    
    # Merge
    existing_data.extend(valid_results)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Đã lưu tổng cộng {len(existing_data)} sản phẩm vào: {OUTPUT_FILE}")

if __name__ == "__main__":
    # Workaround cho Windows (nếu có lỗi EventLoop)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
