# Aristino Extraction & Bypass Techniques

This document details the specific techniques used for extracting data and bypassing anti-bot mechanisms on the Aristino website (built on Haravan).

## 1. Embedded JavaScript JSON Extraction (Haravan/Shopify)
Aristino embeds full product data within a JavaScript object on the product page. This avoids the need to parse DOM elements.

Look for these patterns in the page source:

### Pattern A: `window.productDetail`
```javascript
window.productDetail = {
    data: { /* full product JSON */ },
    id: 1056322122,
    handle: "product-slug"
}
```
**Extraction Regex:**
```python
re.search(r'window\.productDetail\s*=\s*{\s*data:\s*({.*?})\s*,\s*id:', html, re.DOTALL)
```

### Pattern B: `productjson`
```javascript
productjson: { /* full product JSON */ },
template_suffix: null
```
**Extraction Regex:**
```python
re.search(r'productjson:\s*({.*?}),\n\s*template_suffix', html, re.DOTALL)
```

## 2. Popup and Overlay Removal
Vietnamese e-commerce sites, including Aristino, use aggressive marketing overlays that block CDP clicks (e.g., Antsomi marketing platform, newsletter popups).

**Clean Popups Script:**
```python
async def clean_popups(page):
    await page.evaluate("""() => {
        const selectors = [
            '#antsomi-slidedown-container',
            '.antsomi-slidedown-container',
            'div[id*="slidedown"]',
            'div[class*="slidedown"]',
            'div[class*="popup"]',
            'div[class*="modal"]',
            '.modal-backdrop'
        ];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.remove());
        });
    }""")
    await page.keyboard.press("Escape")  # Close any active modals
```
*Note: Run this function BEFORE attempting any click interactions via CDP.*

## 3. Price Handling Quirk
Haravan stores prices multiplied by 100.
For example, `420000000` in the JSON data represents `4,200,000₫` on the storefront. Always apply a `/ 100` division when presenting prices to the end user.

## 4. Image URL Formatting
Aristino stores image URLs as protocol-relative strings (e.g., `//product.hstatic.net/...`).
Before downloading, you must prepend `https:` to these URLs.
```python
def fix_url(url):
    if url and url.startswith("//"):
        return "https:" + url
    return url
```
