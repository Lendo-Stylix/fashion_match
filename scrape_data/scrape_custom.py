import os
import sys
import csv
import json
import time
import random
import uuid
import requests
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.schemas import CatalogItem
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# Định nghĩa thứ tự cột theo yêu cầu Phase 1B — Catalog Encoder Schema
CSV_FIELDNAMES = [
    "item_ID", "image_path", "brand", "gender", 
    "category1", "category2", "category3", 
    "short_text", "detailed_text", 
    "dominant_color", "pattern", "material", "fit_type", 
    "neckline", "sleeve_length", "bottom_length", 
    "season", "style_tags", 
    "source", "split", "is_manually_labeled"
]

VALID_CATEGORY1 = {"tops", "bottoms", "outerwear", "dresses", "shoes", "bags", "accessories"}
BROAD_COLLECTION_SLUGS = {
    "nam",
    "nu",
    "do-nam",
    "do-nu",
    "thoi-trang-nam",
    "thoi-trang-nu",
    "ao-nam",
    "ao-nu",
    "quan-nam",
    "quan-nu",
}

# Từ điển ánh xạ từ khóa giao diện sang chuẩn Taxonomy của dự án
# =========================================================================
# OUTFITMATCH - PRODUCTION TAXONOMY MAP (VN & INTL MARKET OPTIMIZED)
# =========================================================================

