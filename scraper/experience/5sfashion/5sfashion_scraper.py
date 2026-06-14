"""
5S Fashion (5sfashion.vn) Consolidated Scraper
==============================================
Platform: Laravel Backend with custom AJAX filter API
API URL: https://5sfashion.vn/filter?category={id}&page={page}

This script executes both phases sequentially:
1. Discovery Phase: Scrapes category pages using AJAX to discover unique PDP URLs and map variant IDs to SKUs.
2. Harvest Phase: Asynchronously parses details for each discovered URL (Title, Price, Options, Variants, Specs, Images).
"""

import os
import json
import sys
import re
import asyncio
import aiohttp
import urllib.request
import urllib.error
import ssl
import time
from datetime import datetime
from bs4 import BeautifulSoup

# Windows event loop policy
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DISCOVERY_FILE = os.path.join(OUTPUT_DIR, "scraped_products.json")
HARVEST_FILE = os.path.join(OUTPUT_DIR, "5sfashion_products_full.json")

SITE_BASE = "https://5sfashion.vn"
VENDOR = "5S Fashion"
DELAY_DISCOVERY = 0.5
DELAY_HARVEST = 0.3
CONCURRENCY_LIMIT = 5

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

CATEGORIES = [
    {"id": "11", "name": "Áo Thun Nam", "parent": "Nam"},
    {"id": "12", "name": "Áo Polo Nam", "parent": "Nam"},
    {"id": "13", "name": "Áo Sơ Mi Nam", "parent": "Nam"},
    {"id": "15", "name": "Áo Chống Nắng Nam", "parent": "Nam"},
    {"id": "16", "name": "Áo Thun Dài Tay Nam", "parent": "Nam"},
    {"id": "17", "name": "Áo Nỉ Nam", "parent": "Nam"},
    {"id": "19", "name": "Áo Len Nam", "parent": "Nam"},
    {"id": "18", "name": "Áo Khoác Nam", "parent": "Nam"},
    {"id": "21", "name": "Áo Bomber Nam", "parent": "Nam"},
    {"id": "69", "name": "Áo Khoác Gió Nam", "parent": "Nam"},
    {"id": "70", "name": "Áo Phao Nam", "parent": "Nam"},
    {"id": "61", "name": "Áo Vest - Áo Blazer Nam", "parent": "Nam"},
    {"id": "24", "name": "Quần Short Thể Thao Nam", "parent": "Nam"},
    {"id": "25", "name": "Quần Short Kaki Nam", "parent": "Nam"},
    {"id": "26", "name": "Quần Short Tây Nam", "parent": "Nam"},
    {"id": "55", "name": "Quần Short Casual Nam", "parent": "Nam"},
    {"id": "27", "name": "Quần Dài Thể Thao Nam", "parent": "Nam"},
    {"id": "28", "name": "Quần Dài Kaki Nam", "parent": "Nam"},
    {"id": "29", "name": "Quần Tây Nam", "parent": "Nam"},
    {"id": "30", "name": "Quần Jeans Nam", "parent": "Nam"},
    {"id": "33", "name": "Tất Nam", "parent": "Nam"},
    {"id": "72", "name": "Bộ Nỉ Nam", "parent": "Nam"},
    {"id": "73", "name": "Bộ Thể Thao Nam", "parent": "Nam"},
    {"id": "74", "name": "Bộ Vest Nam", "parent": "Nam"},
    {"id": "185", "name": "Bộ Đồ Polo Nam", "parent": "Nam"},
    {"id": "186", "name": "Bộ Đồ T-shirt Nam", "parent": "Nam"},
    {"id": "187", "name": "Bộ Sơ Mi Cộc Tay Nam", "parent": "Nam"},
    
    {"id": "101", "name": "Áo Thun Nữ", "parent": "Nữ"},
    {"id": "102", "name": "Áo Sơ Mi Nữ", "parent": "Nữ"},
    {"id": "103", "name": "Áo Len Nữ", "parent": "Nữ"},
    {"id": "104", "name": "Áo Nỉ Nữ", "parent": "Nữ"},
    {"id": "105", "name": "Áo Giữ Nhiệt Nữ", "parent": "Nữ"},
    {"id": "107", "name": "Áo Phao Nữ", "parent": "Nữ"},
    {"id": "168", "name": "Áo Gió Nữ", "parent": "Nữ"},
    {"id": "108", "name": "Áo Khoác Thời Trang Nữ", "parent": "Nữ"},
    {"id": "109", "name": "Áo Bomber Nữ", "parent": "Nữ"},
    {"id": "174", "name": "Áo Chống Nắng Nữ", "parent": "Nữ"},
    {"id": "172", "name": "Áo Polo Nữ", "parent": "Nữ"},
    {"id": "183", "name": "Áo Tank Top Nữ", "parent": "Nữ"},
    {"id": "111", "name": "Quần Âu Nữ", "parent": "Nữ"},
    {"id": "112", "name": "Quần Jeans Nữ", "parent": "Nữ"},
    {"id": "113", "name": "Quần Khác Nữ", "parent": "Nữ"},
    {"id": "180", "name": "Quần Short Nữ", "parent": "Nữ"},
    {"id": "115", "name": "Chân Váy Nữ", "parent": "Nữ"},
    {"id": "114", "name": "Váy Nữ", "parent": "Nữ"},
    {"id": "117", "name": "Tất Chân Nữ", "parent": "Nữ"},
    {"id": "119", "name": "Bộ Đồ Gió Nữ", "parent": "Nữ"},
    {"id": "120", "name": "Bộ Mặc Nhà Nữ", "parent": "Nữ"},
    {"id": "121", "name": "Bộ Nỉ Nữ", "parent": "Nữ"},
    {"id": "173", "name": "Bộ Đồ Mùa Hè Nữ", "parent": "Nữ"}
]

