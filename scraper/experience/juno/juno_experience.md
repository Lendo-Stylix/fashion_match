# Juno.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `juno.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Next.js 14+ App Router** với React Server Components (RSC) streaming.
- **Backend**: **OneLife.vn** — nền tảng SaaS thương mại điện tử (multi-tenant), chạy dưới subdomain `onelife-api.juno.vn`.
- **CDN Hình Ảnh**: `static.juno.vn` (ảnh sản phẩm chính) và `img.onelife.vn` (ảnh swatch màu nhỏ 60×60, dạng base64-encoded URL proxy).

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. API Sản Phẩm (Category Products)

```
GET https://onelife-api.juno.vn/v1/products/categories/{slug}/products
    ?page={n}&limit={limit}&order=NEWEST&direction=DESC
```

**Response trả về:**
```json
{
  "category": { "id": "...", "name": "Áo", "slug": "ao", ... },
  "pagination": { "current": 1, "total": 51, "last_page": 3, "limit": 20 },
  "products": [ ... ]
}
```

**Không cần auth header** — API hoàn toàn public với CORS mở cho `juno.vn`.

### 2.2. API Bộ Lọc (Category Filters)

```
GET https://onelife-api.juno.vn/v1/products/categories/{slug}/filters
```

Trả về danh sách bộ lọc với ID→Name mapping cho màu sắc và kích thước.

### 2.3. API Chi Tiết Danh Mục

```
GET https://onelife-api.juno.vn/v1/products/categories/{slug}
```

Trả về metadata danh mục (không có sản phẩm).

### 2.4. API Sản Phẩm Đơn Lẻ — KHÔNG TỒN TẠI

Các endpoint như `/v1/products/{id}`, `/v1/products/{slug}` đều trả về **404**. Dữ liệu chi tiết sản phẩm đã được nhúng đầy đủ trong response của category products API.

---

## 3. Cấu Trúc Dữ Liệu Sản Phẩm

Mỗi sản phẩm từ category API chứa các trường quan trọng:

```json
{
  "id": "338051780560554227",
  "name": "Áo thun polo phối viền",
  "slug": "ao-thun-polo-phoi-vien-YtsW",
  "description": "",
  "descriptionJson": { "highlights": "", "introduction": "", ... },
  "discountPercent": 23,
  "discountPrice": 309000,
  "originalPrice": 399000,
  "inStock": 329,
  "images": ["https://static.juno.vn/...", ...],
  "thumbnail": "https://static.juno.vn/...",
  "tickers": ["discount"],
  "attributes": [
    { "code": "variant_sizes", "value": "[\"172\", \"173\", \"174\"]" },
    { "code": "variant_colors", "value": "[\"61\", \"66\", \"70\"]" },
    { "code": "juno_item_type", "value": "Fashion" },
    { "code": "is_new", "value": "true" }
  ],
  "variants": [ ... ]
}
```

### 3.1. Cấu Trúc Variant

```json
{
  "id": "338051661375211763",
  "sku": "8935361447695",
  "name": "Áo thun polo phối viền",
  "discountPrice": 309000,
  "originalPrice": 399000,
  "stockItem": { "quantity": 58 },
  "media": [
    { "url": "...", "itemType": "primary", "title": "Nâu" },
    { "url": "...", "title": "Nâu" },
    { "url": "...", "itemType": "color", "title": "Nâu" }
  ],
  "attributes": [
    { "code": "ol_juno_barcode", "value": "JNATH088" },
    { "code": "haravan_variant_id-...", "value": "..." }
  ],
  "promotionInfo": { "name": "Happy Friday", "endDate": "...", ... }
}
```

---

## 4. Thách Thức & Giải Pháp

### A. RSC Streaming — Không Chứa Dữ Liệu Sản Phẩm

**Vấn đề**: Trang `juno.vn` dùng Next.js RSC. Khi fetch `/collections/ao` với header `RSC: 1`, server trả về stream RSC nhưng `"products": []` — mảng rỗng! Dữ liệu sản phẩm được load hoàn toàn client-side.

**Giải pháp**: Phân tích JS bundle `2608-d4a33d69b898f6f1.js` (chunk của collection page) → tìm ra API base `https://onelife-api.juno.vn/v1` và route pattern `/products/categories/{slug}/products`.

### B. Ảnh Swatch Màu Bị Lẫn Vào Ảnh Sản Phẩm

**Vấn đề**: Mảng `product.images` chứa lẫn URL ảnh 60×60 swatch màu dạng `https://img.onelife.vn/rs:fit:60:60:1/aHR0c...` (base64 encoded). Những ảnh này rất nhỏ và không phải ảnh showcase sản phẩm.

**Giải pháp**: Filter bỏ mọi URL chứa chuỗi `"img.onelife.vn/rs:fit:60:60"` trong hàm `parse_images()`.

### C. Size ID Không Được Giải Mã Cho Danh Mục Quần Áo

**Vấn đề**: Danh mục `dam-jumpsuit` (Đầm & Jumpsuit) không trả về đủ `variant_sizes` trong filters API. Giá trị như `"172"`, `"173"`, `"174"` không được resolve → hiển thị dưới dạng ID số.

