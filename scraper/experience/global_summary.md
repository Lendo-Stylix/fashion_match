# Global Crawler Summary

This document provides a high-level summary of the traits, platform characteristics, and scraping status of the Canifa website in this project.

## 1. Canifa
- **Platform**: Nuxt.js headless storefront powered by a Magento 2 backend API.
- **Status**: Scraped successfully (1,145 unique products, 13,416 variants harvested).
- **Filters Applied**:
  - Excluded kids' products (Bé trai, Bé gái, Trẻ em, sơ sinh) based on URL patterns, product titles, category mappings, and SKU prefixes (starts with "2" or "7").
  - Excluded underwear items (Đồ lót, Sịp, Boxer, Bra, Panties).
  - Kept swimwear (Đồ bơi) and socks/stockings (Tất, Vớ) as exceptions.
- **Key Characteristics**:
  - **Data Structure**: Nuxt serialized state (`window.__NUXT__`) and Elasticsearch proxy API (`https://canifa.com/v1/middleware/search_product`).
  - **Discovery & Harvest**: Direct Elasticsearch paginated queries allow fetching full product listing details (including materials, specifications, and complete variant arrays) without loading individual product detail pages, completing the crawl of the entire store in less than 60 seconds.
  - **Option Mapping (Pinia State)**: Mapped variant option IDs (such as size/color numeric values) by parsing the global Pinia `customAttributeMetadata` list inside the Nuxt state, which provides a key-value dictionary for colors and sizes.
  - **Images**: Prepended `https://media.canifa.com/catalog/product` to all relative CDN paths. Retained absolute image URLs instead of downloading locally.

## 2. Yody
- **Platform**: Client-side React Router application with server-side rendered state variables.
- **Status**: Scraped successfully (690 unique products, including variants harvested).
- **Filters Applied**:
  - Excluded kids' products (Bé trai, Bé gái, Trẻ em, sơ sinh) based on category paths, titles, and URLs.
  - Excluded underwear items (Đồ lót, Sịp, Boxer, Bra, Panties) while keeping swimwear (Đồ bơi) and socks/stockings (Tất, Vớ).
- **Key Characteristics**:
  - **Data Structure**: Initial products list is embedded in `self.products`, metadata in `self.metadata`, category tree in `self.categories`, and individual PDP details are embedded as stringified JSON in `self.PDPData`.
  - **Discovery & Harvest**: Discovery utilizes raw HTML category fetches combined with backend API pagination query requests (`https://yody.vn/api/products?category_id=<id>&limit=24&page=<page>`) to retrieve the full list of products. Harvesting fetches individual PDPs concurrently (with a rate-limit semaphore) and decodes `self.PDPData`.
  - **PDP JSON Decoding**: Decodes the backslash-escaped JSON string literal in `self.PDPData` using a Python double `json.loads` sequence: `json.loads(json.loads(escaped_string))`.
  - **Deduplication**: Query parameters are stripped from product handles to ensure color variations are not fetched repeatedly, saving substantial bandwidth.
  - **Images**: Kept absolute image URLs (starting with `https://buggy.yodycdn.com/`) instead of downloading files locally to preserve disk space.

## 3. Juno
- **Platform**: **Next.js 14+ App Router** (React Server Components) với backend **OneLife.vn SaaS** (multi-tenant, domain `onelife-api.juno.vn`).
- **Status**: Scraped successfully (**318 unique products, 1.827 variants** harvested).
- **Filters Applied**:
  - Included: Giày (xăng đan, cao gót, búp bê, sneakers, dép guốc), Túi (nhỏ/trung/lớn, balo, ví-clutch), Phụ Kiện (mắt kính, nón, móc khóa, phụ kiện tóc, vớ), Quần Áo (đầm/jumpsuit, áo, quần, váy, khoác).
  - Excluded: Juno Beauty (trang điểm, chăm sóc da/cơ thể/tóc — mỹ phẩm), Set Quà Tặng (không phải thời trang). Không có sản phẩm trẻ em trên Juno.
