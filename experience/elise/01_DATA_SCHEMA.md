# Elise Data Schema

Elise product data is extracted from the Magento 2 backend SSR (Server-Side Rendered) HTML. Below is the detailed schema of the harvested product objects.

## Product Level Fields
- `id` (string): The base SKU of the product.
- `handle` (string): The slug of the product from the URL (without `.html`).
- `title` (string): Product title (html-decoded).
- `vendor` (string): Brand name ("Elise").
- `type` (string): Product category (e.g., "Đầm", "Chân Váy").
- `description` (string): Detailed HTML copy of the product description.
- `available` (boolean): Availability of the product (True if any variant has stock > 0).
- `tags` (list of strings): SEO and categorization tags (empty list if not found).
- `images` (list of strings): Absolute URLs of product gallery images.
- `featured_image` (string): The primary display image.
- `options` (list of strings): Available options (e.g., `["Kích thước"]`).
- `url` (string): Direct product URL on the Elise store.
- `price` (float): Product price (VND).
- `compare_at_price` (float/null): Original retail price before discounts.

## Variant Level Fields (inside `variants` list)
- `id` (int): Unique variant ID (simple product ID in Magento).
- `sku` (string): Variant specific SKU (base SKU + size, e.g. `FS2601357DIORPL_S`).
- `title` (string): Size name (e.g. "S", "M", "L").
- `option1` (string): Size option value.
- `price` (float): Variant specific price.
- `compare_at_price` (float/null): Original price for this size.
- `available` (boolean): In stock?
- `inventory_quantity` (float): Exact quantity of stock available for this specific size.