TAXONOMY_MAP = {
    # ================= TOPS (Áo) =================
    "áo thun": {"cat1": "tops", "cat2": "t-shirts", "material": "cotton", "neckline": "crew"},
    "áo phông": {"cat1": "tops", "cat2": "t-shirts", "material": "cotton", "neckline": "crew"},
    "áo polo": {"cat1": "tops", "cat2": "t-shirts", "cat3": "polo", "neckline": "collared"},
    "áo sơ mi": {"cat1": "tops", "cat2": "shirts", "neckline": "collared"},
    "áo kiểu": {"cat1": "tops", "cat2": "blouses"}, # Rất phổ biến ở shop đồ nữ VN
    "áo blouse": {"cat1": "tops", "cat2": "blouses", "style_tags": "office;formal"},
    "áo croptop": {"cat1": "tops", "cat2": "t-shirts", "cat3": "crop_top"},
    "áo tank top": {"cat1": "tops", "cat2": "t-shirts", "cat3": "tank_top", "sleeve_length": "sleeveless"},
    "áo ba lỗ": {"cat1": "tops", "cat2": "t-shirts", "cat3": "tank_top", "sleeve_length": "sleeveless"},
    "áo hai dây": {"cat1": "tops", "cat2": "camisoles", "sleeve_length": "sleeveless"},
    "áo 2 dây": {"cat1": "tops", "cat2": "camisoles", "sleeve_length": "sleeveless"},
    "áo ống": {"cat1": "tops", "cat2": "tube_tops", "sleeve_length": "sleeveless", "neckline": "off_shoulder"},
    "áo trễ vai": {"cat1": "tops", "cat2": "blouses", "neckline": "off_shoulder"},
    "áo sweater": {"cat1": "tops", "cat2": "sweaters", "sleeve_length": "long"},
    "áo len": {"cat1": "tops", "cat2": "sweaters", "material": "knit"},
    "áo nỉ": {"cat1": "tops", "cat2": "hoodies", "material": "fleece"},
    "áo hoodie": {"cat1": "tops", "cat2": "hoodies", "neckline": "hooded"},
    
    # ================= OUTERWEAR (Áo khoác) =================
    "áo khoác": {"cat1": "outerwear", "cat2": "jackets"},
    "áo khoác gió": {"cat1": "outerwear", "cat2": "jackets", "cat3": "windbreaker"},
    "áo gió": {"cat1": "outerwear", "cat2": "jackets", "cat3": "windbreaker"},
    "áo khoác da": {"cat1": "outerwear", "cat2": "jackets", "material": "leather", "style_tags": "streetwear"},
    "áo khoác bò": {"cat1": "outerwear", "cat2": "jackets", "material": "denim"},
    "áo khoác jean": {"cat1": "outerwear", "cat2": "jackets", "material": "denim"},
    "áo khoác len": {"cat1": "outerwear", "cat2": "cardigans", "material": "knit"},
    "áo cardigan": {"cat1": "outerwear", "cat2": "cardigans", "material": "knit"},
    "áo blazer": {"cat1": "outerwear", "cat2": "blazers", "style_tags": "formal;office"},
    "áo vest": {"cat1": "outerwear", "cat2": "suits", "style_tags": "formal;office"},
    "áo măng tô": {"cat1": "outerwear", "cat2": "coats", "season": "winter"},
    "áo phao": {"cat1": "outerwear", "cat2": "puffer_jackets", "season": "winter"},
    "áo chống nắng": {"cat1": "outerwear", "cat2": "jackets", "cat3": "sun_protection"}, 
    
    # ================= BOTTOMS (Quần/Chân váy) =================
    "quần dài": {"cat1": "bottoms", "cat2": "trousers", "bottom_length": "full_length"},
    "quần tây": {"cat1": "bottoms", "cat2": "trousers", "style_tags": "formal;office", "bottom_length": "full_length"},
    "quần âu": {"cat1": "bottoms", "cat2": "trousers", "style_tags": "formal;office", "bottom_length": "full_length"},
    "quần suông": {"cat1": "bottoms", "cat2": "trousers", "fit_type": "relaxed", "bottom_length": "full_length"},
    "quần ống rộng": {"cat1": "bottoms", "cat2": "trousers", "fit_type": "relaxed", "bottom_length": "full_length"},
    "quần jean": {"cat1": "bottoms", "cat2": "jeans", "material": "denim"},
    "quần jeans": {"cat1": "bottoms", "cat2": "jeans", "material": "denim"},
    "quần bò": {"cat1": "bottoms", "cat2": "jeans", "material": "denim"},
    "quần kaki": {"cat1": "bottoms", "cat2": "trousers", "material": "khaki"},
    "quần túi hộp": {"cat1": "bottoms", "cat2": "cargo_pants", "style_tags": "streetwear"},
    "quần cargo": {"cat1": "bottoms", "cat2": "cargo_pants", "style_tags": "streetwear"},
    "quần jogger": {"cat1": "bottoms", "cat2": "joggers", "style_tags": "sport;casual"},
    "quần legging": {"cat1": "bottoms", "cat2": "leggings", "fit_type": "compression", "style_tags": "sport"},
    "quần short": {"cat1": "bottoms", "cat2": "shorts", "bottom_length": "knee"},
    "quần đùi": {"cat1": "bottoms", "cat2": "shorts", "bottom_length": "mini"},
    "quần sooc": {"cat1": "bottoms", "cat2": "shorts", "bottom_length": "mini"},
    "chân váy": {"cat1": "bottoms", "cat2": "skirts"},
    "chân váy xếp ly": {"cat1": "bottoms", "cat2": "skirts", "cat3": "pleated_skirt"},
    "chân váy chữ a": {"cat1": "bottoms", "cat2": "skirts", "cat3": "a_line_skirt"},
    "chân váy dài": {"cat1": "bottoms", "cat2": "skirts", "bottom_length": "midi"},
    "chân váy bò": {"cat1": "bottoms", "cat2": "skirts", "material": "denim"},
    "chân váy jean": {"cat1": "bottoms", "cat2": "skirts", "material": "denim"},
    
    # ================= DRESSES (Váy/Đầm nguyên bộ) =================
    "váy": {"cat1": "dresses", "cat2": "dresses"},
    "đầm": {"cat1": "dresses", "cat2": "dresses"},
    "váy hoa": {"cat1": "dresses", "cat2": "dresses", "pattern": "floral"},
    "đầm hoa": {"cat1": "dresses", "cat2": "dresses", "pattern": "floral"},
    "đầm dự tiệc": {"cat1": "dresses", "cat2": "dresses", "style_tags": "formal;party"},
    "đầm body": {"cat1": "dresses", "cat2": "dresses", "fit_type": "slim"},
    "đầm maxi": {"cat1": "dresses", "cat2": "dresses", "bottom_length": "maxi"},
    "váy maxi": {"cat1": "dresses", "cat2": "dresses", "bottom_length": "maxi"},
    "set trang phục": {"cat1": "dresses", "cat2": "sets", "cat3": "co-ord"},
    "set đồ": {"cat1": "dresses", "cat2": "sets", "cat3": "co-ord"},
    
    # ================= SHOES (Giày dép) =================
    "giày": {"cat1": "shoes", "cat2": "shoes"},
    "giày thể thao": {"cat1": "shoes", "cat2": "sneakers", "style_tags": "sport;casual"},
    "sneaker": {"cat1": "shoes", "cat2": "sneakers", "style_tags": "sport;casual"},
    "giày tây": {"cat1": "shoes", "cat2": "formal_shoes", "style_tags": "formal;office", "material": "leather"},
    "giày da nam": {"cat1": "shoes", "cat2": "formal_shoes", "style_tags": "formal;office", "material": "leather"},
    "giày cao gót": {"cat1": "shoes", "cat2": "heels", "style_tags": "formal;party"},
    "guốc": {"cat1": "shoes", "cat2": "heels"},
    "giày lười": {"cat1": "shoes", "cat2": "loafers", "style_tags": "casual;office"},
    "giày búp bê": {"cat1": "shoes", "cat2": "flats"},
    "bốt": {"cat1": "shoes", "cat2": "boots"},
    "boot": {"cat1": "shoes", "cat2": "boots"},
    "dép": {"cat1": "shoes", "cat2": "sandals"},
    "dép lê": {"cat1": "shoes", "cat2": "sandals"},
    "sandal": {"cat1": "shoes", "cat2": "sandals"},
    "xăng đan": {"cat1": "shoes", "cat2": "sandals"},
    "dép sục": {"cat1": "shoes", "cat2": "clogs"},
    "crocs": {"cat1": "shoes", "cat2": "clogs"},

    # ================= BAGS (Túi xách/Balo) =================
    "túi xách": {"cat1": "bags", "cat2": "handbags"},
    "túi": {"cat1": "bags", "cat2": "handbags"},
    "túi kẹp nách": {"cat1": "bags", "cat2": "shoulder_bags"}, # Trend Gen Z
    "túi đeo chéo": {"cat1": "bags", "cat2": "crossbody_bags"},
    "balo": {"cat1": "bags", "cat2": "backpacks"},
    "ba lô": {"cat1": "bags", "cat2": "backpacks"},
    "ví": {"cat1": "bags", "cat2": "wallets"},
    "bóp": {"cat1": "bags", "cat2": "wallets"},
    "túi tote": {"cat1": "bags", "cat2": "tote_bags", "material": "canvas"},
    "túi vải": {"cat1": "bags", "cat2": "tote_bags", "material": "canvas"},
    
    # ================= ACCESSORIES (Phụ kiện) =================
    "mũ": {"cat1": "accessories", "cat2": "hats"},
    "nón": {"cat1": "accessories", "cat2": "hats"},
    "mũ lưỡi trai": {"cat1": "accessories", "cat2": "hats", "cat3": "caps"},
    "nón lưỡi trai": {"cat1": "accessories", "cat2": "hats", "cat3": "caps"},
    "mũ bucket": {"cat1": "accessories", "cat2": "hats", "cat3": "bucket_hats"},
    "thắt lưng": {"cat1": "accessories", "cat2": "belts"},
    "dây nịt": {"cat1": "accessories", "cat2": "belts"},
    "kính": {"cat1": "accessories", "cat2": "eyewear"},
    "mắt kính": {"cat1": "accessories", "cat2": "eyewear"},
    "kính mát": {"cat1": "accessories", "cat2": "eyewear", "cat3": "sunglasses"},
    "kính râm": {"cat1": "accessories", "cat2": "eyewear", "cat3": "sunglasses"},
    "kính cận": {"cat1": "accessories", "cat2": "eyewear", "cat3": "optical_glasses"},
    "trang sức": {"cat1": "accessories", "cat2": "jewelry"},
    "vòng cổ": {"cat1": "accessories", "cat2": "jewelry", "cat3": "necklaces"},
    "dây chuyền": {"cat1": "accessories", "cat2": "jewelry", "cat3": "necklaces"},
    "bông tai": {"cat1": "accessories", "cat2": "jewelry", "cat3": "earrings"},
    "khuyên tai": {"cat1": "accessories", "cat2": "jewelry", "cat3": "earrings"},
    "nhẫn": {"cat1": "accessories", "cat2": "jewelry", "cat3": "rings"},
    "vòng tay": {"cat1": "accessories", "cat2": "jewelry", "cat3": "bracelets"},
    "đồng hồ": {"cat1": "accessories", "cat2": "watches"},
    "khăn": {"cat1": "accessories", "cat2": "scarves"},
    "cà vạt": {"cat1": "accessories", "cat2": "ties", "style_tags": "formal;office"},
    "tất": {"cat1": "accessories", "cat2": "socks"},
    "vớ": {"cat1": "accessories", "cat2": "socks"}
}

