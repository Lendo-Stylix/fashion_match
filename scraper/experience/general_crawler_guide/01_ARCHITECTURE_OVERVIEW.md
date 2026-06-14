# Architecture Overview — E-Commerce Scraper V3

> **Purpose**: This is the single most important document in the knowledge base. If you are an AI agent with zero context, read this file FIRST. It covers the complete architecture, philosophy, data flow, and every key design decision behind the scraper v3 system.
>
> **Case Study**: All examples reference **Aristino** (aristino.com — a Vietnamese fashion e-commerce site on the Haravan/Shopify platform).

---

## 1. Philosophy — The 2-Phase Architecture

The system divides the scraping problem into two strictly separated phases:

```
┌─────────────────────┐         ┌─────────────────────┐
│   PHASE 1:          │         │   PHASE 2:          │
│   DISCOVERY         │────────▶│   HARVEST           │
│                     │  JSON   │                     │
│ "Find all product   │  file   │ "Visit each URL,    │
│  URLs on the site"  │         │  extract full data"  │
└─────────────────────┘         └─────────────────────┘
```

### Why Two Phases?

| Concern | Discovery | Harvest |
|---------|-----------|---------|
| **Goal** | Collect every product URL, organized by category | Extract full product data (title, price, images, variants) from each URL |
| **Browser needed?** | ✅ Yes — needs Playwright + CDP for AX Tree interaction (clicking filters, "load more" buttons) | ❌ No — uses plain HTTP GET via `aiohttp` (no browser needed) |
| **Speed** | Slow (one category at a time, waits for AJAX) | Fast (concurrent async HTTP, up to 5 simultaneous requests) |
| **Re-runnable?** | ✅ Yes — can re-run discovery for a single category without affecting others | ✅ Yes — tracks `existing_urls` so it only fetches new products |
| **Output** | `scraped_products.json` — a dict of `{category_name: [url1, url2, ...]}` | `aristino_products_full.json` — a list of full product JSON objects |

### The Core Benefit of Separation

- If discovery crashes after scraping 10 out of 20 categories, you have 10 categories saved. Re-run picks up where it left off.
- If the website blocks your IP during harvest, the URL list is untouched. Wait, change IP, re-run harvest — it skips already-fetched products.
- You can debug discovery (browser interaction) and harvest (data parsing) independently.

---

## 2. The Core Innovation — Accessibility Tree (AX Tree) over CSS Selectors

### What is the AX Tree?

The **Accessibility Tree** is a parallel representation of a web page built by the browser for assistive technologies (screen readers). It contains only **semantically meaningful** elements with their roles, names, and states.

```
Traditional DOM:                          AX Tree:
<div class="sc-18kq2x1 fJRqzV">          checkbox | "Áo Blazer" | id=1111
  <div class="filter-option">            checkbox | "Áo Polo ngắn tay" | id=1150
    <label>                               checkbox | "Quần Âu" | id=1192
      <input type="checkbox" ...>         button | "Xem tất cả" | id=2847
      <span>Áo Blazer</span>             link | "TRANG PHỤC" | id=536
    </label>
  </div>
</div>
```

### Why AX Tree Beats CSS Selectors — The 5 Killer Arguments

#### 1. **Resilience to Website Redesigns**
CSS selectors like `div.sc-18kq2x1.fJRqzV > div.filter-option > label > input[type="checkbox"]` will **break** the moment the site:
- Redesigns and changes CSS class names (very common with CSS-in-JS frameworks)
- Adds/removes wrapper divs
- Switches from `<input type="checkbox">` to a custom `<div role="checkbox">`

The AX Tree node `checkbox | "Áo Blazer" | id=1111` survives **all** of these changes because:
- The role (`checkbox`) comes from the element's semantic purpose, not its CSS class
- The name (`"Áo Blazer"`) comes from the visible label text
- The `backendDOMNodeId` is a session-specific identifier — we look it up dynamically each time

#### 2. **Dramatic Size Reduction**
Real measurements from the Aristino website:

| Data | Size | Notes |
|------|------|-------|
| Raw HTML of product list page | ~700 KB | `sample_product.html` |
| Full raw AX Tree JSON | ~2.2 MB | `ax_full_raw_list.json` — includes all metadata |
| Filtered AX Tree (no `ignored` nodes) | ~1.9 MB | `ax_no_ignored_list.json` |
| **Compact AX Tree** | **~67 KB** | `ax_compact_list.txt` — **97% reduction from raw AX** |

The compact format is what the agent actually works with — just 67 KB of human-readable, semantically meaningful data for an entire product listing page.

#### 3. **Natural Filtering of Noise**
The AX Tree automatically excludes:
- Ad tracking pixels and invisible iframes
- Decorative SVG icons and CSS-only dividers
- Hidden elements (`display: none`, `visibility: hidden`)
- `<script>` and `<style>` tags
- Empty wrapper `<div>`s used for layout