- **Key Characteristics**:
  - **Khám Phá API**: Trang dùng RSC streaming — `"products": []` trong RSC payload (load client-side). Tìm API thực bằng cách phân tích JS bundle `2608-*.js` → phát hiện base `https://onelife-api.juno.vn/v1`.
  - **Products Endpoint**: `GET /products/categories/{slug}/products?page={n}&limit={limit}&order=NEWEST&direction=DESC` — trả về đầy đủ thông tin sản phẩm + variants trong một lần call, không cần fetch từng PDP.
  - **Filters Endpoint**: `GET /products/categories/{slug}/filters` — trả về attribute ID→Name mapping cho màu sắc và kích thước.
  - **Color Extraction**: Tên màu lấy từ `variant.media[i].title` (media item với `itemType == "primary"`), không phải từ variant attributes.
  - **Size ID Resolution**: Sử dụng global fallback dict `{171:XL, 172:L, 173:S, 174:M}` vì một số danh mục quần áo không trả về đầy đủ size options trong filters API.
  - **Image Filtering**: Filter bỏ URL `img.onelife.vn/rs:fit:60:60` (color swatch thumbnails 60×60) từ mảng images. Lưu URL tuyệt đối từ `static.juno.vn`.
  - **No Product Detail API**: Không có `/v1/products/{id}` endpoint — toàn bộ dữ liệu variant đã nằm trong category products response.
  - **Deduplication**: Product ID-based deduplication (dùng `seen_ids: set`) giữa các danh mục để tránh sản phẩm xuất hiện ở nhiều category.
  - **Không có `product detail API`**: `descriptionJson` thường rỗng cho sản phẩm thời trang Juno.

## 4. GUMAC
- **Platform**: React SPA storefront giao tiếp với REST CMS API.
- **Status**: Scraped successfully (711 unique products, 5018 variants).
- **Filters Applied**:
  - Excluded kids' products, shoes, and underwear locally using `EXCLUDE_KEYWORDS`.
- **Key Characteristics**:
  - **Data Structure**: CMS REST API at `https://cms.gumac.vn/api/v1/products` returns complete lists of products with color galleries and size guides.
  - **No Listing Prices**: The listing API returns 0 for prices, so prices default to 0.
  - **Variant Construction**: Colors and sizes are combined to form variants. Images are mapped dynamically per color from `color[i].media.gallery`.

## 5. Aristino
- **Platform**: Shopify.
- **Status**: Scraped successfully (49 unique products, 289 variants).
- **Filters Applied**:
  - Excluded kids' products, shoes, and underwear using keyword checks.
- **Key Characteristics**:
  - **Data Structure**: Shopify collection JSON endpoint at `/collections/all/products.json?limit=250&page={n}`.
  - **Variants & Options**: Standard Shopify variant options. Mapped dynamically to colors and sizes based on index lookup.

## 6. Coolmate
- **Platform**: Next.js 14+ App Router (RSC).
- **Status**: Scraped successfully (377 unique products, 5939 variants).
- **Filters Applied**:
  - Excluded underwear and accessories, kids' items are not present.
- **Key Characteristics**:
  - **Data Structure**: Hydration next_f pushes contain products list in RSC format. Extracted via regex and JSON load of unescaped text.
  - **CDN Images**: Image paths starting with `/image/` are prepended with `https://media.coolmate.me`.

## 7. Elise
- **Platform**: Magento 2.
- **Status**: Scraped successfully (978 unique products, 2920 variants).
- **Filters Applied**:
  - Excluded kids' products, shoes, and accessories from category structure.
- **Key Characteristics**:
  - **Data Structure**: Magento 2 GraphQL API at `/graphql` query.
  - **Single Color Configurable**: Colors are represented as distinct product entries varying by size. Colors extracted from titles.

## 8. Dirtycoins
- **Platform**: Haravan (Shopify-like e-commerce JSON API structures).
- **Status**: Scraped successfully (225 unique products harvested).
- **Filters Applied**:
  - Excluded kids' products (except "baby tee" and color names like "baby pink/blue") using checks on product titles and tags.
  - Excluded underwear items (except socks/stockings) and footwear (slides, shoes).
  - Excluded cosmetics and makeup.