class FashionScraper(ABC):
    def __init__(self, brand_name: str, base_url: str):
        self.brand_name = brand_name.lower()
        self.base_url = base_url
        
        self.output_dir = "data/custom/catalog"
        self.image_dir = os.path.join(self.output_dir, "images")
        self.csv_path = os.path.join(self.output_dir, "catalog_metadata.csv")
        self.seen_products_path = os.path.join(self.output_dir, f"{self.brand_name}_seen_product_keys.txt")
        
        os.makedirs(self.image_dir, exist_ok=True)
        self._init_csv()
        self.seen_product_keys = self._load_seen_product_keys()

    def _init_csv(self):
        """Khởi tạo tệp CSV định dạng utf-8-sig."""
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_FIELDNAMES)

    def _load_seen_product_keys(self) -> set[str]:
        if not os.path.exists(self.seen_products_path):
            return set()

        with open(self.seen_products_path, mode="r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}

    def mark_product_seen(self, product_key: str):
        if not product_key or product_key in self.seen_product_keys:
            return

        self.seen_product_keys.add(product_key)
        with open(self.seen_products_path, mode="a", encoding="utf-8") as f:
            f.write(f"{product_key}\n")

    def download_image(self, img_url: str, item_id: str) -> str:
        """Tải dữ liệu hình ảnh và trả về đường dẫn tương đối."""
        try:
            if img_url.startswith("//"):
                img_url = f"https:{img_url}"
            elif img_url.startswith("/"):
                img_url = f"{self.base_url}{img_url}"

            response = requests.get(img_url, stream=True, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            
            filename = f"{item_id}.jpg"
            save_path = os.path.join(self.image_dir, filename)
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return filename
        except Exception as e:
            print(f"[ERROR] Hệ thống không thể tải hình ảnh tại {img_url}: {e}")
            return ""

    def save_item(self, item: CatalogItem):
        """Ghi bản ghi dữ liệu sản phẩm vào tệp CSV."""
        row = item.model_dump()
        for field in ("season", "style_tags"):
            if isinstance(row.get(field), list):
                row[field] = json.dumps(row[field], ensure_ascii=False)

        with open(self.csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writerow(row)

    def make_item_id(self) -> str:
        """Generate a collision-safe ID for long multi-store crawl runs."""
        return f"item_custom_{self.brand_name}_{uuid.uuid4().hex[:12]}"

    def normalize_url(self, url: str) -> str:
        if not url:
            return ""

        absolute_url = urljoin(self.base_url, url)
        parsed = urlparse(absolute_url)
        return parsed._replace(query="", fragment="").geturl().rstrip("/")

    def get_collection_slug(self, url: str) -> str:
        path_parts = [part for part in urlparse(self.normalize_url(url)).path.split("/") if part]
        return path_parts[-1].lower() if path_parts else ""

    def make_product_key(self, product_url: str, img_url: str, title: str) -> str:
        product_url = self.normalize_url(product_url)
        img_url = self.normalize_url(img_url)
        title = " ".join(title.lower().split())
        return product_url or img_url or title

    def infer_gender_from_url(self, url: str) -> str:
        url_lower = url.lower()
        if any(marker in url_lower for marker in ["/women/", "-nu", "/nu/", "nu-"]):
            return "female"
        if any(marker in url_lower for marker in ["/men/", "-nam", "/nam/", "nam-"]):
            return "male"
        return "unisex"
    
    def extract_color(self, text: str) -> str:
        """Trích xuất màu sắc chủ đạo từ tiêu đề (Text Mining)."""
        text_lower = text.lower()
        # Ánh xạ từ vựng tiếng Việt sang tiếng Anh chuẩn
        colors_map = {
            "đen": "black", "trắng": "white", "xám": "grey", "ghi": "grey",
            "đỏ": "red", "vàng": "yellow", "xanh navy": "navy", "xanh dương": "blue",
            "xanh biển": "blue", "xanh lá": "green", "hồng": "pink", "tím": "purple",
            "nâu": "brown", "cam": "orange", "kem": "cream", "be": "beige", "rêu": "olive"
        }
        for vn_color, en_color in colors_map.items():
            if vn_color in text_lower:
                return en_color
        return "unknown"
    
    def extract_material(self, text: str, fallback_material: str = None) -> str | None:
        """Trích xuất chất liệu độc lập từ tiêu đề sản phẩm (Text Mining)."""
        text_lower = text.lower()
        
        # Từ điển chất liệu (Ưu tiên cụm từ dài lên trước)
        material_map = {
            "cotton poly": "blend",   # Sợi pha
            "cotton-poly": "blend",
            "polyester": "polyester",
            "poly": "polyester",
            "cotton": "cotton",
            "linen": "linen",
            "lanh": "linen",
            "denim": "denim",
            "jean": "denim",
            "bò": "denim",            # Áo bò, quần bò
            "kaki": "khaki",
            "khaki": "khaki",
            "len": "knit",
            "nỉ": "fleece",
            "da lộn": "suede",
            "da": "leather",
            "lụa": "silk",
            "voan": "chiffon",
            "nhung": "velvet",
            "canvas": "canvas",
            "vải bố": "canvas",
            "nylon": "nylon"
        }
        
        for kw, mat_en in material_map.items():
            if kw in text_lower:
                return mat_en
                
        return fallback_material

    def infer_category_from_url(self, url: str) -> tuple[str, str]:
        url_lower = url.lower()
        category_markers = [
            (["outerwear", "jacket", "coat", "ao-khoac"], ("outerwear", "jackets")),
            (["bottoms", "pants", "trouser", "jeans", "shorts", "quan"], ("bottoms", "bottoms")),
            (["skirts-and-dresses", "dress", "dresses", "skirt", "vay", "dam"], ("dresses", "dresses")),
            (["shoe", "sneaker", "giay", "dep"], ("shoes", "shoes")),
            (["bag", "backpack", "tui", "balo"], ("bags", "bags")),
            (["accessor", "hat", "belt", "kinh", "mu", "non"], ("accessories", "accessories")),
            (["t-shirt", "shirt", "polo", "sweater", "knitwear", "blouse", "ao"], ("tops", "tops")),
        ]
        for markers, category in category_markers:
            if any(marker in url_lower for marker in markers):
                return category
        return "unknown", "unknown"

    def get_stratified_split(self) -> str:
        """Phân bổ nhãn tập dữ liệu (70% train, 15% val, 15% test)."""
        return random.choices(['train', 'val', 'test'], weights=[70, 15, 15], k=1)[0]

    def classify_item(self, title: str) -> dict:
        """Phân loại danh mục và tự động trích xuất các thuộc tính ẩn dựa trên tiêu đề."""
        title_lower = title.lower()
        sorted_keys = sorted(TAXONOMY_MAP.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in title_lower:
                return TAXONOMY_MAP[key]
        return {"cat1": "unknown", "cat2": "unknown"}

    def resolve_taxonomy(self, title: str, fallback_cat1: str = "unknown", fallback_cat2: str = "unknown") -> dict | None:
        """Classify by title first, then use page/category fallback if title is too vague."""
        taxonomy = dict(self.classify_item(title))

        if taxonomy.get("cat1") not in VALID_CATEGORY1:
            if fallback_cat1 in VALID_CATEGORY1:
                taxonomy["cat1"] = fallback_cat1
                taxonomy["cat2"] = fallback_cat2 if fallback_cat2 != "unknown" else fallback_cat1
            else:
                return None

        return taxonomy

    @abstractmethod
    def scrape_category(self, category_url: str, **kwargs):
        """Hàm trừu tượng yêu cầu các lớp con phải triển khai logic trích xuất riêng."""
        pass


class CoolmateScraper(FashionScraper):
    def __init__(self):
        super().__init__(brand_name="coolmate", base_url="https://www.coolmate.me")

    def discover_sub_categories(self, parent_url: str) -> list[dict]:
        """Tự động phân tích trang danh mục cha để trích xuất các liên kết danh mục con."""
        print(f"[SYSTEM] Bắt đầu phân tích cấu trúc danh mục tại: {parent_url}")
        target_categories = []
        try:
            response = requests.get(parent_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                text = link.get_text(separator=' ', strip=True).lower()
                
                # Loại bỏ các liên kết phân trang/bộ lọc (chứa dấu ?) để chống trùng lặp
                if not text or ('/collection/' not in href) or ('?' in href):
                    continue
                
                full_url = self.normalize_url(href)
                parent_full_url = self.normalize_url(parent_url)
                slug = self.get_collection_slug(full_url)
                if full_url == parent_full_url or slug in BROAD_COLLECTION_SLUGS:
                    continue
                
                for keyword, mapping in TAXONOMY_MAP.items():
                    if keyword in text:
                        target_categories.append({
                            "url": full_url,
                            "cat1": mapping["cat1"],
                            "cat2": mapping["cat2"],
                            "keyword_matched": keyword
                        })
                        break
                        
        except Exception as e:
            print(f"[ERROR] Quá trình phân tích danh mục gặp sự cố: {e}")
            
        return target_categories

    def _get_full_html_with_click(self, url: str) -> str:
        """Kích hoạt trình duyệt, mô phỏng thao tác tương tác nút bấm tải thêm."""
        print(f"[SELENIUM] Khởi tạo phiên làm việc Chrome cho: {url}")
        chrome_options = Options()
        chrome_options.add_experimental_option("detach", False) 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("window-size=1920,1080")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(3)
        
        click_count = 0
        while True:
            try:
                product_cards = driver.find_elements(By.XPATH, "//div[@id='collection-listing']//div[contains(@class, 'relative') and contains(@class, 'w-full')]")
                initial_count = len(product_cards)
                
                buttons = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'xem thêm', 'XEM THÊM'), 'XEM THÊM')]")
                
                if not buttons:
                    break
                
                clicked_successfully = False
                
                for btn in buttons:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                        time.sleep(2) 
                        
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3) 
                        
                        new_product_cards = driver.find_elements(By.XPATH, "//div[@id='collection-listing']//div[contains(@class, 'relative') and contains(@class, 'w-full')]")
                        current_count = len(new_product_cards)
                        
                        if current_count > initial_count:
                            click_count += 1
                            print(f"[SELENIUM] Tương tác tải thêm thành công. Số lượng phần tử: {initial_count} -> {current_count} (Lượt: {click_count})")
                            clicked_successfully = True
                            break 
                            
                    except Exception:
                        continue
                
                if not clicked_successfully:
                    print("[SELENIUM] Đã duyệt hết các phần tử tương tác. DOM không phát sinh thêm.")
                    break
                
            except Exception as e:
                print(f"[ERROR] Ngắt quy trình mô phỏng do lỗi ngoại lệ: {e}")
                break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        full_html = driver.page_source
        driver.quit()
        return full_html

    def scrape_category(self, category_url: str, **kwargs):
        """Xử lý HTML đầu vào, trích xuất cấu trúc dữ liệu cho Coolmate."""
        url_category1, url_category2 = self.infer_category_from_url(category_url)
        category1 = kwargs.get('category1', url_category1)
        category2 = kwargs.get('category2', url_category2)
        if category1 == "unknown":
            category1 = url_category1
        if category2 == "unknown":
            category2 = url_category2
        
        html_content = self._get_full_html_with_click(category_url)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        listing_div = soup.find('div', id='collection-listing')
        if not listing_div:
            print("[ERROR] Không định vị được node chứa dữ liệu sản phẩm trong cấu trúc HTML.")
            return

        products = listing_div.find_all('div', class_='relative w-full shrink-0 grow-0') 
        total_found = len(products)
        print(f"[SYSTEM] Trích xuất cấu trúc: Định vị được {total_found} bản ghi.")

        saved_count = 0
        skipped_count = 0
        duplicate_count = 0
        for idx, prod in enumerate(products, start=1):
            try:
                a_tag = prod.find('a', class_=lambda x: x and 'block h-full w-full' in x)
                if not a_tag:
                    continue
                
                img_elem = a_tag.find('img')
                if not img_elem:
                    continue
                    
                title = img_elem.get('alt', '').strip()
                img_url = img_elem.get('src') or img_elem.get('data-src')
                if not img_url:
                    continue

                product_url = a_tag.get("href", "")
                product_key = self.make_product_key(product_url, img_url, title)
                if product_key in self.seen_product_keys:
                    duplicate_count += 1
                    continue

                taxonomy = self.resolve_taxonomy(title, category1, category2)
                if taxonomy is None:
                    skipped_count += 1
                    continue

                item_id = self.make_item_id()
                image_path = self.download_image(img_url, item_id)
                if not image_path:
                    continue

                # Cố gắng khởi tạo và Validate bằng Pydantic V2 Strict Mode
                try:
                    default_fit = "not_applicable" if taxonomy.get("cat1") in ["shoes", "bags", "accessories"] else "regular"
                    raw_styles = taxonomy.get("style_tags", "")
                    parsed_styles = raw_styles.split(";") if raw_styles else []

                    item = CatalogItem(
                        item_ID=item_id,
                        image_path=image_path,
                        brand=self.brand_name,  # ĐÃ FIX: Điền đúng brand
                        short_text=title, 
                        detailed_text=None,
                        gender=self.infer_gender_from_url(category_url),
                        category1=taxonomy.get("cat1", category1),
                        category2=taxonomy.get("cat2", category2),
                        category3=taxonomy.get("cat3"),
                        dominant_color=self.extract_color(title), # ĐÃ FIX: Tự động trích xuất màu
                        pattern=taxonomy.get("pattern", "solid"),
                        material=self.extract_material(title, fallback_material=taxonomy.get("material")),
                        fit_type=taxonomy.get("fit_type", default_fit),
                        neckline=taxonomy.get("neckline"),
                        sleeve_length=taxonomy.get("sleeve_length"),
                        bottom_length=taxonomy.get("bottom_length"),
                        style_tags=parsed_styles,
                        # Đảm bảo season nếu có thì là list theo schemas.py
                        season=[taxonomy["season"]] if "season" in taxonomy else ["all_season"],
                        source=self.base_url,   # ĐÃ FIX: Lấy URL trang web làm source
                        split=self.get_stratified_split(),
                        is_manually_labeled=False
                    )

                    self.save_item(item)
                    self.mark_product_seen(product_key)
                    saved_count += 1

                except ValidationError as ve:
                    print(f"[WARN] Data Pydantic không hợp lệ tại {item_id}. Bỏ qua. Lỗi: {ve}")
                    continue
                
            except Exception as e:
                print(f"[ERROR] Sự cố trích xuất tại vị trí {idx}: {e}")
                
        print(f"[SUCCESS] Hoàn thành luồng ghi dữ liệu. Lưu thành công {saved_count}/{total_found} bản ghi. Bỏ qua {skipped_count} bản ghi không suy luận được danh mục. Trùng {duplicate_count} bản ghi.")


class UniqloScraper(FashionScraper):
    def __init__(self):
        super().__init__(brand_name="uniqlo", base_url="https://www.uniqlo.com")

    def _get_full_html_infinite_scroll(self, url: str) -> str:
        """Chiến thuật cuộn vô hạn (Infinite Scroll) thông qua kiểm tra chiều cao DOM."""
        print(f"[SELENIUM] Khởi tạo phiên làm việc Chrome cho: {url}")
        chrome_options = Options()
        chrome_options.add_experimental_option("detach", False) 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("window-size=1920,1080")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(4)
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_count = 0
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3) 
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print("[SELENIUM] Chiều cao DOM không thay đổi. Hoàn tất quá trình tải tải.")
                break
                
            last_height = new_height
            scroll_count += 1
            print(f"[SELENIUM] Cuộn trang thành công (Lượt: {scroll_count}). DOM đang được mở rộng.")

        driver.execute_script("window.scrollBy(0, -500);")
        time.sleep(2)

        full_html = driver.page_source
        driver.quit()
        return full_html

    def scrape_category(self, category_url: str, **kwargs):
        """Xử lý HTML đầu vào, trích xuất cấu trúc dữ liệu cho Uniqlo."""
        html_content = self._get_full_html_infinite_scroll(category_url)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # BẢN VÁ LỖI 1: Thu hẹp phạm vi quét vào đúng khung chứa lưới sản phẩm
        grid_container = soup.find('div', class_=lambda x: x and 'fr-ec-product-collection--type-grid' in x)
        
        if not grid_container:
            print("[ERROR] Không định vị được container lưới sản phẩm của Uniqlo. Bỏ qua danh mục.")
            return

        # Chỉ tìm các thẻ <a> chứa class 'product-tile__link' bên trong grid_container
        products = grid_container.find_all('a', class_=lambda x: x and 'product-tile__link' in x)
        
        total_found = len(products)
        print(f"[SYSTEM] Trích xuất cấu trúc: Định vị được {total_found} node sản phẩm.")

        saved_count = 0
        skipped_count = 0
        duplicate_count = 0
        
        # BẢN VÁ LỖI 2: Khởi tạo Set để chống trùng lặp URL hình ảnh cục bộ
        seen_image_urls = set()
        
        for idx, prod in enumerate(products, start=1):
            try:
                img_elem = prod.find('img')
                if not img_elem:
                    continue
                    
                title = img_elem.get('alt', '').strip()
                # Ưu tiên lấy data-src do cơ chế lazy load, sau đó mới đến src
                img_url = img_elem.get('data-src') or img_elem.get('src')
                
                if not img_url or "gif" in img_url.lower(): 
                    continue

                # Kiểm tra và loại bỏ trùng lặp
                if img_url in seen_image_urls:
                    duplicate_count += 1
                    continue
                seen_image_urls.add(img_url)

                product_url = prod.get("href", "")
                product_key = self.make_product_key(product_url, img_url, title)
                if product_key in self.seen_product_keys:
                    duplicate_count += 1
                    continue

                category1, category2 = self.infer_category_from_url(category_url)
                taxonomy = self.resolve_taxonomy(title, category1, category2)
                if taxonomy is None:
                    skipped_count += 1
                    continue

                item_id = self.make_item_id()
                image_path = self.download_image(img_url, item_id)
                if not image_path:
                    continue

                try:
                    default_fit = "not_applicable" if taxonomy.get("cat1") in ["shoes", "bags", "accessories"] else "regular"
                    raw_styles = taxonomy.get("style_tags", "")
                    parsed_styles = raw_styles.split(";") if raw_styles else []
                    inferred_gender = self.infer_gender_from_url(category_url)

                    item = CatalogItem(
                        item_ID=item_id,
                        image_path=image_path,
                        brand=self.brand_name,
                        short_text=title,
                        detailed_text=None,
                        gender=self.infer_gender_from_url(category_url),
                        category1=taxonomy["cat1"],
                        category2=taxonomy["cat2"],
                        category3=taxonomy.get("cat3"),
                        dominant_color=self.extract_color(title), # Tự động bắt màu
                        pattern=taxonomy.get("pattern", "solid"),
                        material=taxonomy.get("material"),
                        fit_type=taxonomy.get("fit_type", default_fit),
                        neckline=taxonomy.get("neckline"),
                        sleeve_length=taxonomy.get("sleeve_length"),
                        bottom_length=taxonomy.get("bottom_length"),
                        style_tags=parsed_styles,
                        season=[taxonomy["season"]] if "season" in taxonomy else ["all_season"],
                        source=self.base_url,
                        split=self.get_stratified_split(),
                        is_manually_labeled=False
                    )
                    
                    self.save_item(item)
                    self.mark_product_seen(product_key)
                    saved_count += 1
                    
                except ValidationError as ve:
                    print(f"[WARN] Dữ liệu Uniqlo bị Pydantic từ chối tại {item_id}: {ve}")
                    continue
                
            except Exception as e:
                print(f"[WARN] Bỏ qua bản ghi tại vị trí {idx} do lỗi trích xuất: {e}")
                
        print(f"[SUCCESS] Hoàn thành luồng ghi dữ liệu. Lưu {saved_count} bản ghi. Loại trừ {skipped_count} bản ghi không thuộc chuyên mục. Trùng {duplicate_count} bản ghi.")