EXCLUDE_KEYWORDS = [
    "bé trai", "bé gái", "trẻ em", "sơ sinh", "em bé", "kids", "baby", "boy", "girl",
    "giày", "dép", "sandal", "sneaker", "boots", "loafer", "shoes", "slipon",
    "đồ lót", "quần lót", "áo lót", "áo ngực", "quần sịp", "sịp", "boxer", "panties", "bra", "underwear",
    "mỹ phẩm", "trang điểm", "makeup", "cosmetics", "son môi", "kem dưỡng", "sữa tắm", "dầu gội", "nước hoa"
]

def is_excluded(title: str, url: str) -> bool:
    title_l = title.lower()
    url_l = url.lower()
    
    # Exceptions
    if "bơi" in title_l or "swim" in title_l or "vớ" in title_l or "tất" in title_l or "socks" in title_l:
        return False
        
    for kw in EXCLUDE_KEYWORDS:
        if kw in title_l or kw in url_l:
            if kw in ["baby", "boy", "girl", "kids", "bra"]:
                if re.search(r'\b' + kw + r'\b', title_l) or re.search(r'\b' + kw + r'\b', url_l):
                    return True
            else:
                return True
    return False

def clean_price(price_str):
    if not price_str:
        return 0.0
    clean = re.sub(r'\D', '', price_str)
    return float(clean) if clean else 0.0

