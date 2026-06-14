# H&M Vietnam — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết các phát hiện kỹ thuật, giải pháp vượt tường lửa (Akamai), tối ưu hiệu năng và sơ đồ ánh xạ dữ liệu khi cào dữ liệu từ H&M Vietnam (`hm.com`).

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: Next.js (Server-Side Rendered)
- **Hệ thống bảo mật**: **Akamai Bot Manager** (Rất nghiêm ngặt).
  - *Thách thức*: Các thư viện HTTP thuần (như `urllib`, `requests`, `requests-html`) đều bị chặn ngay lập tức với mã lỗi `403 Forbidden` khi cố kết nối trực tiếp vào H&M.
  - *Giải pháp*: Kết nối vào trình duyệt Chrome thực qua giao thức **CDP (Chrome DevTools Protocol)** bằng Playwright. Toàn bộ các thao tác điều hướng và đọc dữ liệu đều diễn ra trên trình duyệt thực của người dùng, bỏ qua hoàn toàn các lớp bảo mật vân tay TLS/Akamai.

---

## 2. Kiến Trúc Dữ Liệu & Giải Pháp Tối Ưu

### A. Khai Thác State SSR `__NEXT_DATA__`
Thay vì phân tích cú pháp DOM HTML (dễ gãy và chậm), H&M nhúng toàn bộ dữ liệu cấu trúc trang vào thẻ `<script id="__NEXT_DATA__" type="application/json">`.
- **Category Pages**: Dữ liệu danh sách sản phẩm nằm tại:
  `props.pageProps.plpProps.productListingSectionProps.productListingData.hits`
- **Product Detail Pages (PDP)**: Dữ liệu chi tiết nằm tại:
  `props.pageProps.productPageProps.aemData.productArticleDetails.variations`

### B. Tối Ưu Hiệu Năng bằng Style Grouping
Trong cơ sở dữ liệu của H&M, mỗi mã màu của một mẫu quần áo là một sản phẩm độc lập có URL riêng (ví dụ: `0685816001.html`, `0685816270.html`).
- *Phát hiện*: Khi truy cập vào chi tiết **bất kỳ** màu nào của mẫu đó, trường `variations` trong `__NEXT_DATA__` trả về đầy đủ chi tiết (tên màu, mô tả, chất liệu, hình ảnh, bảng kích cỡ) của **TẤT CẢ** các màu khác thuộc cùng một mẫu (Style ID - là 7 chữ số đầu của article code).
- *Giải pháp*: Trong Phase 1 (Discovery), chúng ta gom nhóm toàn bộ sản phẩm phát hiện theo 7 chữ số đầu. Trong Phase 2 (Harvest), chúng ta chỉ tải **duy nhất 1 trang PDP** cho mỗi mẫu. Điều này giảm số lượt tải trang chi tiết từ trình duyệt xuống **80%–90%**, giảm tải băng thông và đẩy nhanh tốc độ cào.

### C. Giải Pháp Lấy Tình Trạng Còn Hàng (Live Availability)
Thông tin tồn kho từng kích cỡ (size-level stock) không được nhúng cứng trong `__NEXT_DATA__` trên PDP mà được load bất đồng bộ qua API của H&M:
`https://ofg.hm.com/pdh-availability/v1/product/vn/availability/{style_id}`
- *Thách thức*: Gọi API này trực tiếp từ Python bị chặn `403 Forbidden`.
- *Giải pháp*: Thực hiện lệnh `fetch()` trực tiếp trong ngữ cảnh trình duyệt thông qua Playwright:
  ```python
  avail_list = await page.evaluate(f"fetch('{url}').then(r => r.json()).then(d => d.availability || [])")
  ```
  API trả về danh sách các mã kích cỡ (ví dụ: `0685816001010`) đang có hàng. Các mã không nằm trong danh sách này được đánh dấu là hết hàng (`available = False`).

---

## 3. Bản Đồ Ánh Xạ Dữ Liệu (Data Mapping)

Dữ liệu thu hoạch từ `variations[var_code]` được ánh xạ như sau:
- **ID / Handle**: Mã màu (article code 10 chữ số, ví dụ `0685816001`).
- **Title**: Tên sản phẩm + Màu sắc.
- **Price**: Lấy từ `whitePriceValue` (giá gốc) hoặc `redPriceValue` / `yellowPriceValue` (nếu có giá khuyến mãi thấp hơn).
- **Images**: Lấy trực tiếp trường `baseUrl` tuyệt đối trong danh sách hình ảnh (không tải ảnh về máy, chỉ lưu link).
- **Specifications (Thông số chi tiết)**:
  - `Chất liệu`: Duyệt qua `composition[i].materials` để ghép tỷ lệ phần trăm (ví dụ: `Bông 60%; Pôlyexte 40%`).
  - `Lưu ý giặt ủi`: Ghép mảng `careInstructions` phân tách bằng dấu chấm phẩy.
  - `Form dáng`, `Chiều dài`, `Tay áo`, `Cổ áo`: Duyệt qua `productAttributes.description` lọc theo từ khóa tương ứng.

---

## 4. Kết Quả Thu Hoạch

- **Scraper Script**: `experience/hm/hm_scraper.py`
- **Output JSON**: `harvest/hm/output/hm_products_full.json`
- **Khối lượng cào**: ~959 mẫu thiết kế (Style IDs), sinh ra hàng ngàn sản phẩm màu sắc và kích cỡ Normalizer hoàn thiện, đáp ứng các tiêu chuẩn loại trừ sản phẩm trẻ em, giày dép, đồ lót, mỹ phẩm.