#### 4. **Semantic Understanding**
Every node tells you **what it does**, not what it looks like:
```
role=button    → can be clicked to trigger an action
role=link      → navigates to another page (has a URL)
role=checkbox  → can be toggled on/off (has checked state)
role=textbox   → accepts text input
role=heading   → page section title (has level 1-6)
```

Combined with state properties:
```
expanded=true  → a collapsible section is currently open
checked=true   → a checkbox/radio is selected
disabled=true  → element cannot be interacted with
focused=true   → element currently has keyboard focus
```

#### 5. **Works Like a Human Sees the Page**
A screen reader user navigates by hearing:
> "Checkbox, Áo Blazer, not checked"
> "Button, Xem tất cả"
> "Link, TRANG PHỤC, navigates to collections"

This is *exactly* the level of understanding our scraper operates at. No parsing `class="btn btn-primary btn-lg mt-3 d-flex align-items-center justify-content-center"` to figure out "this is a button".

---

## 3. How the AX Tree is Accessed — The CDP Pipeline

The AX Tree is not a standard web API — it is accessed via the **Chrome DevTools Protocol (CDP)**. Here is the exact pipeline:

```
┌──────────────┐     CDP over WebSocket      ┌──────────────┐
│   Python      │◄──────────────────────────►│   Chrome      │
│   Script      │   port 9222                │   Browser     │
│  (Playwright) │                            │   (with       │
│               │   Accessibility            │    --force-    │
│               │   .getFullAXTree()         │    renderer-  │
│               │                            │    accessi-   │
│               │   DOM.scrollIntoViewIfNeeded│    bility)   │
│               │   DOM.getBoxModel          │               │
│               │   Input.dispatchMouseEvent │               │
└──────────────┘                             └──────────────┘
```

### Step-by-Step CDP Communication

```python
# 1. Connect to the already-running Chrome instance
browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")

# 2. Get the existing browser context and page (tab)
context = browser.contexts[0]
page = context.pages[0]

# 3. Open a CDP session on that page
cdp_session = await page.context.new_cdp_session(page)

# 4. Request the FULL Accessibility Tree
full_tree = await cdp_session.send("Accessibility.getFullAXTree")
nodes = full_tree.get("nodes", [])  # List of AX nodes

# 5. Always detach the CDP session when done
await cdp_session.detach()
```

### Clicking an AX Node by `backendDOMNodeId`

Since AX Tree nodes have no CSS selector, you click them using their `backendDOMNodeId`:

```python
async def click_node_via_cdp(page, backend_node_id: int):
    cdp = await page.context.new_cdp_session(page)
    try:
        # Scroll the element into view
        await cdp.send("DOM.scrollIntoViewIfNeeded", {
            "backendNodeId": backend_node_id
        })
        await asyncio.sleep(0.5)

        # Get the element's box model to calculate center coordinates
        box = await cdp.send("DOM.getBoxModel", {
            "backendNodeId": backend_node_id
        })
        content = box["model"]["content"]
        x = (content[0] + content[2]) / 2  # Center X
        y = (content[1] + content[5]) / 2  # Center Y

        # Simulate a real mouse click (press + release)
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1
        })
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1
        })
        return True
    except Exception as e:
        print(f"[!] Click failed for node id={backend_node_id}: {e}")
        return False
    finally:
        await cdp.detach()
```

> [!IMPORTANT]
> **Why `mousePressed` + `mouseReleased` instead of Playwright's `.click()`?**
> Playwright's `.click()` needs a CSS selector. Since we're working purely with AX Tree node IDs, we must use the lower-level CDP `Input.dispatchMouseEvent`. This also gives us more control over the click coordinates and avoids Playwright's auto-scrolling which can sometimes conflict with CDP's `DOM.scrollIntoViewIfNeeded`.

---

## 4. Directory Structure — The Complete Layout

