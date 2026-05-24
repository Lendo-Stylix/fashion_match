"""
config.py — Cấu hình trung tâm cho scraper.
"""

import os

# ─── Browser ────────────────────────────────────────────────────────────────
CHROME_PORT = 9222
BROWSER_URL = f"http://localhost:{CHROME_PORT}"
HEADLESS_MODE = True
CONCURRENCY_LIMIT = 5
MAX_RETRIES = 3

# ─── Tốc độ & Anti-ban ──────────────────────────────────────────────────────
DELAY_BETWEEN_PAGES = 2.0   # giây, delay giữa các trang detail
DELAY_BETWEEN_SCROLL = 1.0  # giây, delay khi scroll listing
PAGE_LOAD_TIMEOUT = 30_000  # ms, timeout chờ page load
NETWORK_IDLE_TIMEOUT = 5_000  # ms, chờ network idle sau khi load

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ─── Đường dẫn Output ───────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

OUTPUT_BASE_DIR = os.path.join(_PROJECT_ROOT, "data", "scraped")

# ─── Cấu hình từng site ─────────────────────────────────────────────────────
SITES = {
    "coolmate": {
        "base_url": "https://www.coolmate.me",
        "product_url_prefix": "/product/",
        "categories": [
            "ao-thun-nam",
            "quan-short-nam",
            "quan-dai-nam",
            "ao-polo-nam",
            "ao-so-mi-nam",
            "ao-khoac-nam",
            "do-the-thao-nam",
        ],
        "collection_pattern": "https://www.coolmate.me/collection/{category}",
        "tech": "nuxt",  # 'nuxt' | 'next' | 'react' | 'generic'
        "gender_default": "male",
        "brand": "Coolmate",
    },
    "gumac": {
        "base_url": "https://gumac.vn",
        "sitemap_url": "https://gumac.vn/sitemap.xml",
        "product_url_patterns": [  # regex patterns xác định URL sản phẩm
            r"^https://gumac\.vn/[\w-]+/[\w]+\d+$",
        ],
        "exclude_url_patterns": [
            r"/tin-tuc/", r"/bo-suu-tap/", r"/sale-off/", r"/showrooms",
            r"/gioi-thieu", r"/tuyen-dung", r"/huong-dan-", r"/chinh-sach-",
            r"/lien-he", r"/dang-ky", r"/quen-mat-khau", r"/gio-hang",
        ],
        "tech": "react",
        "gender_default": "female",
        "brand": "GUMAC",
    },
}
