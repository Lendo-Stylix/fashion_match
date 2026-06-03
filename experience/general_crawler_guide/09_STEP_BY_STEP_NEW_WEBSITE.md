# Step-by-Step Guide: Scraping a New E-Commerce Website

This is the complete checklist for approaching any new e-commerce website from scratch.
Follow these steps in order.

## Phase 0: Preparation (~5 minutes)

### 0.1: Create Directory Structure
```
scraper_v3/
├── chrome.bat            ← Centralized Chrome launcher with CDP flags (port 9222)
├── chrome_profile/       ← Centralized isolated Chrome profile directory (git-ignored)
├── discovery/
│   └── <website_name>/
│       ├── tools/
│       │   ├── get_ax_tree.py    ← Copy from templates
│       │   ├── interact_ax_node.py  ← Copy from templates
│       │   └── input.txt         ← URL to analyze
│       ├── docs_and_logs/        ← AX tree dumps go here
│       ├── output/               ← Scraped URLs go here
│       └── <website>_scraper.py  ← Main discovery script
├── harvest/
│   └── <website_name>/
│       ├── output/
│       ├── product_harvester.py
│       ├── image_downloader.py
│       └── analyze_product.py
```

### 0.2: Install Dependencies
```bash
pip install playwright aiohttp
python -m playwright install chromium
```

### 0.3: Setup Chrome with CDP
Use the centralized `chrome.bat` located at the root of the project workspace (`scraper_v3/chrome.bat`).
Run it from the root directory to launch Chrome in CDP-ready mode (port 9222) with a shared profile.

## Phase 1: Manual Website Reconnaissance (~30 minutes)

### 1.1: Browse Manually
Open the website in the CDP Chrome instance and manually:
- Find the main product category pages
- Note the URL patterns for categories and products
- Check if there are filters/sorting options
- Check pagination style (page numbers? load more? infinite scroll?)
- Note any popups or overlays that appear

### 1.2: Dump AX Tree of Key Pages
For EACH important page type, dump the AX tree:
1. **Homepage**: Put homepage URL in `input.txt`, run `get_ax_tree.py`
   - Rename output files with `_home` suffix
2. **Category/Collection Page**: The page with product listings
   - Rename with `_list` suffix
3. **Product Detail Page**: A single product page
   - Rename with `_product` suffix

### 1.3: Analyze Compact AX Trees
Open each `ax_compact.txt` and answer these questions:

**For Homepage:**
- Where are the main navigation links? (role=link, name contains category text)
- What are the category names and their AX node IDs?

**For Category Page:**
- Is there a filter sidebar? (Look for heading with filter text, checkbox nodes)
- How are filters organized? (By category, color, size, brand?)
- Where are product links? (role=link with `/products/` in URL)
- Is there a "Load More" / "View All" button? (role=button)
- Is there a total product count displayed? (StaticText with "N products")

**For Product Page:**
- What's the page structure? (title, price, images, variants)
- This is mainly for understanding; actual data extraction uses HTML analysis

### 1.4: Write Analysis Document
Create `docs_and_logs/recipe_analysis.md` documenting:
- Navigation flow (how to get from homepage to product list)
- Filter structure (which groups, which checkboxes)
- Product URL pattern
- Pagination mechanism
- Key node IDs for reference (though they change between loads)

## Phase 2: Discovery Script (~2 hours)

### 2.1: Write the Recipe Script First
Create `tools/<website>_recipe.py` that:
1. Connects to Chrome CDP
2. Navigates to the target page
3. Gets AX tree and finds key elements
4. Allows interactive CLI exploration
5. This is your SANDBOX for testing

### 2.2: Test Key Operations
Using the recipe, verify:
- Can you navigate to the category page?
- Can you find all filter checkboxes?
- Can you toggle checkboxes and verify state change?
- Can you extract product URLs from the filtered view?
- Can you click "Load More" to get more products?

### 2.3: Write the Full Discovery Scraper
Create `<website>_scraper.py` that automates:
1. Navigate to collection page
2. Set viewport to 1920x1080
3. Clean popups
4. Extract all category checkboxes
5. For EACH category:
   a. Uncheck all others
   b. Check this category
   c. Wait for filter to apply
   d. Click "Load More" until all products visible
   e. Extract all product URLs
   f. Save incrementally
6. Output: `output/scraped_products.json`

## Phase 3: Harvest Script (~1 hour)

### 3.1: Analyze One Product Page
Run `analyze_product.py` to save:
- Full HTML of a sample product page
- AX tree of the product page
- Any SSR JSON state

### 3.2: Find Data Extraction Pattern
Open the saved HTML and search for:
1. `window.productDetail` or similar JS object
2. `productjson:` in shop configuration
3. `__NEXT_DATA__` or `__NUXT__` script tags
4. `application/ld+json` script tags

Write the regex to extract the product JSON.

### 3.3: Write the Product Harvester
Create `product_harvester.py` that:
1. Reads URLs from discovery output
2. Fetches each URL via HTTP (not browser — faster)
3. Extracts product JSON using your regex
4. Handles 429 errors with exponential backoff
5. Saves results incrementally
6. Supports resume (skips already-scraped URLs)

### 3.4: Write the Image Downloader
Create `image_downloader.py` that:
1. Reads product JSON
2. Collects all image URLs
3. Downloads images to local `output/images/` directory
4. Replaces URLs in JSON with local paths
5. Saves as `_local.json`

## Phase 4: Validation (~15 minutes)

### 4.1: Verify Data Completeness
- Total URLs collected matches website's displayed count
- Product JSON has expected fields (title, price, images, variants)
- Images downloaded successfully

### 4.2: Spot Check
- Open 5 random products on the website
- Compare displayed data with scraped JSON
- Verify prices, images, variant counts match

## Common Pitfalls
1. **Forgetting to set viewport** → Gets mobile layout with different AX tree structure
2. **Not cleaning popups** → Clicks land on popup instead of target element
3. **Using stale AX tree** → After navigation/filter change, ALWAYS re-fetch AX tree
4. **Not handling encoding** → Vietnamese characters crash on Windows console
5. **Too aggressive concurrency** → Gets IP blocked. Start with `Semaphore(3)` and increase.
6. **Hardcoding node IDs** → IDs change every page load. Always search by text/role.
7. **Not saving incrementally** → Crash at 80% means losing everything
8. **Price units** → Haravan stores price * 100. Always verify.

## Quick Reference: Key Files to Copy
When starting a new website, copy these files from templates:
- `tools/get_ax_tree.py` → Works with ANY website, no changes needed
- `tools/interact_ax_node.py` → Works with ANY website, no changes needed

*Note:* `chrome.bat` is now centralized at the project root (`scraper_v3/chrome.bat`). You only need to run this single file from the root to start the shared Chrome browser session for any crawler.

Customize for each new website:
- `tools/<website>_recipe.py` → Navigation logic specific to site
- `<website>_scraper.py` → Category structure specific to site
- `product_harvester.py` → JSON extraction regex specific to site