def run_discovery():
    print("=" * 60)
    print("🚀 PHASE 1: DISCOVERY PHASING STARTING")
    print("=" * 60)
    
    results = {"categories": {}, "variant_sku_map": {}}
    seen_urls = set()
    
    if os.path.exists(DISCOVERY_FILE):
        try:
            with open(DISCOVERY_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
            for cat, urls in results.get("categories", {}).items():
                for u in urls:
                    seen_urls.add(u)
            print(f"Loaded {len(seen_urls)} existing URLs. Resuming discovery...")
        except Exception:
            pass

    for idx, cat in enumerate(CATEGORIES):
        name = cat["name"]
        cat_id = cat["id"]
        print(f"[{idx+1}/{len(CATEGORIES)}] Scanning: {name} (ID: {cat_id})...")
        
        if name not in results["categories"]:
            results["categories"][name] = []
            
        page = 1
        while True:
            url = f"{SITE_BASE}/filter?category={cat_id}&page={page}"
            req = urllib.request.Request(url, headers=HEADERS)
            content = None
            
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode('utf-8'))
                            content = data.get("content", "")
                            break
                        elif resp.status == 429:
                            time.sleep(2 ** attempt + 1)
                except Exception:
                    time.sleep(1)
                    
            if not content:
                break
                
            soup = BeautifulSoup(content, "html.parser")
            product_cards = soup.select(".item-product")
            if not product_cards:
                break
                
            page_added = 0
            for card in product_cards:
                a_link = card.select_one("a[href*='/san-pham/']")
                if not a_link:
                    continue
                href = a_link["href"]
                if href.startswith("/"):
                    href = SITE_BASE + href
                href = href.split("?")[0]
                
                title_el = card.select_one(".name-product") or card.select_one(".name")
                title = title_el.text.strip() if title_el else ""
                
                if is_excluded(title, href):
                    continue
                    
                if href not in seen_urls:
                    results["categories"][name].append(href)
                    seen_urls.add(href)
                    page_added += 1
                    
                for inp in card.find_all("input", type="hidden"):
                    v_id = inp.get("data-id")
                    v_sku = inp.get("data-sku")
                    if v_id and v_sku:
                        results["variant_sku_map"][str(v_id)] = v_sku
                        
            print(f"  - Page {page}: added {page_added} product URLs.")
            if len(product_cards) < 12:
                break
            page += 1
            time.sleep(DELAY_DISCOVERY)
            
        with open(DISCOVERY_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    print(f"\n[✓] Discovery finished! Discovered {len(seen_urls)} products.")
    return results

async def harvest_pdp_url(session, url, category_name, variant_sku_map, sem):
    async with sem:
        await asyncio.sleep(DELAY_HARVEST)
        try:
            async with session.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, ssl=ctx, timeout=15) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        except Exception:
            return None
            
        try:
            soup = BeautifulSoup(html, "html.parser")
            title_el = soup.find("h1")
            if not title_el:
                return None
            title = title_el.text.strip()
            handle = url.split("/")[-1]
            
            base_sku = ""
            words = title.split()
            if words:
                last_word = words[-1]
                if re.search(r'[a-zA-Z0-9]+', last_word):
                    base_sku = last_word
            
            # Options mapping
            colors = []
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
                            img_url = img_url.replace("/fast/69x0/", "/fast/1325x0/").replace("/fast/180x0/", "/fast/1325x0/")
                    if c_name and c_id:
                        colors.append({"name": c_name, "id": c_id, "image": img_url})
                        
            sizes = []
            size_container = soup.find(class_="variant-size")
            if size_container:
                for li in size_container.find_all("li"):
                    s_name = li.get("data-size")
                    s_id = li.get("data-size-id")
                    if s_name and s_id:
                        sizes.append({"name": s_name, "id": s_id})
                        
            # Variants
            variants = []
            prices = []
            compare_prices = []
            for c in colors:
                for s in sizes:
                    cls_name = f"{c['id']}-{s['id']}"
                    inp = soup.find("input", class_=cls_name)
                    if inp:
                        v_id = inp.get("data-id")
                        inv = int(inp.get("data-inventory", 0))
                        p_val = clean_price(inp.get("data-price-promotion") or inp.get("data-price"))
                        c_val = clean_price(inp.get("data-price"))
                        
                        if p_val:
                            prices.append(p_val)
                        if c_val > p_val:
                            compare_prices.append(c_val)
                            
                        sku_val = variant_sku_map.get(str(v_id)) or f"{base_sku}-{c['name']}-{s['name']}"
                        variants.append({
                            "id": str(v_id),
                            "sku": sku_val,
                            "title": f"{title} - {c['name']} - Size {s['name']}",
                            "option1": c["name"],
                            "option2": s["name"],
                            "price": p_val,
                            "compare_at_price": c_val if c_val > p_val else None,
                            "available": inv > 0,
                            "inventory_quantity": inv,
                            "images": [c["image"]] if c["image"] else []
                        })
                        
            if not variants:
                return None
                
            p_min = min(prices) if prices else 0.0
            p_max = max(prices) if prices else 0.0
            comp_price = max(compare_prices) if compare_prices else None
            disc = int(round((comp_price - p_min) / comp_price * 100)) if comp_price and p_min and comp_price > p_min else 0
            
            # Specs and Desc
            specs = {"Mã sản phẩm": base_sku, "Chất liệu": "", "Form dáng": "", "Họa tiết": "", "Màu sắc": ", ".join([c["name"] for c in colors]), "Xuất xứ": "Việt Nam"}
            content_desc = soup.select_one(".content-desc")
            desc = ""
            if content_desc:
                desc = content_desc.text.strip()
                lines = [l.strip() for l in desc.split("\n") if l.strip()]
                mat_list, fit_list, design_list = [], [], []
                for line in lines:
                    line_clean = re.sub(r'^[-*•\s]+', '', line).strip()
                    line_lower = line_clean.lower()
                    if line.startswith(('-', '*', '•')) or '%' in line:
                        if ('%' in line or any(x in line_lower for x in ["cotton", "spandex", "polyester", "bamboo", "bông"])) and not any(x in line_lower for x in ["phom", "form", "dáng", "thiết kế"]):
                            if len(line_clean) < 150:
                                mat_list.append(line_clean)
                    if any(x in line_lower for x in ["phom dáng", "form dáng", "slimfit", "regular", "relaxed"]):
                        if len(line_clean) < 200:
                            fit_list.append(line_clean)
                    if line.startswith(('-', '*', '•')):
                        if any(x in line_lower for x in ["thiết kế", "họa tiết", "trơn basic", "in logo"]):
                            if len(line_clean) < 200:
                                design_list.append(line_clean)
                                
                if mat_list: specs["Chất liệu"] = "; ".join(mat_list[:3])
                if fit_list: specs["Form dáng"] = fit_list[0]
                if design_list: specs["Họa tiết"] = design_list[0]
                
            # Images
            slider_imgs = []
            slider = soup.select_one(".slider-main") or soup.select_one(".slider-thumb")
            if slider:
                for img in slider.find_all("img"):
                    src = img.get("data-src") or img.get("src")
                    if src and not src.startswith("data:"):
                        if src.startswith("//"): src = "https:" + src
                        elif src.startswith("/"): src = SITE_BASE + src
                        src = src.replace("/fast/69x0/", "/fast/1325x0/").replace("/fast/180x0/", "/fast/1325x0/")
                        if src not in slider_imgs: slider_imgs.append(src)
                        
            f_img = slider_imgs[0] if slider_imgs else (colors[0]["image"] if colors else "")
            p_cat = "Nữ" if "nữ" in category_name.lower() else "Nam"
            
            return {
                "id": str(variants[0]["id"]),
                "handle": handle,
                "title": title,
                "vendor": VENDOR,
                "type": category_name,
                "parent_category": p_cat,
                "description": desc,
                "available": any(v["available"] for v in variants),
                "url": url,
                "_scraped_category": category_name,
                "_scraped_url": url,
                "price": p_min,
                "price_min": p_min,
                "price_max": p_max,
                "compare_at_price": comp_price,
                "discount_percent": disc,
                "images": slider_imgs,
                "featured_image": f_img,
                "options": {"colors": [c["name"] for c in colors], "sizes": [s["name"] for s in sizes]},
                "specifications": specs,
                "tags": [category_name, VENDOR],
                "variants": variants,
                "_scraped_at": datetime.now().isoformat()
            }
        except Exception:
            return None

