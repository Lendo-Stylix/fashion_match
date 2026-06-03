# Discovery Phase — Website Analysis & URL Collection

## Goal
The Discovery phase answers: "What product URLs exist on this website, organized by category?"
Output: A JSON file mapping category names to arrays of product URLs.

## Step-by-Step Process

### Step 1: Manual Reconnaissance (Tool: `get_ax_tree.py`)
Before writing any automation, you MUST understand the website's structure.

1. Open the target website in Chrome (via `chrome.bat`)
2. Navigate to the main page manually
3. Run `get_ax_tree.py` with the URL in `input.txt`
4. This produces 3 files:
   - `ax_full_raw.json` — Complete raw AX tree
   - `ax_no_ignored.json` — Filtered (ignored nodes removed)
   - `ax_compact.txt` — Human-readable compact tree
5. Read `ax_compact.txt` to understand the page structure
6. Repeat for different pages (homepage, category page, product listing page)

The tool creates output in `docs_and_logs/` directory with suffixes like `_main.txt`, `_list.txt`.

### Step 2: Analyze Compact AX Tree
Look for these patterns in the compact text:

**Navigation links**: Find the main menu
```
link | "TRANG PHỤC" | id=536 | url=https://aristino.com/collections/trang-phuc
```
This tells you: There's a clickable link with text "TRANG PHỤC" that goes to the clothing collection.

**Filter sidebar**: Find category filters
```
heading | "BỘ LỌC" | id=1046 | level=3
button | "SẢN PHẨM" | id=1105 | expanded
  checkbox | "Áo Blazer" | id=1111
  checkbox | "Áo Polo ngắn tay" | id=1150
```
This tells you: There's a filter group called "SẢN PHẨM" (Products) with checkboxes for each category.

**Product links**: Find product cards
```
link | id=2639 | url=https://aristino.com/products/ao-polo-ngan-tay-nam-...
```
URLs containing `/products/` are individual product pages.

**Pagination**: Find "Load More" or "View All" buttons
```
button | "Xem tất cả" | id=XXXX
```

### Step 3: Write the Recipe (`aristino_recipe.py`)
The Recipe is a semi-automated exploration script that:
1. Connects to Chrome CDP
2. Navigates to the target page
3. Gets AX tree dynamically (waits with retry loop)
4. Finds and clicks navigation elements
5. Extracts filter options
6. Allows interactive CLI selection

Key pattern — Dynamic element finding with retry:
```python
trang_phuc_node = None
for attempt in range(15):  # Wait up to 15 seconds
    nodes = await get_ax_tree(page)
    trang_phuc_node = find_node_by_text_and_role(nodes, "TRANG PHỤC", "link")
    if trang_phuc_node:
        break
    await asyncio.sleep(1)
```
Why 15 retries? Some pages load AX tree content asynchronously. Need patience.

### Step 4: Write the Full Scraper (`aristino_scraper.py`)
The full scraper automates the entire URL collection process:

1. Connect to Chrome CDP
2. Navigate to collection page directly
3. Set viewport to 1920x1080 (IMPORTANT: prevents mobile layout)
4. Clean popup overlays via JavaScript
5. Extract all category checkboxes from the "SẢN PHẨM" filter group
6. For EACH category:
   a. Uncheck all other categories first
   b. Check only this category
   c. Wait for filter to apply (3 seconds)
   d. Click "Xem tất cả" (View All) repeatedly until all products load
   e. Extract all product URLs from the DOM
   f. Save results incrementally to JSON
   g. Uncheck this category before moving to next

## Extracting Categories from AX Tree
The `extract_categories()` function is critical. It:
1. Builds `id_map` and `children_map` from nodes
2. For each checkbox node, walks up the tree to find which filter group it belongs to
3. Uses the `find_group_for_node()` algorithm (checks node names AND sibling names)
4. Returns list of `{name, bid (backendDOMNodeId), checked}` for each category checkbox

## Toggling Checkbox State
The `toggle_checkbox()` function:
1. Cleans popup overlays first
2. Gets fresh AX tree (tree changes after clicks!)
3. Finds the category by name
4. Checks current state vs desired state
5. If already in desired state, skip
6. Otherwise, click via CDP
7. Polls AX tree every 1.5 seconds for up to 10 attempts to verify state changed
8. This verification loop is essential — some sites update filters asynchronously

## Extracting Product URLs
```python
def extract_product_urls(nodes):
    urls = set()  # Use set for deduplication
    for n in nodes:
        if get_role(n) == "link":
            props = get_props(n)
            url = props.get("url", "")
            if "/products/" in url:  # Filter for product links only
                clean_url = url.split("?")[0]  # Remove query params
                if clean_url.startswith("/"):
                    clean_url = "https://aristino.com" + clean_url
                urls.add(clean_url)
    return list(urls)
```
Key decisions:
- Use `set()` to auto-deduplicate (products appear in multiple places on page)
- Split on `?` to remove tracking parameters
- Handle relative URLs by prepending domain
- Filter by `/products/` in URL path

## Handling "Load More" / Infinite Scroll
Many e-commerce sites don't show all products at once.
Pattern used:
```python
while True:
    nodes = await get_ax_tree(page)
    urls = extract_product_urls(nodes)
    if len(urls) >= total_count:
        break  # All products loaded
    xem_tat_ca_btn = find_button_by_text(nodes, "xem tất cả")
    if not xem_tat_ca_btn:
        break  # No more "Load More" button
    await click_node_via_cdp(page, xem_tat_ca_btn.bid)
    await asyncio.sleep(3)  # Wait for AJAX to load new products
```

## Getting Total Product Count
Use regex to find text like "1363 sản phẩm" in AX tree:
```python
def get_total_product_count(nodes):
    for n in nodes:
        if get_role(n) == "StaticText":
            match = re.search(r"(\d+)\s+s\u1ea3n\s+ph\u1ea9m", get_name(n), re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None
```

## Output Format
`scraped_products.json`:
```json
{
  "Áo Blazer": [
    "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm040z",
    "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm030z"
  ],
  "Áo Polo ngắn tay": [
    "..."
  ],
  "Quần Âu": [
    "..."
  ]
}
```

## Cleaning Popups
Many Vietnamese e-commerce sites have aggressive popups. Clean them:
```python
async def clean_popups(page):
    await page.evaluate("""() => {
        const selectors = [
            '#antsomi-slidedown-container',
            'div[id*="slidedown"]',
            'div[class*="popup"]',
            'div[class*="modal"]',
            '.modal-backdrop'
        ];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.remove());
        });
    }""")
```
Also try: `await page.keyboard.press("Escape")` to dismiss modal dialogs.