- **Key Characteristics**:
  - **Data Structure**: Product lists and variant details are fetched directly from `/collections/all/products.json?limit=50&page={page}`.
  - **Option Mapping**: Dynamically maps color and size option values by tracking option name indices in the product metadata, ensuring robust color/size extraction.
  - **Specifications Parsing**: Extracts specifications such as material ("cotton", "polyester") and form ("Regular", "Relaxed Fit") directly from description text blocks.
  - **Images**: CDN image URLs (`https://cdn.hstatic.net/...`) are stored directly without local downloads. Variant images are matched via `image_id` lookup.

## 9. Levents
- **Platform**: **Storecake** (Pancake.vn multi-tenant e-commerce system).
- **Status**: Scraped successfully (73 unique products, including variants harvested).
- **Filters Applied**:
  - Excluded footwear (slides, shoes) such as "Levents® Everstar Slide".
  - Excluded gift/promotional items starting with `[Hàng tặng` or containing `quà tặng` (such as `[Hàng tặng không thu tiền] Levents® XL Cup`).
  - Excluded kids' products, underwear (except socks), and cosmetics/makeup.
  - Kept socks/stockings (tất, vớ) as exceptions.
- **Key Characteristics**:
  - **Data Structure**: Storecake API endpoint at `/view/products` expects a POST request with `site_id: "af59cab4-c62d-4826-8e90-807ce1c501df"`, `category_id: "all_products"`, and query slugs to fetch products in JSON format.
  - **Discovery & Harvest**: Fast, clean backend API retrieval (get_dom=false) to get all raw product listings, variant fields, stock, and descriptions without browser rendering.
  - **Option Mapping**: Resolves variant attributes (Color and Size options) dynamically by scanning the pairs in the variant `fields` array.
  - **Size Guide Image**: Extracted from the HTML images embedded in the `short_description` array blocks.
  - **Images**: Main product images collected by merging all variant-specific image lists from the Pancake CDN (`https://content.pancake.vn/...`). Links are stored as absolute URLs without local downloads.

## 10. YaMe.vn
- **Platform**: Shopify.
- **Status**: Scraped successfully (1,402 unique products, 5,393 variants harvested).
- **Filters Applied**:
  - Excluded kids' products (bé trai, bé gái, trẻ em, sơ sinh, em bé) based on title/tags, using regex word boundary limits to avoid false positives (e.g., baby tee, baby pink, baby blue exceptions).
  - Excluded underwear items (đồ lót, sịp, boxer, bra, panties), using regex word boundaries to avoid matching the nhãn hiệu "Non Branded".
  - Excluded footwear (slides, giày, dép, sandal, sneaker, boots, loafer) and cosmetics/makeup.
  - Kept swimwear (đồ bơi) and socks/stockings (tất, vớ) as exceptions.
- **Key Characteristics**:
  - **Data Structure**: Standard Shopify e-commerce backend. List data is fetched directly using `/products.json?limit=250&page={page}`.
  - **Discovery & Harvest**: Global products endpoint paginated requests fetch the complete catalog in 6 pages. High speed and low overhead compared to individual PDP crawls.
  - **Color in Title**: Colors are represented as distinct product entries rather than variants under the same product. The color name is parsed from the title (e.g., "Màu Đen 99" or "Màu Trắng 11") and mapped to `option1` in our variants dataset.
  - **Option Mapping**: Sizes (S, M, L, XL, XXL) are resolved from the product options list (under names "Size" or "Kích Cỡ") and mapped to `option2` of variants.
  - **Specifications (Material/Fit)**: Extracted detailed specifications such as fabric composition ("94% Cotton, 6% Spandex") from both HTML `<li>` items and plain text lists in `body_html`. Fit style ("Dáng Hộp F5", "Dáng Vừa Vặn F3") extracted from titles.
  - **Images**: Shopify absolute CDN URLs (`https://cdn.shopify.com/s/files/...`) are saved directly without local downloads.


