# Gumac Data Schema

Gumac product data is harvested using direct API calls. Below is the detailed schema and data fields available for each product.

## Product Level Fields
- `id` (int): Unique product ID.
- `handle` (string): The slug used in the product URL.
- `title` (string): Full product title.
- `vendor` (string): Brand name ("Gumac").
- `type` (string): Product category type (e.g., "Váy đầm").
- `description` (string): Clean plain-text parsed description copy for readable layout.
- `description_html` (string): HTML formatted raw description containing structural tags and image coordinates.
- `size_guide_image` (string): Absolute URL of the size guide/chart image (extracted from category metadata or description HTML).
- `price` (float): The final sale price of the first variant.
- `compare_at_price` (float): The original price before sale (if on sale).
- `available` (boolean): Overall availability of the product.
- `tags` (list of strings): Keywords/hashtags.
- `images` (list of strings): Absolute URLs to product gallery images (constructed by prepending `https://cms.gumac.vn` to CDN paths).
- `featured_image` (string): The primary image for the product.
- `options` (list of strings): Custom configuration options (e.g., `["Kích thước"]`).
- `url` (string): Direct URL path to the product page on the store website.
- `material` (string/null): Material specifications.
- `features` (list of strings): List of outstanding design features.

## Variant Level Fields (inside `variants` list)
- `id` (int): Unique variant ID.
- `sku` (string): Stock keeping unit for inventory tracking (e.g., `DF07008_VANG_L`).
- `title` (string): Variant title (e.g., "Vàng / L").
- `option1` (string): The color option value (e.g., "Vàng").
- `option2` (string): The size option value (e.g., "L").
- `price` (float): Variant-specific price.
- `compare_at_price` (float/null): Variant-specific compare price.
- `available` (boolean): Variant availability.
- `featured_image` (string): The specific color swatch image.
- `gallery` (list of strings): Image gallery associated with this specific color.
- `specifications` (object): Form Dáng, Chất Liệu, co giãn, túi, and body measurements (Ngực, Eo, Vai, Dài Tay, vv.).
