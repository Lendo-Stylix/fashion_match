# Gumac Extraction and Bypass Details

This document records the engineering choices, challenges, and solutions implemented during the Gumac scraping development.

## 1. Platform Reconnaissance
- **Storefront**: React SPA (Single Page Application). Category pages are client-side rendered, resulting in static HTML with minimal size (~650 bytes).
- **Backend/CMS**: Custom API layer integrated with Haravan assets. The main data endpoints reside at `https://cms.gumac.vn`.

## 2. API Endpoints Used
1. **Discovery (Listing)**: 
   `https://cms.gumac.vn/api/v1/products?page={page}&limit={limit}&category={category_slug}`
   Returns a clean list of products with metadata like total pages. This completely bypasses the need for heavy browser rendering with Playwright.
2. **Harvest (Details)**: 
   `https://cms.gumac.vn/api/v1/products/{product_code}`
   Where `{product_code}` is the last segment of the product page URL (e.g. `df07008` in `https://gumac.vn/vay-dam-form-a/df07008`). It returns highly detailed nested JSON.

## 3. Quirks and Solutions
### Relative Images
- **Problem**: Image paths inside the API response colors list are relative (e.g. `/storage/upload/...`).
- **Solution**: Prepend `https://cms.gumac.vn` to convert them into absolute URLs.

### Variant Attributes & Static Specifications
- **Problem**: GUMAC CMS returns a static attributes table with size S measurements and size label `"Thông Tin Size": "S"` for all variants (S, M, L, XL, XXL) of a product.
- **Solution**: Dynamically scans the attributes dictionary and overrides the size label key (e.g., `Thông Tin Size`, `Số Đo Size`) with the variant's actual size name (e.g., `M`, `L`, etc.) for consistency.

### Unstructured HTML Descriptions
- **Problem**: The raw `description` field contains noisy HTML markup, style/script blocks, and images.
- **Solution**: Stored raw HTML under `description_html`. Standardized `description` to plain-text by stripping HTML tags, styling blocks, and unescaping HTML entities (like `&ndash;`, `&eacute;`) into readable text paragraphs.

### Missing Size Chart (Bảng Size)
- **Problem**: The harvester did not extract size guide images.
- **Solution**: Extracted absolute size guide URLs from `category.sizeGuideImage` or searched description HTML for images matching `bang-size` or `size-guide` patterns, saving them in `size_guide_image`.

### Category Coverage & Duplication Pruning
- **Problem**: Scanning all categories (parent roots and subcategories) led to heavily duplicate associations (e.g., `vay-dam` and `vay-dam-form-a` containing the same product), causing duplicate requests and duplicate outputs.
- **Solution**: Implemented a category pruning rule: for any parent category with nested subcategories, the parent is excluded and only subcategories are crawled (e.g. only crawl `vay-dam-form-a`, not `vay-dam`). Parent categories without subcategories are crawled at the root. We also added a `seen_in_run` set in the harvester loop to ensure each unique URL is only processed once. This reduced discovery to 715 URLs and exactly 672 unique, duplicate-free scraped products.

### Resiliency Against Null JSON Paths
- **Problem**: API fields like `category`, `color`, or `media` can be `null` in GUMAC's database for certain collections, causing python `NoneType` attribute crashes when chaining `.get()` operations.
- **Solution**: Replaced all chained `.get()` lookups with safe, defensive checks (`isinstance(obj, dict)`) to make the harvester completely crash-proof.

### Local Chrome CDP Failures
- **Problem**: Running Chrome CDP port-binding locally crashed due to headless display sandbox limitations on the terminal.
- **Solution**: Developed both scraper and harvester using self-contained direct HTTP requests, entirely bypassing the need for manual browser port-listener scripts.
