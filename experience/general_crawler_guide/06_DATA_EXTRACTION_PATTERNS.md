# Data Extraction Patterns for E-Commerce Sites

## Overview
This document catalogs general techniques used to extract structured data from e-commerce websites.
When approaching a new website, try these patterns in order of preference.

## Pattern 1: Embedded JavaScript JSON (Most Reliable)
Many modern e-commerce platforms embed product data as JavaScript objects in the page HTML.
This is the BEST source because it's structured, complete, and doesn't require rendering.

### Single-Page Apps (Next.js / Nuxt.js)
Single-Page Apps often store state in a script tag:
```html
<script id="__NEXT_DATA__" type="application/json">{...}</script>
<script id="__NUXT__">{...}</script>
```
Extraction:
```python
next_data = await page.evaluate('''
    () => {
        const script = document.getElementById('__NEXT_DATA__') || document.getElementById('__NUXT__');
        if (script) return script.textContent;
        return null;
    }
''')
```

## Pattern 2: JSON-LD Structured Data
SEO-compliant sites embed Schema.org JSON-LD in `<script type="application/ld+json">`:
```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Product Name",
  "url": "https://example.com/products/...",
  "image": "https://example.com/image.jpg",
  "brand": "Brand",
  "aggregateRating": { "ratingValue": "5", "ratingCount": "5" },
  "offers": []
}
```
Limitation: Usually has LESS detail than embedded JS (no variants, no inventory, no SKU).
But useful as a fallback or for brand/rating data.

Extraction:
```python
import re, json
ld_scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
for script_content in ld_scripts:
    data = json.loads(script_content)
    if data.get('@type') == 'Product':
        # Found product LD+JSON
```

## Pattern 3: AX Tree Static Text Extraction
When there's no embedded JSON, extract data from what's visible on the page.
The AX tree's `StaticText` nodes contain all visible text.

Use cases:
- Product name: Find heading nodes (`role=heading`) near product area
- Price: Find StaticText containing currency patterns
- Description: Find StaticText nodes within the product detail region
- Category labels: Find checkbox/link names in filter sidebars

## Pattern 4: API Endpoints Discovery
Some sites have REST APIs that return JSON directly.
Look in the JS source for API endpoint patterns:
```javascript
$.get('/cart.js')           // Cart API
'/api/products/list'        // Products API  
```

## Pattern 5: DOM Query via `page.evaluate()`
Last resort: Use JavaScript to query the DOM directly.
```python
data = await page.evaluate('''() => {
    const title = document.querySelector('h1.product-title')?.innerText;
    const price = document.querySelector('.product-price')?.innerText;
    return { title, price };
}''')
```
Downside: Relies on CSS selectors that change with redesigns.

## Choosing the Right Pattern
Decision tree:
1. Does the page have embedded JS object? → Use Pattern 1
2. Does the page have JSON-LD? → Use Pattern 2 (supplementary)
3. Is the site a SPA with `__NEXT_DATA__`? → Use Pattern 1 variant
4. None of above? → Use Pattern 3 (AX Tree) or Pattern 5 (DOM)

## Data Quality Checklist
After extraction, verify:
- [ ] Title is not empty
- [ ] Price is a valid number 
- [ ] At least one image URL exists and is accessible
- [ ] Product handle/slug is present for deduplication
- [ ] Variants have SKU codes