```
scraper_v3/
│
├── chrome.bat                          ← Centralized Chrome launcher with CDP flags (port 9222)
├── chrome_profile/                     ← Centralized isolated Chrome profile directory
│                                          (cookies, cache — shared across all crawlers)
│
├── discovery/                          ← PHASE 1: Website analysis & URL collection
│   └── aristino/                       ← One subdirectory per target website
│       ├── aristino_scraper.py         ← ★ Main automated scraper (422 lines)
│       │                                  Iterates categories, clicks filters,
│       │                                  clicks "Xem tất cả", extracts product URLs
│       ├── tools/                      ← Reusable helper scripts
│       │   ├── get_ax_tree.py          ← Dumps AX Tree in 3 formats: raw JSON,
│       │   │                              filtered (no ignored), compact text
│       │   ├── interact_ax_node.py     ← Interactive CLI tool to click/type on any
│       │   │                              AX node by its backendDOMNodeId
│       │   ├── aristino_recipe.py      ← Step-by-step automation recipe: navigate
│       │   │                              homepage → click "TRANG PHỤC" → extract
│       │   │                              filter checkboxes → interactive CLI
│       │   └── input.txt               ← URL input for get_ax_tree.py
│       ├── docs_and_logs/              ← Analysis documents and AX Tree dumps
│       │   ├── ax_compact_main.txt     ← Compact AX of homepage (~51 KB)
│       │   ├── ax_compact_list.txt     ← Compact AX of product list page (~67 KB)
│       │   ├── ax_full_raw_main.json   ← Full raw AX of homepage (~1.6 MB)
│       │   ├── ax_full_raw_list.json   ← Full raw AX of product list page (~2.2 MB)
│       │   ├── ax_no_ignored_main.json ← Filtered AX of homepage (~1.5 MB)
│       │   ├── ax_no_ignored_list.json ← Filtered AX of product list page (~1.9 MB)
│       │   └── recipe_analysis.md      ← Human-written analysis of AX Tree structure
│       │                                  (how to find "TRANG PHỤC" link, "BỘ LỌC"
│       │                                   sidebar, "SẢN PHẨM" checkboxes)
│       └── output/
│           └── scraped_products.json   ← ★ OUTPUT: {category_name: [url, url, ...]}
│                                          (~177 KB, all discovered product URLs)
│
├── harvest/                            ← PHASE 2: Product data extraction
│   ├── note.txt                        ← Dev note: "combine AX Tree + DOM Tree"
│   └── aristino/
│       ├── product_harvester.py        ← ★ Bulk HTTP fetcher (130 lines)
│       │                                  Reads scraped_products.json → async HTTP GET
│       │                                  each URL → regex extract embedded JSON →
│       │                                  saves aristino_products_full.json
│       ├── image_downloader.py         ← Image downloader + URL replacer (128 lines)
│       │                                  Reads product JSON → downloads all images →
│       │                                  replaces remote URLs with local paths
│       ├── analyze_product.py          ← One-off tool: saves HTML + AX Tree of a
│       │                                  single product page for analysis
│       ├── sample_product.html         ← Saved HTML of one product page (~700 KB)
│       ├── sample_product_ax.json      ← Saved AX Tree of one product page (~1.3 MB)
│       ├── js_script.js                ← Extracted JS from product page (~146 KB)
│       ├── ld_json.json                ← Extracted JSON-LD structured data (~4.6 KB)
│       └── output/
│           ├── aristino_products_full.json       ← ★ Full product data (~25 MB)
│           ├── aristino_products_full_local.json  ← Same but with local image paths (~29 MB)
│           ├── single_product_sample.json         ← One product for testing
│           ├── single_product_sample_local.json   ← Same with local image paths
│           └── images/                            ← Downloaded product images
│
├── experience/                         ← ★ THIS KNOWLEDGE BASE
│   ├── README.md                       ← Index and reading guide
│   ├── 01_ARCHITECTURE_OVERVIEW.md     ← You are reading this file
│   ├── 02_CHROME_CDP_SETUP.md          ← Chrome initialization deep dive
│   ├── 03_AX_TREE_DEEP_DIVE.md         ← AX Tree: extraction, filtering, compacting
│   ├── 04_DISCOVERY_PHASE.md           ← Discovery phase walkthrough
│   ├── 05_HARVEST_PHASE.md             ← Harvest phase walkthrough
│   ├── 06_DATA_EXTRACTION_PATTERNS.md  ← HTML/JS/JSON extraction patterns
│   ├── 07_ANTI_BLOCKING_AND_RESILIENCE.md ← Rate limiting, retries, error handling
│   ├── 08_CODING_PATTERNS_AND_UTILS.md ← Reusable code patterns
│   └── 09_STEP_BY_STEP_NEW_WEBSITE.md  ← Complete playbook for a new website
│
├── ax_tree_methodology.md              ← High-level AX Tree methodology summary
└── llama_cpp_hosting_methodology.md    ← Local LLM hosting guide (for AI agent use)
```

---

## 5. Technology Stack — Why Each Tool

| Technology | Role | Why This Choice |
|------------|------|-----------------|
| **Python 3.x** | Main language | Async support, rich ecosystem, rapid prototyping |
| **Playwright** | Browser automation framework | Supports CDP connections (`connect_over_cdp`), async API, cross-browser |
| **Chrome DevTools Protocol (CDP)** | Low-level browser control | Direct access to `Accessibility.getFullAXTree`, `DOM.scrollIntoViewIfNeeded`, `Input.dispatchMouseEvent` — APIs not available in Playwright's high-level API |
| **aiohttp** | Async HTTP client | For Phase 2 (Harvest) — parallel HTTP GET without a browser. Much faster than Playwright for pure HTML fetching |
| **asyncio** | Async concurrency | Powers both Playwright (Phase 1) and aiohttp (Phase 2) concurrency |
| **Chrome** | Browser | Only browser that exposes the full Accessibility Tree via CDP's `Accessibility.getFullAXTree` |
| **JSON** | Data interchange format | All intermediate and final outputs are JSON — easy to inspect, merge, and resume |

