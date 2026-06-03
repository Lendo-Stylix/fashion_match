# Aristino Data Schema

The scraped product data from Aristino (Haravan platform) is extracted as a structured JSON object. Below is the detailed schema and data fields available for each product.

## Product Level Fields
- `id` (int): Unique product ID on Haravan.
- `handle` (string): The slug used in the product URL (e.g., `ao-khoac-blazer-nam-aristino-abzm040z`).
- `title` (string): Full product title.
- `vendor` (string): Brand name (e.g., "Aristino").
- `type` (string): Product category type (e.g., "Áo Blazer").
- `description` (string): HTML formatted description containing form, design, material, and size info.
- `price`, `price_min`, `price_max`, `compare_at_price` (float): Pricing information. *Note: Prices are in VND * 100 (e.g., 420000000.0 means 4,200,000 VND).*
- `available` (boolean): Overall availability of the product.
- `tags` (list of strings): SEO and internal categorization tags.
- `images` (list of strings): List of image URLs or local paths.
- `featured_image` (string): The primary image for the product.
- `options` (list of strings): The variant options available (e.g., ["Màu", "Kích thước"]).
- `url` (string): Relative URL path to the product page.
- `pagetitle`, `metadescription` (string): SEO metadata fields.
- `_scraped_category`, `_scraped_url` (string): Metadata added by the scraper (custom fields).

## Variant Level Fields (inside `variants` list)
Each product contains a list of variants (e.g., different sizes/colors).
- `id` (int): Unique variant ID.
- `sku`, `barcode` (string): Stock keeping unit and barcode for inventory tracking.
- `title` (string): Variant title (e.g., "Hồng 2 kẻ Jacquard / M").
- `option1`, `option2`, `option3` (string): The specific values for the options (e.g., "Hồng 2 kẻ Jacquard", "M").
- `price`, `compare_at_price` (float): Variant-specific pricing.
- `available` (boolean): Is this specific variant in stock?
- `inventory_quantity`, `old_inventory_quantity` (float): Exact stock counts.
- `weight` (float): Weight of the variant.
- `featured_image` (object): The specific image associated with this variant.
