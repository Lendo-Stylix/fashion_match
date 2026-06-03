# Global Crawler Summary

This document provides a high-level summary of the traits, platform characteristics, and scraping status of all websites analyzed in this project.

## 1. Aristino
- **Platform**: Haravan (Shopify variant).
- **Status**: Scraped successfully (Discovery & Harvest phases completed).
- **Key Characteristics**:
  - **Data Structure**: Product data is deeply embedded in the HTML source code within a JavaScript variable (e.g., `window.productDetail` or `productjson`), rather than relying strictly on the DOM structure.
  - **Prices**: Prices in the JSON data are multiplied by 100 (e.g., 420000000 = 4,200,000 VND).
  - **Images**: Image URLs are often protocol-relative (e.g., `//product.hstatic.net/...`) and require prepending `https:`.
  - **Anti-Bot / Annoyances**: Heavy use of marketing popups and overlay banners (Antsomi) which block automated CDP clicks if not explicitly removed.

## 2. Gumac
- **Platform**: React SPA storefront with a custom CMS API (`https://cms.gumac.vn`) powered by Haravan assets.
- **Status**: Upgraded successfully (Scraped 672 unique, duplicate-free products).
- **Key Characteristics**:
  - **Data Structure**: Initial HTML is a client-rendered React SPA skeleton (~650 bytes). All listings and product details are fetched from CMS JSON API endpoints.
  - **Discovery**: Done by scanning subcategory endpoints mapped from CMS menu metadata. Prioritizes specific leaf subcategories over parent roots to avoid duplicate URL mappings (discovered 715 URLs).
  - **Harvest**: Product details fetched from `cms.gumac.vn/api/v1/products/{sku_code}`. Standardized descriptions to plain-text (while keeping `description_html` separate) and extracted size charts to `size_guide_image`. Deduplicates requests to crawl exactly 672 unique products.
  - **Override Static Sizes**: Dynamically overrides GUMAC's database design flaw where size label inside variant specifications is static ("S") for all sizes, updating it to match the variant actual size name (e.g. M, L, XL).
  - **NoneType Resiliency**: Chained `.get()` calls are replaced with defensive checks to prevent python crashes when category or media fields are null in the CMS database.
  - **Images**: Prepend `https://cms.gumac.vn` to all relative CDN paths.

## 3. Elise
- **Platform**: Magento 2.
- **Status**: Scraped successfully (Discovery & Harvest completed).
- **Key Characteristics**:
  - **Data Structure**: Fully Server-Side Rendered (SSR). Product lists and details are parsed from the HTML.
  - **Discovery**: Extracted using regex matches for `product-item-link` class.
  - **Harvest**: Variants and sizes parsed from JSON script blocks containing `[data-role=swatch-options]`. Images are extracted from elements with `data-big` attributes.
  - **Rocket Loader**: Cloudflare Rocket Loader rewrites script tags (e.g., `type="[hash]-text/javascript"`). Requires resilient regex patterns to locate Magento JSON blocks.