### Libraries NOT Used and Why

| Library | Why Not |
|---------|---------|
| **BeautifulSoup / lxml** | Not needed — Phase 2 extracts data from embedded JavaScript JSON, not by parsing HTML DOM |
| **Selenium** | Playwright is faster, has native async, and supports CDP sessions directly |
| **Scrapy** | Overkill for our use case — we need browser interaction (Phase 1) + simple HTTP (Phase 2) |
| **requests** | Replaced by `aiohttp` for async concurrency |

---

## 6. Data Flow — Complete End-to-End Pipeline

```
                    PHASE 1: DISCOVERY                           PHASE 2: HARVEST
                    ════════════════                             ════════════════

    ┌─────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────────┐
    │ chrome  │     │  aristino_   │     │  scraped_     │     │  product_        │
    │  .bat   │────▶│  scraper.py  │────▶│  products     │────▶│  harvester.py    │
    │         │     │              │     │  .json        │     │                  │
    │ Launches│     │  Connects    │     │              │     │  Reads URLs,     │
    │ Chrome  │     │  via CDP,    │     │  {category:  │     │  HTTP GETs each, │
    │ on port │     │  navigates,  │     │   [url, ...]}│     │  extracts JSON   │
    │ 9222    │     │  clicks      │     │              │     │  from HTML       │
    └─────────┘     │  filters,    │     └──────────────┘     └────────┬─────────┘
                    │  collects    │                                    │
                    │  URLs        │                                    ▼
                    └──────────────┘                          ┌──────────────────┐
                                                             │  aristino_       │
                                                             │  products_full   │
                                                             │  .json           │
                                                             │                  │
                                                             │  [{title, price, │
                                                             │    images, ...}] │
                                                             └────────┬─────────┘
                                                                      │
                                                                      ▼
                                                             ┌──────────────────┐
                                                             │  image_          │
                                                             │  downloader.py   │
                                                             │                  │
                                                             │  Downloads imgs, │
                                                             │  replaces URLs   │
                                                             │  with local paths│
                                                             └────────┬─────────┘
                                                                      │
                                                                      ▼
                                                             ┌──────────────────┐
                                                             │  aristino_       │
                                                             │  products_full   │
                                                             │  _local.json     │
                                                             │                  │
                                                             │  + images/       │
                                                             │    ├── handle_0  │
                                                             │    ├── handle_1  │
                                                             │    └── ...       │
                                                             └──────────────────┘
```

### Step-by-Step Walkthrough

#### Step 1 — Launch Chrome with CDP (`chrome.bat`)

```batch
set FLAGS=--remote-debugging-port=9222 --user-data-dir=%PROFILE_DIR% --force-renderer-accessibility --disable-background-timer-throttling --no-first-run --no-default-browser-check
start "" %CHROME_BIN% %FLAGS%
```

**Critical flags explained:**
- `--remote-debugging-port=9222` — Opens a WebSocket endpoint for CDP communication
- `--user-data-dir=chrome_profile` — Creates an isolated browser profile (no interference with your personal Chrome)
- `--force-renderer-accessibility` — **THE MOST IMPORTANT FLAG** — Forces Chrome to build and maintain the Accessibility Tree even when no screen reader is active. Without this, `Accessibility.getFullAXTree` may return incomplete data
- `--disable-background-timer-throttling` — Prevents Chrome from slowing down timers in background tabs (important if the scraper tab loses focus)
- `--no-first-run --no-default-browser-check` — Skips "Welcome" dialogs and "Set as default browser" prompts that block automation

#### Step 2 — Discovery: Connect & Navigate (`aristino_scraper.py`)

```python
# Connect to the Chrome instance launched by chrome.bat
browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]  # Reuse existing context
page = context.pages[0]        # Reuse existing tab

# Set desktop viewport to avoid mobile responsive layout
await page.set_viewport_size({"width": 1920, "height": 1080})

# Navigate to the product collection page
await page.goto("https://aristino.com/collections/trang-phuc", wait_until="domcontentloaded")
await page.wait_for_timeout(3000)  # Wait for AJAX content to load
```

#### Step 3 — Discovery: Extract Category Checkboxes from AX Tree

