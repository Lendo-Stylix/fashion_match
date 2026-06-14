import os
import json
import sys
import urllib.request
import ssl
import time
from typing import Dict, List, Any

# Ensure output is UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_INPUT_FILE = os.path.join(BASE_DIR, "../../discovery/canifa/output/scraped_products.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "canifa_products_full.json")
NUXT_DATA_FILE = "C:/Users/hi/.gemini/antigravity-ide/brain/67c5ae17-ad4d-4262-8ea8-9f671978a0ca/scratch/nuxt_data.json"

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global Option Maps
global_color_map = {}
global_size_map = {}
global_sex_map = {}

def load_global_metadata():
    global global_color_map, global_size_map, global_sex_map
    if not os.path.exists(NUXT_DATA_FILE):
        return
    try:
        with open(NUXT_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = data.get("pinia", {}).get("customAttributeMetadata", {}).get("customAttributeMetadata", [])
        for attr in metadata:
            code = attr.get("attribute_code")
            options = attr.get("attribute_options") or []
            if code == "color":
                for opt in options:
                    global_color_map[str(opt.get("value"))] = opt.get("label")
            elif code == "size":
                for opt in options:
                    global_size_map[str(opt.get("value"))] = opt.get("label")
            elif code == "sex":
                for opt in options:
                    global_sex_map[str(opt.get("value"))] = opt.get("label")
    except Exception:
        pass

def fetch_products(offset, size=100):
    url = "https://canifa.com/v1/middleware/search_product"
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    payload = {
        "indexName": "vue_storefront_catalog_2",
        "query": {
            "query": {
                "bool": {
                    "filter": {
                        "bool": {
                            "must": [
                                {"terms": {"visibility": [2, 3, 4]}},
                                {"terms": {"status": [0, 1]}}
                            ]
                        }
                    }
                }
            }
        },
        "groupToken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJncm91cF9pZCI6MSwiaWQiOjMsInVzZXIiOiJ2YW5kQGdtYWlsLmNvbSJ9.VMNebCbNSLF8xlyoG4qcaWlP21OFgcXJR3Ak2C0Oyac",
        "queryParams": {"from": offset, "size": size, "sort": ""}
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None

def should_skip_product(p):
    categories = p.get("categories_map") or []
    cat_names = [c.get("name", "").lower() for c in categories if isinstance(c, dict)]
    sku = (p.get("sku") or "").lower()
    url_key = (p.get("url_key") or "").lower()
    name = (p.get("name") or "").lower()
    
    # 1. Check Kids (Bé trai, Bé gái, Trẻ em, sơ sinh)
    is_kid = False
    if any(x in url_key for x in ["be-trai", "be-gai", "tre-em", "so-sinh", "boy", "girl"]):
        is_kid = True
    if any(x in name for x in ["bé trai", "bé gái", "trẻ em", "sơ sinh"]):
        is_kid = True
    if any(x in c for c in cat_names for x in ["bé trai", "bé gái", "trẻ em", "sơ sinh", "boy", "girl"]):
        is_kid = True
    if sku.startswith("2") or sku.startswith("7"):
        is_kid = True
        
    if is_kid:
        return True
        
    # 2. Check Underwear (Đồ lót)
    is_underwear = False
    if any(x in url_key for x in ["do-lot", "quan-lot", "ao-lot", "sip", "sịp", "boxer", "panties", "bra"]):
        is_underwear = True
    if any(x in name for x in ["đồ lót", "quần lót", "áo lót", "sịp", "quần sịp", "áo ngực", "bra", "boxer"]):
        is_underwear = True
    if any(x in c for c in cat_names for x in ["đồ lót", "quần lót", "áo lót", "sịp", "bra"]):
        is_underwear = True
        
    # Exceptions to Keep: Đồ bơi (swimwear), Tất, Vớ (socks)
    is_swimwear = "bơi" in name or "swim" in name or "bơi" in url_key or "swim" in url_key or any("bơi" in c or "swim" in c for c in cat_names)
    is_socks = "tất" in name or "vớ" in name or "tat" in url_key or "vo" in url_key or any("tất" in c or "vớ" in c or "tat" in c for c in cat_names)
    
    if is_underwear and not (is_swimwear or is_socks):
        return True
        
    # 3. Check Towels (khăn mặt, khăn tắm) to skip
    is_towel = False
    if any(x in name for x in ["khăn mặt", "khăn tắm", "khăn lau", "tắm", "khăn bông"]):
        if not any(y in name for y in ["quàng", "choàng", "cổ"]):
            is_towel = True
    if any(x in url_key for x in ["khan-mat", "khan-tam", "khan-lau", "khan-bong"]):
        if not any(y in url_key for y in ["quang", "choang", "co"]):
            is_towel = True
    if any("khăn tắm" in c or "khăn mặt" in c for c in cat_names):
        is_towel = True
        
    if is_towel:
        return True
        
    return False

def make_absolute_image_url(path: str) -> str:
    if not path:
        return ""
    path = path.strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("/"):
        return "https://media.canifa.com/catalog/product" + path
    return "https://media.canifa.com/catalog/product/" + path

def main():
    print("=" * 60)
    print("[CANIFA] HARVESTER STARTING (WITH FILTERS)")
    print("=" * 60)
    
    load_global_metadata()
    if not os.path.exists(DISCOVERY_INPUT_FILE):
        print(f"[!] Discovery file not found: {DISCOVERY_INPUT_FILE}")
        return
        
    with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
        discovery_map = json.load(f)
        
    url_to_category = {}
    for cat_group, urls in discovery_map.items():
        for url in urls:
            url_to_category[url] = cat_group
            
    print(f"[*] Loaded {len(url_to_category)} discovered URLs.")
    
    existing_skus = set()
    existing_data = []
    
    print("[*] Rebuilding output file with filtered products only...")
    
    offset = 0
    size = 100
    total_harvested = 0
    
    while True:
        data = fetch_products(offset, size)
        if not data or "hits" not in data or "hits" not in data["hits"]:
            print(f"[!] No response or empty data at offset {offset}")
            break
            
        hits_obj = data["hits"]
        total_count = hits_obj.get("total", {}).get("value", 0)
        products = hits_obj.get("hits", [])
        
        if not products:
            print(f"[*] No more products found at offset {offset}")
            break
            
        print(f"  - Processing offset {offset} (Found {len(products)} products)...")
        
        for p_hit in products:
            p = p_hit.get("_source")
            if not p:
                continue
                
            sku = p.get("sku")
            url_key = p.get("url_key")
            if not url_key or not sku:
                continue
                
            # Filter out kids' products and underwear (except swimwear and socks)
            if should_skip_product(p):
                continue
                
            if sku in existing_skus:
                continue
                
            product_url = f"https://canifa.com/{url_key}"
            if product_url not in url_to_category:
                clean_url = product_url.split("?")[0]
                if clean_url not in url_to_category:
                    continue
            category_group = url_to_category.get(product_url) or url_to_category.get(product_url.split("?")[0])
            
            color_map = global_color_map.copy()
            size_map = global_size_map.copy()
            for opt in p.get("configurable_options_map") or []:
                attr_code = opt.get("attribute_code")
                values = opt.get("values") or []
                if attr_code == "color":
                    for v in values:
                        color_map[str(v.get("value_index"))] = v.get("label")
                elif attr_code == "size":
                    for v in values:
                        size_map[str(v.get("value_index"))] = v.get("label")
            
            variants = []
            child_prices = []
            total_stock = 0
            for child in p.get("configurable_children") or []:
                child_price = float(child.get("final_price") or p.get("final_price") or 0)
                child_reg_price = float(child.get("regular_price") or p.get("regular_price") or 0)
                child_compare = child_reg_price if child_reg_price > child_price else None
                color_id = str(child.get("color"))
                size_id = str(child.get("size"))
                color_label = color_map.get(color_id) or f"Color-{color_id}"
                size_label = size_map.get(size_id) or f"Size-{size_id}"
                v_title = f"{color_label} / {size_label}"
                v_img = make_absolute_image_url(child.get("image") or p.get("thumbnail_url"))
                qty = float(child.get("logistic_qty") or 0)
                total_stock += qty
                
                child_data = {
                    "id": int(child.get("id")),
                    "sku": child.get("sku") or f"{sku}_{child.get('id')}",
                    "title": v_title,
                    "option1": color_label,
                    "option2": size_label,
                    "price": child_price,
                    "compare_at_price": child_compare,
                    "available": qty > 0,
                    "inventory_quantity": qty,
                    "featured_image": v_img,
                    "specifications": {
                        "Chất liệu": p.get("materials", "").strip(),
                        "Hướng dẫn sử dụng": p.get("instruction", "").strip()
                    }
                }
                variants.append(child_data)
                child_prices.append(child_price)
            
            parent_price = float(p.get("final_price") or 0)
            parent_reg_price = float(p.get("regular_price") or 0)
            compare_price = parent_reg_price if parent_reg_price > parent_price else None
            price_min = min(child_prices) if child_prices else parent_price
            price_max = max(child_prices) if child_prices else parent_price
            
            images = []
            for img_obj in p.get("media_gallery") or []:
                img_path = img_obj.get("image")
                if img_path:
                    abs_url = make_absolute_image_url(img_path)
                    if abs_url and abs_url not in images:
                        images.append(abs_url)
            thumb = make_absolute_image_url(p.get("thumbnail_url"))
            if thumb and thumb not in images:
                images.insert(0, thumb)
            featured_image = images[0] if images else ""
            
            materials = (p.get("materials") or "").strip()
            instruction = (p.get("instruction") or "").strip()
            desc_parts = []
            desc_html_parts = []
            if materials:
                desc_parts.append(f"Chất liệu: {materials}")
                desc_html_parts.append(f"<p><strong>Chất liệu:</strong> {materials}</p>")
            if instruction:
                desc_parts.append(f"Hướng dẫn sử dụng:\n{instruction}")
                inst_br = instruction.replace("\r\n", "<br>").replace("\n", "<br>")
                desc_html_parts.append(f"<p><strong>Hướng dẫn sử dụng:</strong><br>{inst_br}</p>")
            description = "\n\n".join(desc_parts)
            description_html = "".join(desc_html_parts)
            
            product_data = {
                "id": int(p.get("id")),
                "handle": url_key,
                "title": p.get("name") or p.get("meta_title") or url_key,
                "vendor": "Canifa",
                "type": category_group,
                "description": description,
                "description_html": description_html,
                "available": total_stock > 0 if variants else p.get("is_in_stock", True),
                "tags": [c.get("name") for c in p.get("categories_map") or [] if isinstance(c, dict)],
                "url": product_url,
                "_scraped_category": category_group,
                "_scraped_url": product_url,
                "price": parent_price,
                "price_min": price_min,
                "price_max": price_max,
                "compare_at_price": compare_price,
                "images": images,
                "featured_image": featured_image,
                "options": ["Màu sắc", "Kích thước"],
                "specifications": {
                    "Chất liệu": materials,
                    "Hướng dẫn sử dụng": instruction
                },
                "variants": variants
            }
            existing_data.append(product_data)
            existing_skus.add(sku)
            total_harvested += 1
            
        # Save batch incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
        if len(products) < size:
            print(f"[*] Harvest completed. Processed all active products.")
            break
            
        offset += size
        time.sleep(0.5)
        
    print("\n" + "="*50)
    print("🏆 CANIFA HARVEST COMPLETED!")
    print(f"Total unique products harvested in this run: {total_harvested}")
    print(f"Total accumulated products: {len(existing_data)}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