## 11. Uniqlo
- **Platform**: **Custom REST API** (Fast Retailing Backend API v5).
- **Status**: Scraped successfully (664 unique products, 7,593 variants harvested).
- **Filters Applied**:
  - Excluded kids' products (Bé trai, Bé gái, Trẻ em, sơ sinh, em bé) from taxonomy categories and product titles.
  - Excluded underwear items (Đồ lót, Sịp, Boxer, Brief, Bra, Panties, Innerwear) from category structures and titles while keeping swimwear (Đồ bơi) and socks/stockings (Tất, Vớ) as exceptions.
  - Excluded footwear (Giày, Dép, Sandal, Sneaker).
- **Key Characteristics**:
  - **Data Structure**: Product list data and taxonomy hierarchy are retrieved directly from endpoints like `/api/commerce/v5/vi/products` and `/api/commerce/v5/vi/products/taxonomies`.
  - **Client ID Identification**: Queries to the internal v5 API return a 400 Bad Request if missing custom headers. Handled by passing `x-fr-clientid: uq.vn.web-spa` and `x-fr-client-version: 3.2506.1`.
  - **Dynamic Breadcrumbs Mapping**: Mapped and categorized products dynamically using the `breadcrumbs` dictionary inside the details response (which lists `gender`, `class`, and `category` meta-information).
  - **Variant & Option Extraction**: Extracted variant options (Colors like `00 WHITE`, sizes like `S`, `M`, `L`, `XL`), prices (mapping base vs promo dynamically), and SKU details (`communicationCode` as SKU) from the detailed product `l2s` array.
  - **Safe Multi-Threading**: Used a ThreadPoolExecutor with 4 concurrent workers and a 0.2s delay to complete detail scraping for all 660+ products in under 1.5 minutes without triggering IP blocking.
  - **Images**: Stored absolute image URLs (`https://image.uniqlo.com/...`) directly without local downloads to optimize storage. Mapped specific variant images to main color swatches.
  
## 12. H&M
- **Platform**: Next.js Server-Side Rendered (SSR) storefront.
- **Status**: Scraped successfully (crawling in progress).
- **Filters Applied**:
  - Excluded kids' products (bé trai, bé gái, trẻ em, sơ sinh, em bé, kids, baby) and shoes/footwear using string matching on title and category tags.
  - Excluded underwear items (đồ lót, sịp, boxer, bra, panties, innerwear) while keeping swimwear (đồ bơi) and socks/stockings (tất, vớ, socks) as exceptions.
  - Excluded cosmetics and makeup (mỹ phẩm, trang điểm).
- **Key Characteristics**:
  - **Data Structure**: Extracts product catalog and variant lists from the embedded Next.js SSR `__NEXT_DATA__` state dictionary.
  - **Discovery & Harvest**: Discovery crawls the master category listing pages (`/nam/san-pham/xem-tat-ca.html` and `/nu/goi-y-san-pham/xem-tat-ca.html`) to discover 959 unique style IDs.
  - **Style ID Grouping**: Groups color variations by Style ID (first 7 digits of the 10-digit code) and fetches only one PDP per style, reducing the number of PDP page loads by 85%–90%.
  - **Live Availability API**: Queries H&M's global VN availability API gateway (`https://ofg.hm.com/pdh-availability/v1/product/vn/availability/{style_id}`) inside the page context using `page.evaluate()` to safely fetch live size stock and bypass Akamai blocks.
  - **Images**: Saves absolute CDN URLs (`https://image.hm.com/...`) directly without downloading locally.

## 13. 4MEN
- **Platform**: Custom PHP/MySQL platform (Generator "4MEN").
- **Status**: Scraped successfully (889 unique products, 2,764 variants harvested).
- **Filters Applied**:
  - Excluded kids' products (bé trai, bé gái, trẻ em, sơ sinh, em bé, kids, baby) and shoes/footwear using string matching on title and category tags.
  - Excluded underwear items (đồ lót, sịp, boxer, bra, panties, innerwear) while keeping socks/stockings (tất, vớ, socks) as exceptions.
  - Excluded cosmetics and makeup (mỹ phẩm, trang điểm).