async def run_harvest(discovery_data):
    print("=" * 60)
    print("🚀 PHASE 2: HARVESTING STARTING")
    print("=" * 60)
    
    discovery_map = discovery_data.get("categories", {})
    variant_sku_map = discovery_data.get("variant_sku_map", {})
    
    url_to_category = {}
    for cat, urls in discovery_map.items():
        for u in urls:
            url_to_category[u] = cat
            
    harvested = []
    seen = set()
    if os.path.exists(HARVEST_FILE):
        try:
            with open(HARVEST_FILE, "r", encoding="utf-8") as f:
                harvested = json.load(f)
            for p in harvested:
                seen.add(p["_scraped_url"])
            print(f"Loaded {len(harvested)} existing harvested products. Resuming...")
        except Exception:
            pass
            
    todo = [u for u in url_to_category.keys() if u not in seen]
    print(f"Remaining PDP URLs to harvest: {len(todo)}")
    if not todo:
        print("[✓] Harvest already complete!")
        return
        
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    async with aiohttp.ClientSession() as session:
        tasks = [harvest_pdp_url(session, u, url_to_category[u], variant_sku_map, sem) for u in todo]
        results = await asyncio.gather(*tasks)
        
        new_items = [item for item in results if item]
        harvested.extend(new_items)
        
        with open(HARVEST_FILE, "w", encoding="utf-8") as f:
            json.dump(harvested, f, ensure_ascii=False, indent=2)
            
    total_vars = sum(len(p.get("variants", [])) for p in harvested)
    print("\n" + "=" * 60)
    print("🏆 5S FASHION HARVEST COMPLETE!")
    print(f"Harvested in this run    : {len(new_items)} products")
    print(f"Total unique products    : {len(harvested)}")
    print(f"Total variants           : {total_vars}")
    print(f"Output saved to          : {HARVEST_FILE}")
    print("=" * 60)

def main():
    discovery_data = run_discovery()
    asyncio.run(run_harvest(discovery_data))

if __name__ == "__main__":
    main()
