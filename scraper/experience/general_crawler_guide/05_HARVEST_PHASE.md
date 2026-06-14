# Harvest Phase — Product Data Extraction & Image Download

## Goal
The Harvest phase takes the product URLs from Discovery and extracts full product data for each one.
Output: A JSON file with complete product information + locally downloaded images.

## 3 Sub-steps

### Sub-step 1: Analyze a Sample Product Page (`analyze_product.py`)
BEFORE writing the bulk harvester, analyze ONE product page:
1. Open the product URL in a headless Playwright browser
2. Save the full HTML to `sample_product.html` (for manual inspection)
3. Save the AX tree to `sample_product_ax.json`
4. Check for SSR JSON state (`__NEXT_DATA__`, `__NUXT__`)
5. Look at the HTML source for embedded product data

This exploratory step reveals HOW the website stores product data.

### Sub-step 2: Extract Product Data (`product_harvester.py`)

#### Data Extraction Strategy for Haravan/Shopify-based Sites
Many Vietnamese e-commerce sites use Haravan (Vietnamese Shopify clone).
Product data is embedded directly in the page HTML as JavaScript variables:

**Pattern 1 — window.productDetail**:
```javascript
window.productDetail = {
    data: {"available":true, "title":"...", "price":420000000},
    id: 1056322122,
    handle: "ao-khoac-blazer-nam-aristino-abzm040z"
}
```
Regex to extract:
```python
match = re.search(r'window\.productDetail\s*=\s*{\s*data:\s*({.*?})\s*,\s*id:', html, re.DOTALL)
```

**Pattern 2 — productjson**:
```javascript
window.shop = {
    productjson: {"available":true, "title":"..."},
    template_suffix: null
}
```
Regex to extract:
```python
match = re.search(r'productjson:\s*({.*?}),\n\s*template_suffix', html, re.DOTALL)
```

Both patterns give you the SAME complete product JSON with:
- title, description, handle, id
- price, compare_at_price
- images (array of URLs)
- variants (with size, color, SKU, barcode, inventory_quantity)
- tags, vendor, type, published_at

#### Async Bulk Fetching
Key architecture decisions:
```python
async def fetch_product_data(session, url, category, semaphore):
    max_retries = 5
    for attempt in range(max_retries):
        async with semaphore:  # Limit concurrency
            await asyncio.sleep(0.5)  # Rate limiting between requests
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                if response.status == 429:
                    wait_time = (2 ** attempt) + 1  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    continue
                html = await response.text()
                # Extract JSON from HTML using regex
                ...
```

Critical design choices:
- `asyncio.Semaphore(5)` — Max 5 concurrent requests. More = faster but risks being blocked.
- `asyncio.sleep(0.5)` — 500ms delay between requests (rate limiting)
- Exponential backoff on 429: wait 2^attempt + 1 seconds
- User-Agent header to look like a real browser
- Max 5 retries per URL

#### Incremental Scraping (Resume Support)
```python
existing_urls = set()
existing_data = []
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        existing_data = json.load(f)
    for item in existing_data:
        existing_urls.add(item["_scraped_url"])

# Only scrape URLs not already in output
for url in urls:
    if url not in existing_urls:
        items_to_scrape.append(url)
```
This allows restarting the scraper after a crash without re-downloading everything.

#### Custom Metadata Fields
Add metadata to each product:
```python
product_data['_scraped_category'] = category
product_data['_scraped_url'] = url
```
Prefix with `_scraped_` to distinguish from original data.

### Sub-step 3: Download Images (`image_downloader.py`)

#### URL Fixing
Haravan sometimes returns protocol-relative URLs:
```python
def fix_url(url):
    if url and url.startswith("//"):
        return "https:" + url
    return url
```

#### Image Collection from Product JSON
Images can be in multiple places in product JSON:
1. `product["featured_image"]` — Main product image
2. `product["images"]` — Array of all product images
3. `product["variants"][*]["featured_image"]["src"]` — Variant-specific images

Collect ALL unique URLs:
```python
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
```

#### File Naming Convention
`{product_handle}_{index}{extension}` e.g., `ao-khoac-blazer-nam-aristino-abzm040z_0.jpg`

#### URL Replacement
After downloading, replace remote URLs with local paths in the JSON:
```python
product["featured_image"] = "images/ao-khoac-blazer-0.jpg"
product["images"] = ["images/ao-khoac-blazer-0.jpg", "images/ao-khoac-blazer-1.jpg"]
```
Save as `_local.json` to preserve original remote URLs file.

#### Concurrency for Images
`asyncio.Semaphore(10)` for images (can be more aggressive than page fetching since images are static CDN resources)

## Output Files
- `aristino_products_full.json` — All product data with remote image URLs
- `aristino_products_full_local.json` — Same but with local image paths
- `images/` — Directory with all downloaded images
- `single_product_sample.json` — One product for reference

## Windows-specific: Event Loop Policy
```python
import os
import asyncio

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
Fixes `aiohttp` compatibility issues on Windows.