- **Key Characteristics**:
  - **Data Structure**: Product detail pages embed variant information (SKU, brand, price, name, ID) inside a Google Tag Manager `dataLayer.push` block with `'event': 'productDetail'`.
  - **Discovery & Harvest**: Discovery crawls category pages (e.g. `/ao-so-mi-nam.html` and `/ao-so-mi-nam/trang-2.html`) directly via HTTP requests. Unique color variations are listed as specific links in the product list cards (inside `.item-thumbs .pc-wrap a`) and crawled as separate product entries to preserve detailed images and color-specific SKUs.
  - **Specifications Parsing**: Detailed materials (such as Bamboo, Poly, Spandex ratios) and phom dáng (Slimfit, Regular) are parsed from bullet points inside the `.details-box.html-content` or `.accordion-content` text block using regex.
  - **Images**: Saves absolute CDN URLs (`https://4men.com.vn/images/...`) from the gallery slider (`.prod-slider.sync1 img`) directly without downloading locally.
  
## 14. 5S Fashion
- **Platform**: Custom Laravel platform.
- **Status**: Scraped successfully (1,070 unique products, 17,351 variants harvested) — [5sfashion_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/5sfashion/output/5sfashion_products_full.json).
- **Filters Applied**:
  - Excluded kids' products (Bé trai, Bé gái, Trẻ em, sơ sinh) using category mappings and regex word checks.
  - Excluded underwear items (Quần lót, áo lót, sịp, boxer) while keeping socks/stockings (Tất, Vớ) as exceptions.
  - Excluded footwear (giày, dép, sandal, sneaker) and cosmetics/makeup.
- **Key Characteristics**:
  - **Data Structure**: Uses custom Laravel filter endpoint `/filter?category={id}&page={page}` returning JSON with `content` containing product card HTML list, `total` product count, and `filter` options HTML.
  - **Discovery & variant-SKU Mapping**: Discovery queries categories page by page using AJAX `/filter` to fetch all product URLs and a map of `variant_id -> SKU` (parsed from list page product card hidden inputs). This maps SKUs on PDP pages where `data-sku` is empty. Script: [5sfashion_scraper.py](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/experience/5sfashion/5sfashion_scraper.py).
  - **Swatch & Option Mapping**: Resolves options by scanning the color swatch list `.variant-color li` (extracting `data-color`, `data-product-color-id` and variant image `data-src`) and size list `.variant-size li` (extracting `data-size` and `data-size-id`).
  - **Heuristics Spec Parsing**: Extracts specifications such as material composition (e.g. `95% Sợi Cotton; 5% Spandex`), form dáng (fit), and design/pattern (họa tiết) from the description block `.content-desc` using a heuristic text matching approach.
  - **Images**: Standardizes CDN image paths to high resolution `/fast/1325x0/` format. Saves absolute URLs without local downloads.

## 15. Teelab
- **Platform**: Sapo / Bizweb E-Commerce System.
- **Status**: Scraped successfully (117 unique products, 1,133 variants harvested) — [teelab_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/teelab/output/teelab_products_full.json).
- **Filters Applied**:
  - Excluded kids' products, shoes/footwear, underwear (except socks), and cosmetics/makeup using word boundaries and keywords checks on product name, tags, and type.
  - Kept socks/vớ as exceptions.