```python
# Get the full AX Tree
nodes = await get_ax_tree(page)  # Returns list of all AX nodes

# Find all checkboxes under the "SẢN PHẨM" filter group
categories = extract_categories(nodes)
# Result: [
#   {"name": "Áo Blazer", "bid": 59259, "checked": False},
#   {"name": "Áo Polo ngắn tay", "bid": 75909, "checked": False},
#   {"name": "Quần Âu", "bid": 75951, "checked": False},
#   ...
# ]
```

**How `extract_categories` finds the right checkboxes:**
1. Builds a parent-child map from all AX nodes
2. For each `role="checkbox"` node, walks up the tree to find an ancestor or sibling named `"SẢN PHẨM"`
3. Only returns checkboxes that belong to the "SẢN PHẨM" filter group (ignoring checkboxes in "MÀU SẮC", "KÍCH CỠ", etc.)

#### Step 4 — Discovery: Iterate Categories & Collect URLs

For each category:
1. **Uncheck all other categories** — ensures we're filtering for exactly one category
2. **Check the target category** — click its checkbox via CDP
3. **Wait for filter to apply** — `asyncio.sleep(3)` for AJAX response
4. **Click "Xem tất cả" (Show All)** repeatedly — some categories have hundreds of products loaded lazily
5. **Extract all product URLs** — find all `role="link"` nodes whose URL contains `/products/`
6. **Save immediately** — write to `scraped_products.json` after EACH category

```python
# Find the "Xem tất cả" button in the AX Tree
for n in nodes:
    if get_role(n) == "button" and "xem tất cả" in get_name(n).lower():
        if not get_props(n).get("disabled", False):
            xem_tat_ca_btn = n
            break

# Click it and wait for more products to load
await click_node_via_cdp(page, xem_tat_ca_btn["backendDOMNodeId"])
await asyncio.sleep(3)  # Wait for AJAX to load more products
```

```python
# Extract product URLs from AX Tree links
def extract_product_urls(nodes):
    urls = set()
    for n in nodes:
        if get_role(n) == "link":
            props = get_props(n)
            url = props.get("url", "")
            if "/products/" in url:
                clean_url = url.split("?")[0]  # Remove query params
                if clean_url.startswith("/"):
                    clean_url = "https://aristino.com" + clean_url
                urls.add(clean_url)
    return list(urls)
```

#### Step 5 — Harvest: Bulk HTTP Fetch (`product_harvester.py`)

```python
# Read the discovery output
with open(DISCOVERY_INPUT_FILE, "r", encoding="utf-8") as f:
    category_map = json.load(f)  # {category: [url1, url2, ...]}

# Skip already-scraped URLs (incremental scraping)
existing_urls = set()
if os.path.exists(OUTPUT_FILE):
    existing_data = json.load(open(OUTPUT_FILE))
    for item in existing_data:
        existing_urls.add(item["_scraped_url"])

# Fetch each URL concurrently with semaphore limiting
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
async with aiohttp.ClientSession() as session:
    tasks = [fetch_product_data(session, url, category, semaphore)
             for url in urls if url not in existing_urls]
    results = await asyncio.gather(*tasks)
```

**Data extraction from HTML** — The key insight: Aristino embeds full product JSON in a JavaScript variable:
```python
# Pattern 1: window.productDetail = { data: {...}, id: ...}
match = re.search(r'window\.productDetail\s*=\s*{\s*data:\s*({.*?})\s*,\s*id:', html, re.DOTALL)

# Pattern 2: productjson: {...}, template_suffix
if not match:
    match = re.search(r'productjson:\s*({.*?}),\n\s*template_suffix', html, re.DOTALL)

product_data = json.loads(match.group(1))
```

> [!NOTE]
> **Why regex instead of a proper HTML parser?** Because the data is inside a `<script>` tag as a JavaScript object literal, not as HTML elements. BeautifulSoup would give us the raw script text anyway — we'd still need regex to extract the JSON from it. Using regex directly on the full HTML skips the unnecessary DOM parsing step.

#### Step 6 — Harvest: Download Images (`image_downloader.py`)

```python
# Collect all image URLs from the product data
urls_to_download = set()
urls_to_download.add(product["featured_image"])
for img in product.get("images", []):
    urls_to_download.add(img)
for variant in product.get("variants", []):
    if variant.get("featured_image", {}).get("src"):
        urls_to_download.add(variant["featured_image"]["src"])

# Download each image with retry
async def download_image(session, url, save_path, semaphore):
    url = fix_url(url)  # Fix "//product.hstatic.net..." → "https://..."
    if os.path.exists(save_path):
        return True  # Skip already downloaded

    async with semaphore:
        for attempt in range(3):
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    with open(save_path, "wb") as f:
                        f.write(content)
                    return True
            await asyncio.sleep(1)
    return False

# Replace remote URLs with local paths in the JSON
product["featured_image"] = "images/handle_0.jpg"
product["images"] = ["images/handle_0.jpg", "images/handle_1.jpg", ...]
```

---

## 7. Key Design Decisions Explained

