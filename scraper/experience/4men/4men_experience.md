# 4MEN.com.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết kinh nghiệm thực chiến, các đặc tính kỹ thuật, thách thức và giải pháp thu thập được trong quá trình tự động hóa cào dữ liệu từ hệ thống thời trang nam `4men.com.vn`.

---

## 1. Nhận Diện Nền Tảng & Đặc Điểm Hạ Tầng

- **Platform**: Nền tảng tự phát triển (Custom PHP/MySQL Platform) với thẻ generator là `"4MEN"`.
- **Dữ liệu**: Không hỗ trợ endpoint JSON công khai (như Shopify hay Haravan). Tuy nhiên, trang web tải rất nhanh và trả về cấu trúc HTML tĩnh đầy đủ thông tin, phù hợp tuyệt đối cho phương pháp cào trực tiếp qua HTTP requests (`urllib` + `BeautifulSoup` / `aiohttp` + `bs4`) mà không cần sử dụng các thư viện render nặng nề như Playwright.

---

## 2. Kiến Trúc Dữ Liệu & Giải Pháp Trích Xuất

### 2.1. Phân Trang & Khám Phá URL (Discovery Phase)
- **Cấu trúc phân trang**:
  - Trang 1: `https://4men.com.vn/{category_slug}.html`
  - Trang 2+: `https://4men.com.vn/{category_slug}/trang-{page}.html`
  - Nếu số lượng sản phẩm trên trang ít hơn 24 hoặc gặp lỗi 404, chúng ta có thể dừng phân trang cho danh mục đó.
- **Trích xuất các phiên bản màu sắc**:
  - Mỗi màu sắc của sản phẩm được lưu thành một trang riêng biệt trên hệ thống (ví dụ: Áo Sơ Mi Trơn Form Slimfit SM205 màu Trắng, Đen, Xanh Biển có 3 URL khác nhau).
  - Ngay từ trang danh sách, các card sản phẩm `.pro` có chứa sẵn danh sách tất cả các biến thể màu sắc này trong phần `.item-thumbs .pc-wrap a` với đầy đủ thuộc tính như `href`, `title`, `price`, `s` (danh sách size), `data-src` (ảnh).
  - Giải pháp: Trích xuất toàn bộ các liên kết màu sắc từ `.pc-wrap a` làm URL đích để harvest. Nếu sản phẩm chỉ có một màu (không có `.item-thumbs`), chúng ta sẽ lấy URL gốc tại thẻ `h4 a`.

### 2.2. Thu Hoạch Chi Tiết Sản Phẩm (Harvest Phase)
- **Dữ liệu GTM (Google Tag Manager)**:
  - Hệ thống nhúng thông tin sản phẩm chi tiết trong thẻ `<script>` dưới dạng biến Google Tag Manager `dataLayer.push` với sự kiện `'event': 'productDetail'`.
  - Cấu trúc này chứa các thông tin chuẩn hóa: `name`, `id` (mã ID biến thể), `price`, `brand`, `category`, và đặc biệt là `SKU` chuẩn của hệ thống (ví dụ: `'SKU': '2603271745304'`).
  - Giải pháp: Dùng biểu thức chính quy (Regex) quét thẻ script để giải mã trực tiếp dữ liệu này, đạt độ tin cậy 100% không phụ thuộc CSS selectors.
- **Thuộc Tính Chi Tiết (Specifications)**:
  - Các thông số quan trọng như chất liệu cụ thể (ví dụ: Bamboo, Poly, Spandex với tỉ lệ % cụ thể), phom dáng (Slimfit, Regular), mã sản phẩm được lưu ở dạng văn bản có gạch đầu dòng trong class `.accordion-content` hoặc `.details-box.html-content`.
  - Giải pháp: Tách dòng và viết parser biểu thức chính quy theo mẫu `^[-*•]\s*([^:]+):\s*(.*)` để bóc tách thông tin lưu vào mục `specifications`.
- **Kích Thước (Sizes)**:
  - Trích xuất từ các option của thẻ select `#sizeSelect`.
- **Hình Ảnh (Images)**:
  - Thu thập tất cả các link ảnh chất lượng cao từ slider `.prod-slider.sync1 img` (có chứa cụm `slide-products`). Chỉ lưu trữ URL tuyệt đối từ CDN của 4MEN (`https://4men.com.vn/images/...`), tuyệt đối không tải ảnh về đĩa cứng.

---

## 3. Thách Thức & Các Bộ Lọc Loại Trừ

- **Lọc danh mục không phù hợp**:
  - Loại trừ sản phẩm trẻ em, đồ lót, giày dép, mỹ phẩm theo cấu hình bằng cách bỏ qua các danh mục `/quan-lot.html`, `/giày-dep-nam.html` và viết hàm kiểm tra từ khóa loại trừ `EXCLUDE_KEYWORDS` trên tiêu đề và URL.
  - Ngoại trừ: giữ lại tất/vớ (`vo-nam.html`) và đồ bơi (nếu có).
- **Unicode Terminal trên Windows**:
  - Console trên Windows có thể gặp lỗi crash `UnicodeEncodeError` khi in các chữ tiếng Việt có dấu. Khắc phục bằng cách cấu hình ghi đè encoding cho console ở đầu các script:
    ```python
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    ```
- **Giới hạn băng thông & HTTP 429**:
  - Gặp phản hồi 429 (Too Many Requests) khi gọi đồng thời quá nhiều request. Khắc phục bằng cách giới hạn concurrency `asyncio.Semaphore(5)` và thêm delay nhỏ `0.3s` giữa các lượt call.

---

## 4. Kết Quả

- **Discovery Output**: `discovery/4men/output/scraped_products.json` chứa 889 URL duy nhất chia theo danh mục.
- **Harvest Output**: `harvest/4men/output/4men_products_full.json` chứa bộ dữ liệu chi tiết của 4MEN tiệm cận chuẩn Aristino.