if __name__ == "__main__":
    print("[SYSTEM] KHỞI ĐỘNG HỆ THỐNG THU THẬP DỮ LIỆU ĐA NỀN TẢNG (MULTI-SITE CRAWLER)")
    print("\n[PHASE 1] KÍCH HOẠT MODULE COOLMATE")
    coolmate_crawler = CoolmateScraper()
    coolmate_parent_urls = [
        # Danh mục Nam
        "https://www.coolmate.me/collection/ao-nam",
        "https://www.coolmate.me/collection/quan-nam",
        # Danh mục Nữ
        "https://www.coolmate.me/collection/ao-nu",
        "https://www.coolmate.me/collection/quan-nu"
    ]
    
    raw_cm_targets = []
    for parent in coolmate_parent_urls:
        raw_cm_targets.extend(coolmate_crawler.discover_sub_categories(parent))
        
    coolmate_targets = []
    cm_seen = set()
    for target in raw_cm_targets:
        if target["url"] not in cm_seen:
            coolmate_targets.append(target)
            cm_seen.add(target["url"])
            
    for index, target in enumerate(coolmate_targets, start=1):
        print(f"\n[COOLMATE - TASK {index}/{len(coolmate_targets)}] Đang xử lý endpoint: {target['url']}")
        try:
            coolmate_crawler.scrape_category(
                category_url=target["url"],
                category1=target["cat1"],
                category2=target["cat2"]
            )
        except Exception as e:
            print(f"[ERROR] Hệ thống gián đoạn tại {target['url']}: {e}")
        time.sleep(8)

    print("\n[PHASE 2] KÍCH HOẠT MODULE UNIQLO")
    uniqlo_crawler = UniqloScraper()
    
    uniqlo_urls = [
        # Danh mục Nam
        "https://www.uniqlo.com/vn/vi/men/t-shirts-sweat-and-fleece", 
        "https://www.uniqlo.com/vn/vi/men/sweaters-and-knitwear",             
        "https://www.uniqlo.com/vn/vi/men/shirts-and-polo-shirts",                   
        "https://www.uniqlo.com/vn/vi/men/bottoms",
        "https://www.uniqlo.com/vn/vi/men/outerwear",
        # Danh mục Nữ
        "https://www.uniqlo.com/vn/vi/women/t-shirts-sweat-and-fleece",
        "https://www.uniqlo.com/vn/vi/women/sweaters-and-knitwear",
        "https://www.uniqlo.com/vn/vi/women/shirts-and-blouses",
        "https://www.uniqlo.com/vn/vi/women/bottoms",
        "https://www.uniqlo.com/vn/vi/women/outerwear",
        "https://www.uniqlo.com/vn/vi/women/skirts-and-dresses",
    ]
    
    for index, url in enumerate(uniqlo_urls, start=1):
        print(f"\n[UNIQLO - TASK {index}/{len(uniqlo_urls)}] Đang xử lý endpoint: {url}")
        try:
            uniqlo_crawler.scrape_category(category_url=url)
        except Exception as e:
            print(f"[ERROR] Hệ thống gián đoạn tại {url}: {e}")
        time.sleep(10)

    print("\n[SYSTEM] TOÀN BỘ TIẾN TRÌNH THU THẬP DỮ LIỆU ĐÃ KẾT THÚC.")
