# Yody.vn Scraper Experience & Practical Insights

## 1. Platform Identification & Technical Context
- **Platform**: Yody.vn uses a client-side **React Router** application.
- **Key Discovery**: Rather than relying entirely on heavy AJAX calls or dynamic DOM changes that require Playwright browser automation, Yody pre-loads state variables into the raw HTML source code:
  - Product lists: Embedded in `self.products = [...]` inside a large `<script>` block.
  - Page Metadata: Embedded in `self.metadata = {...}`.
  - Category Tree: Embedded in `self.categories = [...]`.
  - Product Details: Embedded in `self.PDPData = "..."` on the product detail page.
- **Pagination API**: We discovered that when clicking "Xem thêm" (View more), the page calls a backend products API directly:
  `https://yody.vn/api/products?category_id=<category_id>&limit=<limit>&page=<page>`
  This API returns clean JSON containing `items` and `metadata`, allowing us to paginate without browser rendering.

---

## 2. Issues Encountered & Solutions

### Issue 2.1: Massive Category Page HTML Source Size
- **Symptom**: Fetching Yody's category landing pages via `urllib` returns a massive HTML document (often **30+ MB**).
- **Reason**: The page embeds `self.currentCategory`, which contains a highly recursive tree of all categories on the site (including all children and sibling structures).
- **Solution**: Regular expressions targeting simple brackets like `re.search(r'self\.products = (\[.*?\])', html)` fail because they stop at the first internal bracket of the JSON. Instead, we use a robust regex bounded by neighboring JS variables:
  `re.search(r'self\.products\s*=\s*(.*?)\s*;?\s*self\.metadata\s*=', html, re.DOTALL)`
  This extracts the exact JSON substring reliably.

### Issue 2.2: Escaped JSON in `self.PDPData`
- **Symptom**: On the product page, `self.PDPData` is not a raw JS object literal. It is rendered as a double-quoted string literal containing stringified JSON (escaped quotes `\"` and backslashes `\\`).
- **Solution**: In Python, we extract the string block and perform a **double JSON load**:
  1. `decoded_str = json.loads(f'"{prepared_str}"')` -> resolves JS escape sequences into a raw JSON string.
  2. `pdp_data = json.loads(decoded_str)` -> parses the raw JSON string into a Python dictionary.

### Issue 2.3: Playwright Navigation Timeout
- **Symptom**: When attempting Playwright browser recon, `page.goto` times out because of `wait_until="networkidle"`.
- **Reason**: Yody runs aggressive background script loops for Facebook Pixel, Google Tag Manager, and Cloudflare RUM. The network is never idle.
- **Solution**: Bypassed browser automation entirely. All data is fetched via standard async HTTP GET requests (`aiohttp`), which are faster, safer, and 100% headless.

---

## 3. Best Practices & Optimization Notes
- **Deduplication**: Yody listing pages return different URL suffixes for different colors of the same product (e.g., `slug?color=765&size=1`). To avoid fetching the same product page multiple times, we strip all query parameters from the slug:
  `clean_slug = slug.split('?')[0]`
  This successfully deduplicated the 700+ listing items down to unique product pages, reducing network overhead significantly.
- **Incremental Saves**: Discovery and Harvest phases save data after every category/batch. This protects against network dropouts or rate-limit blocks, allowing the scraper to resume from the last saved state.