**Giải pháp**: Thêm `GLOBAL_SIZE_FALLBACK` dict trong scraper:
```python
GLOBAL_SIZE_FALLBACK = {"171": "XL", "172": "L", "173": "S", "174": "M"}
```

Áp dụng fallback sau khi lookup trong category-specific size_map.

### D. Màu Variant — Lấy Từ Media, Không Phải Từ Attribute

**Vấn đề**: Variant `attributes` chỉ chứa `haravan_variant_id`, `ol_juno_barcode`, `ol_juno_variant_position` — không có color ID trực tiếp.

**Giải pháp**: Màu sắc của variant lấy từ `variant.media[i].title` — field "title" chính là tên màu (VD: "Nâu", "Kem", "Đen"). Media item với `itemType == "primary"` là ảnh chính của màu đó.

### E. Product Detail API — Không Tồn Tại

**Vấn đề**: Tìm endpoint để lấy thêm chi tiết sản phẩm (chất liệu, hướng dẫn) nhưng không thành công. Juno không expose product detail API.

**Giải pháp**: Field `descriptionJson` trong category API response chứa các sub-field như `highlights`, `introduction`, `ingredients` — nhưng thường empty cho sản phẩm thời trang. Dữ liệu chi tiết sản phẩm của Juno khá hạn chế về mô tả.

### F. Không Có Số Liệu Tổng Cho Category Cha

**Vấn đề**: Một số category cha (VD: "Túi cỡ nhỏ") có nhiều hơn `PAGE_LIMIT=40` sản phẩm. Cần pagination đúng cách.

**Giải pháp**: Dùng `pagination.last_page` để xác định khi nào hết trang, loop qua tất cả pages.

---

## 5. Danh Mục Đã Cào

| Danh mục cha | Danh mục con | Slug | Số SP |
|---|---|---|---|
| Giày | Giày xăng đan | `giay-xang-dan` | 36 |
| Giày | Giày cao gót | `giay-cao-got` | 40 |
| Giày | Giày búp bê | `giay-bup-be` | 22 |
| Giày | Giày Sneakers | `giay-sneakers` | 1 |
| Giày | Dép guốc | `dep-guoc` | 20 |
| Túi | Túi cỡ nhỏ | `tui-co-nho` | 60 |
| Túi | Túi cỡ trung | `tui-co-trung` | 3 |
| Túi | Túi cỡ lớn | `tui-co-lon` | 13 |
| Túi | Balo | `balo` | 9 |
| Túi | Ví - Clutch | `vi-clutch` | 16 |
| Phụ Kiện | Mắt kính | `mat-kinh` | 2 |
| Phụ Kiện | Nón | `non` | 1 |
| Phụ Kiện | Móc Khóa | `moc-khoa` | 9 |
| Phụ Kiện | Phụ kiện tóc | `phu-kien-toc` | 9 |
| Phụ Kiện | Vớ | `vo` | 7 |
| Quần Áo | Đầm & Jumpsuit | `dam-jumpsuit` | 10 |
| Quần Áo | Áo | `ao` | 21 |
| Quần Áo | Quần | `quan` | 12 |
| Quần Áo | Váy | `vay` | 18 |
| Quần Áo | Khoác | `khoac` | 9 |

**Tổng: 318 sản phẩm, 1.827 biến thể**

### Danh mục đã loại trừ theo yêu cầu:
- `juno-beauty` (Juno Beauty: Trang điểm, Chăm sóc da, mỹ phẩm) — **Loại bỏ**
- `set-qua-tang` (Set Quà Tặng) — **Loại bỏ** (không phải thời trang)

---

## 6. Kết Quả

- **File output**: `harvest/juno/output/juno_products_full.json`
- **Kích thước**: ~4.7 MB
- **Tổng sản phẩm**: 318 unique products
- **Tổng biến thể**: 1.827 variants
- **Hình ảnh**: Lưu URL tuyệt đối (không download về máy)
- **Chống trùng lặp**: Dùng `seen_ids: set` để dedup theo product ID

---

## 7. Scripts Tham Khảo

- **Scraper chính**: `experience/juno/juno_scraper.py`
- **Harvester chạy thực tế**: `harvest/juno/product_harvester.py`

---

## 8. Lưu Ý Quan Trọng Cho Agent Sau

1. **API base có thể thay đổi**: Subdomain `onelife-api.juno.vn` là private SaaS API. Nếu bị chặn, thử tìm lại trong JS bundle `**/chunks/2608-*.js`.
2. **Thumbnail color swatch**: Luôn filter bỏ URL có `img.onelife.vn/rs:fit:60:60` trước khi lưu ảnh.
3. **Size mapping cho quần áo**: Dùng global fallback `{171:XL, 172:L, 173:S, 174:M}` vì không phải category nào cũng return đủ size options trong filters API.
4. **Không có product detail API**: Toàn bộ thông tin cần thiết đã nằm trong category products response.
5. **Juno Beauty**: KHÔNG cào — là mỹ phẩm/trang điểm, không phải thời trang.