### 7.1 — Separate Chrome Profile (`--user-data-dir`)

```batch
set PROFILE_DIR="%~dp0chrome_profile"
set FLAGS=... --user-data-dir=%PROFILE_DIR% ...
```

**Why?**
- Avoids cookie/session conflicts with your personal Chrome
- Prevents the scraper from polluting your browsing history, extensions, or saved passwords
- The profile directory is stored *inside* the project root (`chrome_profile/`), making it self-contained and shared across all crawlers.
- If cookies get corrupted or a captcha appears, just delete the profile folder and start fresh

### 7.2 — `--force-renderer-accessibility` Flag

**Why?**
Chrome normally only builds the Accessibility Tree when a screen reader is detected. Without this flag:
- `Accessibility.getFullAXTree` may return an empty or partial tree
- Nodes may lack `backendDOMNodeId` (making them un-clickable)
- Dynamic content (loaded via AJAX) may not appear in the tree

With this flag, Chrome builds the full AX Tree immediately on page load and keeps it updated as the DOM changes.

### 7.3 — Save Results After EACH Category

```python
for cat in target_categories:
    product_urls = await scrape_current_category_products(page, cat["name"])
    results[cat["name"]] = product_urls

    # Save immediately after each category
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
```

**Why?**
- The Aristino website has ~20 product categories. Scraping all of them takes 30+ minutes.
- If the script crashes at category 15, you still have categories 1-14 saved.
- If the website starts blocking you, you have partial results to work with.
- On re-run, you can skip already-completed categories.

### 7.4 — `asyncio.Semaphore(5)` for Concurrency Control

```python
semaphore = asyncio.Semaphore(5)

async def fetch_product_data(session, url, category, semaphore):
    async with semaphore:  # Only 5 concurrent requests
        await asyncio.sleep(0.5)  # Additional delay between requests
        async with session.get(url, ...) as response:
            ...
```

**Why 5?**
- Too many concurrent requests → HTTP 429 (Too Many Requests) or IP ban
- Too few → waste time (the website can handle moderate load)
- 5 with a 0.5s delay ≈ 10 requests/second — a reasonable rate for most e-commerce sites
- The semaphore is combined with exponential backoff retry on 429 responses

### 7.5 — Incremental Scraping via `existing_urls`

```python
existing_urls = set()
if os.path.exists(OUTPUT_FILE):
    existing_data = json.load(open(OUTPUT_FILE))
    for item in existing_data:
        existing_urls.add(item["_scraped_url"])

# Only scrape URLs not already in the output
items_to_scrape = [
    item for item in all_items if item["url"] not in existing_urls
]
```

**Why?**
- If harvest crashes halfway through 1300 products (due to network error, power loss, etc.), re-running starts from where it left off
- If discovery finds new products on re-run, harvest only fetches the new ones
- Saves time and reduces load on the target website

### 7.6 — UTF-8 Encoding Fix for Windows

```python
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

**Why?**
- Windows console defaults to `cp1252` or `cp437` encoding
- Vietnamese product names (Áo, Quần, Bộ đồ) contain diacritical marks that cause `UnicodeEncodeError` on Windows
- `sys.stdout.reconfigure(encoding='utf-8')` is the Python 3.7+ way to fix this
- The `AttributeError` fallback handles older Python versions or wrapped stdout streams
- All JSON files are written with `encoding='utf-8'` and `ensure_ascii=False`

### 7.7 — Windows Event Loop Policy

```python
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

**Why?**
- On Windows, `asyncio` defaults to `ProactorEventLoop` which has compatibility issues with `aiohttp`
- `WindowsSelectorEventLoopPolicy` forces use of `SelectorEventLoop` which works correctly with `aiohttp`
- This is only needed in the harvest phase (which uses `aiohttp`). The discovery phase uses Playwright which handles its own event loop.

### 7.8 — Protocol-Relative URL Fix

```python
def fix_url(url):
    if url and url.startswith("//"):
        return "https:" + url
    return url
```

**Why?**
- Aristino (on Haravan/Shopify platform) stores image URLs as `//product.hstatic.net/...` (protocol-relative)
- `aiohttp` requires a full URL starting with `http://` or `https://`
- The fix prepends `https:` to protocol-relative URLs

---

## 8. AX Tree Node Structure — The Raw Data Format

Each node returned by `Accessibility.getFullAXTree` has this structure:

```json
{
  "nodeId": "1111",
  "ignored": false,
  "role": {"type": "role", "value": "checkbox"},
  "name": {"type": "computedString", "value": "Áo Blazer", "sources": [...]},
  "properties": [
    {"name": "checked", "value": {"type": "tristate", "value": "false"}},
    {"name": "focused", "value": {"type": "boolean", "value": false}}
  ],
  "childIds": [],
  "parentId": "1110",
  "backendDOMNodeId": 59259
}
```

