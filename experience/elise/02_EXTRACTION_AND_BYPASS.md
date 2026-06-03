# Elise Extraction and Bypass Details

This document records the design patterns, parsing mechanisms, and anti-blocking configurations implemented for Elise.

## 1. Platform Reconnaissance
- **Type**: Magento 2.
- **Rendering**: Server-Side Rendered (SSR) HTML for both listing (category) pages and product detail pages. This allows fast parsing of pages directly via HTTP requests.

## 2. Scraping Strategies
### 2.1 Discovery (Listing)
- Category pages like `https://elise.vn/thoi-trang-nu/dam.html` return the full HTML containing product cards.
- Product URLs are inside links with class `product-item-link`. We extract them using a regex:
  `class="[^"]*product-item-link[^"]*"\s+href="([^"]+)"`
- Pagination is handled by appending `?p=N` to the URL.

### 2.2 Harvest (Details)
- Magento 2 configuration scripts (`type="text/x-magento-init"`) are embedded in the HTML.
- **Swatches/Sizes/Prices**: Extracted from the script tag containing `[data-role=swatch-options]`. This JSON configuration exposes:
  - Linked simple product IDs (`index`)
  - Variant sizes (`attributes`)
  - Pricing per size (`optionPrices`)
  - Real-time inventory levels (`stockQty`)
- **Images**: Elise's custom theme does not use standard Magento gallery scripts. Product slide images are extracted using regex targeting zoom-link attributes:
  `data-big="([^"]+)"`

## 3. Challenges & Solutions
### HTML Encoding
- **Problem**: Titles and text are HTML-entity encoded (e.g. `&#x0110;&#x1EA6;M`).
- **Solution**: Decoded via `html.unescape` in Python.

### Rocket Loader & Cloudflare Rewrites
- **Problem**: Cloudflare Rocket Loader changes the script tag types (e.g. `type="7d4a63...-javascript"`).
- **Solution**: Built resilient regexes that match `<script[^>]*type="text/x-magento-init"[^>]*>` to dynamically find the target script blocks regardless of custom type hashes.

## 4. Under-Scraping Issues and Upgrades
### 4.1 Root Causes of Missing Volume
1. **Discovery Pagination Cap**: The initial implementation stopped discovery at page 2 (`page >= 2`).
2. **Incremental Stop Logic Bug**: The scraper had an optimization `if page_added == 0: break`. However, if the scraper was re-run and the local JSON already had the products of page 1 cached, `page_added` for page 1 evaluated to `0`, causing the scraper to immediately stop on page 1 and miss all deeper pages (e.g., pages 3 and 4) which were never scraped.
3. **Harvest Cap**: The harvester had a hard limit of `crawl_limit = 50`.

### 4.2 Upgraded Solutions
1. **Category Refinement**: Aligned category lists to the 4 main subcategories under the main listing (Đầm, Áo, Chân Váy, Quần) as shown in the brand's navigation header.
2. **Page Signature Comparison**: Replaced the naive `page_added == 0` break check. We now compute a hash signature of the list of product URLs found on each page (`tuple(sorted(matches))`). If the signature of page `N` matches any previously seen page signature, it indicates that the site has redirected us back to page 1 or the list has wrapped around, signaling a robust termination point. This allows the scraper to safely advance past pages containing cached items to discover new products on deeper pages.
3. **Removal of Limits**: Removed both the discovery page limits and the harvester's `crawl_limit = 50` cap. The scripts successfully completed discovery of **433 products** and fully harvested them into `elise_products_full.json`.

