# 5S Fashion (5sfashion.vn) — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết toàn bộ phân tích kỹ thuật, các thách thức và giải pháp thu được trong quá trình thiết lập crawler cho hệ thống `5sfashion.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Hạ tầng & Platform**: Sử dụng **Laravel Framework** (phát hiện qua các cookie `laravel_session`, `XSRF-TOKEN` và header `X-Powered-By: PHP/8.2.13`). Frontend sử dụng Bootstrap 5, Swiper, jQuery và Vanilla LazyLoad.
- **Dữ liệu**: Hỗ trợ endpoint AJAX động qua `/filter`.
- **Thách thức chính**:
  - Trang PDP sử dụng cấu trúc inputs ẩn cho biến thể nhưng bị thiếu mất thuộc tính `data-sku` ở trang chi tiết.
  - Phân loại danh mục con phong phú, cần lọc bỏ đồ trẻ em, đồ lót, giày dép và mỹ phẩm theo yêu cầu.
  - Tối ưu hóa kích thước hình ảnh tải từ CDN.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Discovery: AJAX Filter Endpoint
Khi nhấn "Xem thêm" hoặc thay đổi các bộ lọc ở trang danh mục, frontend sẽ gọi AJAX đến endpoint:
```http
GET https://5sfashion.vn/filter?category={category_id}&page={page}
```
Header yêu cầu:
- `X-Requested-With: XMLHttpRequest`
- `Accept: application/json, text/javascript, */*; q=0.01`

Response trả về là JSON chứa 3 keys:
1. `content`: Chứa mã HTML của danh sách sản phẩm.
2. `filter`: Chứa mã HTML của thanh bộ lọc.
3. `total`: Tổng số sản phẩm thuộc danh mục đó.

**Giải pháp Discovery**:
Tận dụng endpoint này để lấy toàn bộ 1070 sản phẩm của 50 danh mục một cách nhanh chóng mà không cần render trình duyệt.

### 2.2. variant-to-SKU Mapping
Trên trang danh mục (trong trường `content` của API filter), mỗi card sản phẩm chứa các input ẩn chứa đầy đủ thuộc tính biến thể:
```html
<input type="hidden" data-sku="Y0ATS25045DEN02K2" data-id="13455" class="776-26-1" data-percent="30" data-price="229.000đ" data-price-promotion="159.000đ" />
```
Trong đó:
- `data-sku`: Mã SKU đầy đủ của biến thể (có mã màu, mã size).
- `data-id`: ID duy nhất của biến thể.
- `class`: Liên kết giữa `{group_id}-{color_id}-{size_id}`.

Vì trên trang chi tiết sản phẩm (PDP), thuộc tính `data-sku` trên các input ẩn này bị bỏ trống, chúng ta xây dựng một map toàn cục `variant_sku_map` (`variant_id -> SKU`) ngay từ bước Discovery để tra cứu lại khi Harvest.

---

## 3. Thách Thức & Giải Pháp Harvest PDP

### A. Trích xuất màu sắc và kích thước (Options)
Mỗi tùy chọn màu sắc trong `.variant-color li` chứa:
- `data-color`: Tên màu (ví dụ: `Hồng`, `Đen`).
- `data-product-color-id`: Tiền tố màu (ví dụ: `776-46`).
- Thẻ `img` con chứa ảnh mẫu của màu đó.

Mỗi kích thước trong `.variant-size li` chứa:
- `data-size`: Tên size (ví dụ: `S`, `M`, `L`).
- `data-size-id`: ID của size (ví dụ: `1`, `2`).

Biến thể được ghép nối bằng cách tìm input ẩn có `class="{color_prefix}-{size_id}"` để lấy giá bán, giá cũ, tồn kho và ID biến thể.

### B. Trích xuất hình ảnh chất lượng cao
Ảnh trong slider có tiền tố kích thước trong CDN URL của cdneverest.net như `/fast/69x0/` (thumbnail) hoặc `/fast/180x0/`.
Chúng ta chuẩn hóa các đường dẫn này bằng cách thay thế kích thước thành `/fast/1325x0/` để lấy ảnh độ phân giải cao nhất cho sản phẩm.

### C. Heuristic Specs Parser
Thông tin mô tả cấu trúc dưới dạng văn bản tự do trong `.content-desc`. Chúng ta sử dụng parser thông minh dựa trên keyword để trích xuất:
- **Chất liệu**: Tìm các dòng chứa tỉ lệ `%` hoặc các sợi vải (cotton, spandex, polyester...).
- **Form dáng**: Tìm dòng chứa từ khóa `phom dáng`, `form dáng`, `slimfit`, `regular`...
- **Họa tiết**: Tìm dòng chứa `in logo`, `trơn basic`, `thiết kế`...

---

## 4. Kết Quả

- **File Discovery**: `discovery/5sfashion/output/scraped_products.json`
- **File Harvest**: `harvest/5sfashion/output/5sfashion_products_full.json`
- **Thống kê**:
  - Số lượng URL sản phẩm: 1.070
  - Số lượng biến thể map SKU: 17.358
  - Toàn bộ hình ảnh được lưu dưới dạng URL tuyệt đối CDN cdneverest.net.