- **Key Characteristics**:
  - **Data Structure**: Sapo public endpoint `/products.json?limit=250&page={page}` returns clean JSON with full title, type, tags, variants, options, and HTML descriptions.
  - **Discovery & Harvest**: Discovery queries the catalog page directly using Sapo public products listing endpoint. Harvesting parses variants, options, absolute CDN image paths (`https://bizweb.dktcdn.net/`), and specs directly from the API response without individual PDP loads. Script: [teelab_scraper.py](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/experience/teelab/teelab_scraper.py).
  - **Option Mapping**: Dynamically tracks color and size option indices to map variant options to `option1` (color) and `option2` (size).
  - **Heuristic Specs Parser**: Uses Regex to clean the HTML description block and extract structured specifications (`Mã sản phẩm`, `Chất liệu`, `Form dáng`, `Họa tiết`, `Màu sắc`, `Xuất xứ`).
  - **Images**: Keeps absolute CDN paths and replaces schema-relative `//` prefixes with `https:`. No local image downloads.

## 16. Degrey
- **Platform**: Haravan (Shopify-like e-commerce SaaS architecture).
- **Status**: Scraped successfully (49 unique products, 147 variants harvested) — [degrey_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/degrey/output/degrey_products_full.json).
- **Filters Applied**:
  - Excluded kids' products (bé trai, bé gái, trẻ em, sơ sinh) and footwear (giày, dép, sandal, sneaker) using word boundary checks.
  - Excluded underwear items (đồ lót, sịp, boxer) while keeping swimwear/socks. Successfully filtered out activewear `Sport Bra` under this rule.
  - Excluded cosmetics and makeup.
- **Key Characteristics**:
  - **Data Structure**: Haravan collections API endpoint at `/collections/all/products.json?limit=250&page={page}`. It returns the entire catalog details in one load, bypassing the need to scrape separate product pages.
  - **Color & Option Mapping**: Color resolved by scanning titles against sorted known color phrases (such as `WAX XÁM`, `ĐEN VÀNG`), checking SKU suffixes, and description tables. Mapped color to `option1` and size to `option2` (which is stored in `option1` of Haravan raw variant data, normalized to `FREESIZE` for default options).
  - **HTML Table Specifications Parsing**: Extracted detailed specs (Chất liệu, Form dáng, Họa tiết, Màu sắc, Sản xuất) from description tables using `BeautifulSoup` search, with regex logic as a fallback for unstructured texts.
  - **Images**: Kept absolute CDN image URLs (`https://cdn.hstatic.net/...`) instead of local downloads. Mapped specific variant images to their corresponding color-specific media items using Haravan's `image_id` lookup.

## 17. Bad Rabbit
- **Platform**: Haravan (Shopify-like e-commerce SaaS architecture).
- **Status**: Scraped successfully (45 unique products, 215 variants harvested) — [badrabbit_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/badrabbit/output/badrabbit_products_full.json).
- **Filters Applied**:
  - Excluded kids' products (bé trai, bé gái, trẻ em, sơ sinh, em bé, kids, baby, etc.) while keeping character name references (e.g., "Kid Rabbit" tee for adults) and adult streetwear styles (e.g., "baby tee", "baby pink" / "baby blue" colorways).
  - Excluded underwear items (đồ lót, sịp, boxer) and footwear (giày, dép, slides, sneakers).
  - Excluded cosmetics and makeup (mỹ phẩm, trang điểm).
- **Key Characteristics**:
  - **Data Structure**: Haravan collections API endpoint at `/collections/all/products.json?limit=250&page={page}`. It returns the entire catalog details in one load, bypassing the need to scrape separate product pages.
  - **Option Mapping**: Dynamically tracks color and size option indices to map variant options to `option1` (color) and `option2` (size). If options are missing, defaults color from title/specs and size to `"FREESIZE"`.
  - **Heuristic Specifications Parsing**: Extracted detailed specs (`Chất liệu`, `Form dáng`, `Màu sắc`, `Kỹ thuật`, `Phụ kiện`, `Họa tiết`, `Sản xuất`) from description list bullet points using a line-by-line regex parser, with fallback searches on HTML text.
  - **Images**: Keeps absolute CDN paths and replaces schema-relative `//` prefixes with `https:`. No local image downloads.

