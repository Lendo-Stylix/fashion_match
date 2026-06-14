# Canifa Real-World Scraping Experience & Technical Lessons

This document records the engineering details, platform characteristics, challenges, and solutions identified during the automated cào (scraping) process for `canifa.com`.

---

## 1. Platform & Infrastructure Reconnaissance

- **Platform**: Nuxt.js (Vue 3, Vue Router, Pinia) headless storefront communicating with a Magento 2 backend.
- **Data Endpoint**: The client-side Nuxt hydration uses an Elasticsearch middleware proxy:
  - **URL**: `https://canifa.com/v1/middleware/search_product`
  - **Method**: `POST`
  - **Payload Structure**: Elasticsearch OpenSearch JSON DSL.
  - **Authentication**: A static JWT token `groupToken` representing guest/anonymous group access.

---

## 2. Key Challenges & Technical Solutions

### A. Bypassing Browser Automation
- **Problem**: Opening 2,043 product detail pages via Playwright headlessly is highly resource-intensive, slow, and prone to rate-limiting or blocking.
- **Solution**: We monitored the initial Nuxt page hydration and identified that the Elasticsearch REST API returns *full product details* (including pricing, materials, specifications, and complete lists of variants/configurable children). We bypassed all browser automation and did direct paginated POST requests, completing the entire discovery and harvest phases in under **60 seconds**!

### B. Option Mapping (ID to Label Resolution)
- **Problem**: In the Elasticsearch product payload, variant attributes are returned as numeric IDs (e.g., `"color": 7423`, `"size": 2250`). Product-level `configurable_options_map` is frequently `null` for some products.
- **Solution**: We analyzed `window.__NUXT__` serialized state inside the initial HTML page source. We discovered a global Pinia store metadata field called `customAttributeMetadata` containing complete mappings for 6,419 color codes and 236 size codes.
- **Implementation**: The harvester loads `nuxt_data.json` state, builds `global_color_map` and `global_size_map` dictionaries, and matches child variant color/size option indices to human-readable strings (e.g., `Value=7423 -> Label=SB714`, `Value=2250 -> Label=110`).

### C. Relative Image URLs
- **Problem**: Product images are stored as relative paths (e.g., `/8/t/8ts26s014-pb547-xl-1-u.jpg`).
- **Solution**: We mapped the image CDN subdomain to `media.canifa.com` and prepended `https://media.canifa.com/catalog/product` to all relative image paths.

### D. No Image Downloads
- **Problem**: Downloading images locally makes the disk footprint heavy and slows down performance.
- **Solution**: In accordance with the user's requirements, we skipped local disk downloads and stored absolute CDN URLs in the product objects.

---

## 3. Tech Stack Reference Scripts

- **Discovery script**: Located at `experience/canifa/canifa_scraper.py`
- **Harvester script**: Located at `experience/canifa/product_harvester.py`