### Key Fields for Scraping

| Field | Usage | Example |
|-------|-------|---------|
| `role.value` | Determines what the element IS | `"checkbox"`, `"link"`, `"button"` |
| `name.value` | The visible label text | `"Áo Blazer"`, `"Xem tất cả"` |
| `backendDOMNodeId` | Target ID for CDP click/scroll | `59259` |
| `parentId` | Navigate up the tree to find parent groups | `"1110"` → listitem → list → "SẢN PHẨM" |
| `properties` | State info | `checked`, `disabled`, `expanded`, `url` |
| `ignored` | Whether to skip this node (decorative) | `true` for invisible elements |

### Helper Functions to Extract Node Data

```python
def get_role(node):
    """Extract the role string from a node."""
    return node.get("role", {}).get("value", "")

def get_name(node):
    """Extract the name string from a node."""
    return node.get("name", {}).get("value", "").strip()

def get_props(node):
    """Extract all properties as a flat dict."""
    result = {}
    for p in node.get("properties", []):
        pname = p["name"]
        val = p["value"].get("value")
        if val is not None:
            if val == "true": val = True
            elif val == "false": val = False
            result[pname] = val
    return result
```

---

## 9. The Three AX Tree Output Formats

The `get_ax_tree.py` tool produces three progressively compressed versions:

### Format 1: Raw JSON (`ax_full_raw.json`)
- **Size**: ~2.2 MB for a product list page
- **Content**: Exact output from `Accessibility.getFullAXTree`
- **Use case**: Debugging, understanding the full node structure

### Format 2: Filtered JSON (`ax_no_ignored.json`)
- **Size**: ~1.9 MB (removes `ignored: true` nodes)
- **Content**: Same structure as raw, but without decorative/invisible nodes
- **Use case**: Programmatic analysis without noise

### Format 3: Compact Text (`ax_compact.txt`)
- **Size**: ~67 KB (**97% reduction** from raw)
- **Content**: One line per meaningful node, indented by tree depth

```
RootWebArea | "Trang phục nam ARISTINO – Thời trang công sở nam" | id=988
  banner | id=990
    navigation | "Chính" | id=1002
      link | "TRANG PHỤC" | id=536 | url=https://aristino.com/collections/trang-phuc
  main | id=1032
    heading | "BỘ LỌC" | id=1046 | level=3
    button | "SẢN PHẨM" | id=1105 | expanded
    list | id=1109
      listitem | id=1110 | level=1
        checkbox | "Áo Blazer" | id=1111
      listitem | id=1113 | level=1
        checkbox | "Áo Dài" | id=1114
```

**Compaction rules** (from `get_ax_tree.py`):
- **Keep**: Interactive roles (`button`, `link`, `textbox`, `checkbox`, etc.), landmarks (`navigation`, `main`, `banner`), structure (`heading`, `list`), meaningful `StaticText`, named `image`
- **Skip**: `generic`, `InlineTextBox`, `none` roles (layout-only elements)
- **Props kept**: `focused`, `disabled`, `expanded`, `checked`, `level`, `url`, `editable`, `required`
- URLs are truncated to 80 characters for readability

---

## 10. Popup Handling — The `clean_popups` Strategy

Vietnamese e-commerce sites are notorious for aggressive popups (newsletter signups, promotional banners, notification permission requests). These popups overlay the page and block CDP clicks.

```python
async def clean_popups(page):
    """Remove advertising banners and overlay popups via JavaScript."""
    try:
        await page.evaluate("""() => {
            const selectors = [
                '#antsomi-slidedown-container',    // Antsomi marketing platform
                '.antsomi-slidedown-container',
                'div[id*="slidedown"]',            // Generic slidedown banners
                'div[class*="slidedown"]',
                'div[class*="popup"]',             // Generic popups
                'div[class*="modal"]',             // Bootstrap-style modals
                '.modal-backdrop'                  // Modal overlay background
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
        }""")
    except Exception as e:
        print(f"[*] Error cleaning popups: {e}")
```

**Why `el.remove()` instead of `el.style.display = 'none'`?**
- `display: none` would keep the element in the DOM and potentially in the AX Tree
- `el.remove()` completely removes the element, ensuring it doesn't block clicks
- This is called before EVERY click operation to ensure no popup appeared since the last cleanup

---

## 11. Running the System — Quick Reference

### Prerequisites
```powershell
pip install playwright aiohttp
playwright install chromium
```

### Phase 1: Discovery
```powershell
# Step 1: Launch Chrome with CDP (from the root directory)
.\chrome.bat

# Step 2: Run the scraper (from its subdirectory)
cd discovery\aristino
python aristino_scraper.py

# Output: discovery\aristino\output\scraped_products.json
```