## 18. City Cycle
- **Platform**: **Nhanh.vn** (vietnamese local e-commerce platform).
- **Status**: Scraped successfully (140 unique products, 775 variants harvested) — [citycycle_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/citycycle/output/citycycle_products_full.json).
- **Filters Applied**:
  - Excluded kids' products, shoes/footwear, cosmetics, and underwear using keyword checks on titles and URL paths.
  - Kept socks/stockings (tất, vớ) and swimwear (đồ bơi) as exceptions.
- **Key Characteristics**:
  - **Discovery**: Simple page-by-page crawling using query parameter `?page=N`. Paging limits are dynamically parsed from pagination labels like `1 - 24 / 84` or `totalPages` selector.
  - **Option Mapping**: Swatches resolve color name and `data-pids` array (e.g. `data-pids="id1,id2,id3"`). Size Swatches align 1-1 by order index to map specific variant IDs.
  - **Live Inventory Endpoint**: Checks stocks of all variants by calling POST `/product/checkinventory` directly with list of variant IDs in batches of 50, resulting in high accuracy and performance.
  - **Heuristics Spec Parser**: Parses material composition, form/fit, and prints using regex patterns matching headings like `Chất liệu & Tính năng:` or `Kiểu dáng:` inside description paragraphs.
  - **Images**: Retained absolute CDN URLs (starting with `https://pos.nvncdn.com/`) directly without local downloads.

## 19. Under Armour Vietnam
- **Platform**: Shopify.
- **Status**: Scraped successfully (668 unique products, 2,999 variants harvested) — [underarmour_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/underarmour/output/underarmour_products_full.json).
- **Filters Applied**:
  - Excluded kids' products, shoes/footwear, underwear, and cosmetics using strict word boundary and keyword checks on titles, product types, handles, and tags.
  - Kept swimwear (đồ bơi, swim) and socks/stockings (tất, vớ, socks) as exceptions.
- **Key Characteristics**:
  - **Data Structure**: Shopify public storefront API at `/products.json?limit=250&page={page}` allows clean, structured JSON parsing without browser automation.
  - **Option Mapping**: Scans the `options` metadata array to detect color and size indices dynamically. Maps them to the project standard `option1` (color) and `option2` (size) for all variants.
  - **Heuristics Specifications Parser**: Parses HTML elements (`<li>`) and text from `body_html` to extract style codes, material compositions (percentage matching), fit styles (form dáng), and proprietary technology labels (such as HeatGear, Iso-Chill, Storm).
  - **Images**: Retained absolute CDN image URLs (starting with `https://cdn.shopify.com/...`) instead of downloading files locally to optimize storage.

## 20. Owen.vn
- **Platform**: **Magento 2** with public client-side **GraphQL API** gateway (`/graphql`).
- **Status**: Scraped successfully (1,132 unique products, 5,704 variants harvested) — [owen_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/owen/output/owen_products_full.json).
- **Filters Applied**:
  - Excluded kids' products, shoes/footwear, underwear (except socks/stockings and swimwear), cosmetics/makeup via title keyword checks.
  - Kept swimwear (đồ bơi), socks/stockings (tất, vớ), belts (dây lưng), wallets (ví da), and ties (cà vạt) as accessories.
- **Key Characteristics**:
  - **GraphQL Data Extraction**: Products list, HTML description, variant attributes, stock status, and prices were fetched directly in batches of 50 products per category request via `/graphql`, completing the harvesting of 1,100+ items in less than 90 seconds without browser overhead.
  - **SKU Inference**: Missing SKUs on parent simple products (socks, accessories) were dynamically inferred from title text using a regex alphanumeric scanner matching standard code formats (such as `TA252530`, `BELT261059`).
  - **Simple Products Mapping**: Custom default variants with size `"FREESIZE"` were generated for simple products lacking variations, mapping the parent price, stock, and image parameters.
  - **Variant Availability**: Derived stock availability per variant directly from the GraphQL response `stock_status` parameter (`IN_STOCK` vs `OUT_OF_STOCK`), ensuring maximum accuracy.
  - **Images**: Retained absolute CDN image URLs (`https://owen.cdn.vccloud.vn/`) directly. Filtered out Magento default `/placeholder/` images and set child variants to parent color-specific gallery images.