### Phase 2: Harvest
```powershell
# Step 3: Fetch full product data (no browser needed)
cd harvest\aristino
python product_harvester.py

# Output: harvest\aristino\output\aristino_products_full.json

# Step 4: Download images and localize URLs
python image_downloader.py

# Output: harvest\aristino\output\aristino_products_full_local.json
#         harvest\aristino\output\images\*.jpg
```

### Debugging / Analysis Tools
```powershell
# Dump AX Tree of any page (writes 3 formats to tools\ directory)
# First, write the target URL to tools\input.txt
echo https://aristino.com/collections/trang-phuc > discovery\aristino\tools\input.txt
python discovery\aristino\tools\get_ax_tree.py

# Interactively click any AX node by its ID
python discovery\aristino\tools\interact_ax_node.py

# Step-by-step recipe with interactive filter selection
python discovery\aristino\tools\aristino_recipe.py

# Analyze a single product page (saves HTML + AX Tree)
python harvest\aristino\analyze_product.py
```

---

## 12. Output Data Schema

### Discovery Output: `scraped_products.json`

```json
{
  "Áo Blazer": [
    "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm040z",
    "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm041z",
    "..."
  ],
  "Áo Polo ngắn tay": [
    "https://aristino.com/products/ao-polo-nam-aristino-apsg240s",
    "..."
  ]
}
```

### Harvest Output: `aristino_products_full.json`

Each product object contains the embedded Shopify/Haravan product JSON plus two metadata fields:

```json
{
  "id": 1234567890,
  "title": "Áo Khoác Blazer Nam Aristino ABZM040Z",
  "handle": "ao-khoac-blazer-nam-aristino-abzm040z",
  "vendor": "ARISTINO",
  "product_type": "Áo Blazer",
  "price": 2990000,
  "compare_at_price": 3490000,
  "featured_image": "//product.hstatic.net/...",
  "images": ["//product.hstatic.net/...", "..."],
  "variants": [
    {
      "id": 9876543210,
      "title": "Xanh Navy / S",
      "price": 2990000,
      "sku": "ABZM040Z-XNV-S",
      "option1": "Xanh Navy",
      "option2": "S",
      "featured_image": {"src": "//product.hstatic.net/..."}
    }
  ],
  "options": [
    {"name": "Màu sắc", "values": ["Xanh Navy", "Đen", "Xám"]},
    {"name": "Kích thước", "values": ["S", "M", "L", "XL", "XXL"]}
  ],
  "body_html": "<p>Chất liệu: Vải polyester cao cấp...</p>",
  "_scraped_category": "Áo Blazer",
  "_scraped_url": "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm040z"
}
```

The `_scraped_category` and `_scraped_url` fields are added by the harvester to track the source.

---

## 13. Relationship Between Files — Cross-Reference Map

```
chrome.bat
    │
    ▼ launches Chrome on port 9222
    │
aristino_scraper.py ──── imports ────┬── get_ax_tree() [inline]
    │                                ├── click_node_via_cdp() [inline]
    │                                ├── extract_categories() [inline]
    │                                ├── extract_product_urls() [inline]
    │                                ├── toggle_checkbox() [inline]
    │                                ├── clean_popups() [inline]
    │                                └── scrape_current_category_products() [inline]
    │
    ▼ writes
    │
scraped_products.json
    │
    ▼ read by
    │
product_harvester.py ──── uses ─────┬── aiohttp (async HTTP)
    │                                ├── regex (extract JSON from HTML)
    │                                └── asyncio.Semaphore(5)
    │
    ▼ writes
    │
aristino_products_full.json
    │
    ▼ read by
    │
image_downloader.py ──── uses ──────┬── aiohttp (download images)
    │                                ├── asyncio.Semaphore(10)
    │                                └── fix_url() (protocol-relative → https)
    │
    ▼ writes
    │
aristino_products_full_local.json + images/
```

---

## 14. Summary for New Agents

If you are an AI agent starting from scratch and need to replicate this system for a new website:

1. **Read this file** (you just did ✅)
2. **Read `09_STEP_BY_STEP_NEW_WEBSITE.md`** for a complete checklist
3. **Start with analysis**: Use `get_ax_tree.py` to dump the AX Tree of the target website
4. **Build discovery**: Write a scraper that navigates categories and collects product URLs using the AX Tree
5. **Build harvest**: Write a fetcher that HTTP-GETs each URL and extracts product data from embedded JSON
6. **Add image download**: Download all product images and localize the URLs

The AX Tree approach means your scraper will be **resilient to CSS changes** and **compact in its representation** — the two biggest advantages over traditional scraping approaches.

> [!TIP]
> **Golden Rule**: Always dump and analyze the AX Tree BEFORE writing any scraping code. The tree tells you exactly what interactive elements exist on the page, what they're called, and how they're organized. Your scraper should be a direct translation of what you see in the compact AX Tree.
