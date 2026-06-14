# dirtycoins.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép lại toàn bộ kinh nghiệm thực tế, giải pháp kỹ thuật và bài học rút ra trong quá trình cào dữ liệu tự động từ website `dirtycoins.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Haravan** e-commerce backend (có cấu trúc tương tự Shopify).
- **Dữ liệu**: Hỗ trợ endpoint public `/collections/all/products.json?limit=50&page={page}` chứa đầy đủ dữ liệu chi tiết của sản phẩm và biến thể (variants), cho phép lấy trực tiếp thay vì cào HTML hoặc tương tác trình duyệt.
- **Thách thức chính**:
  - Xác định đúng vị trí option màu sắc/kích thước từ danh sách options động (vì Haravan sử dụng `option1`, `option2`, `option3` với thứ tự thay đổi).
  - Lọc bỏ các sản phẩm đồ lót (Boxer), giày dép (Slides), trẻ em (Kids) và mỹ phẩm nhưng giữ lại các ngoại lệ như tất/vớ (Socks) và baby tee (áo thun ôm dáng nữ).

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. API Lấy Danh Sách & Chi Tiết Sản Phẩm
Haravan hỗ trợ lấy danh sách sản phẩm theo trang:
```
GET https://dirtycoins.vn/collections/all/products.json?limit=50&page={page}
```
Mỗi trang chứa tối đa 50 sản phẩm với đầy đủ thông tin:
- Tiêu đề (`title`), handle, loại sản phẩm (`product_type`), tags.
- Mô tả định dạng HTML (`body_html`).
- Options (tên option và danh sách giá trị như Màu sắc, Kích thước).
- Biến thể (`variants`): `sku`, `price`, `compare_at_price`, `available`, `inventory_quantity`, và các trường `option1`, `option2`, `option3`.
- Hình ảnh (`images`): URL tuyệt đối của CDN Haravan (`https://cdn.hstatic.net/...`).

---

## 3. Thách Thức & Giải Pháp Kỹ Thuật

### A. Trích Xuất & Ánh Xạ Biến Thể Động
- **Vấn đề**: Các sản phẩm khác nhau có thứ tự option khác nhau. Ví dụ, một sản phẩm có option 1 là "Đơn vị tính", option 2 là "Màu sắc", option 3 là "Kích thước". Sản phẩm khác lại chỉ có option 1 là "Kích thước".
- **Giải pháp**: 
  1. Duyệt qua mảng `options` của sản phẩm để tìm vị trí (index) chứa từ khóa "màu" hoặc "color" làm `color_idx`, và từ khóa "kích" hoặc "size" làm `size_idx`.
  2. Khi parse từng variant, lấy giá trị option tương ứng từ mảng `[option1, option2, option3]` thông qua chỉ số đã tìm thấy để map vào chuẩn `option1` (Màu sắc) và `option2` (Kích thước) trong file kết quả.

### B. Trích Xuất Thông Số Sản Phẩm (Specifications)
- **Vấn đề**: Haravan không có API chứa thông số kỹ thuật rời. Toàn bộ thông số nằm trong trường `body_html` dưới dạng văn bản thô trộn lẫn thẻ HTML.
- **Giải pháp**:
  1. Dùng regex để loại bỏ thẻ HTML, chuẩn hóa khoảng trắng và chuyển đổi các thẻ ngắt dòng `<br>`, `<p>` thành `\n`.
  2. Quét văn bản theo dòng và sử dụng các regex:
     - Chất liệu: `(?:Chất liệu|Thành phần):\s*([^••\n\-]+)`
     - Form dáng: `(?:Form|Dáng|Kiểu dáng):\s*([^••\n\-]+)`
     - Công nghệ in: `(?:Hình in|Công nghệ in|Artwork):\s*([^••\n\-]+)`
  3. Trích xuất thành công các thông số chi tiết như `cotton`, `polyester`, `Regular` cho từng sản phẩm.

### C. Bộ Lọc Loại Trừ Đặc Thù
- **Vấn đề**: Yêu cầu loại bỏ đồ trẻ em (Kids) nhưng giữ lại áo dáng ôm "Baby Tee" (vốn chứa từ khóa "baby" dễ bị nhận diện nhầm thành đồ trẻ em).
- **Giải pháp**: 
  - Trong bộ lọc `is_kid`, thêm ngoại lệ bỏ qua kiểm tra từ khóa "baby" nếu tiêu đề chứa "baby tee" hoặc "baby-tee", hoặc màu sắc chứa "baby pink", "baby blue".
  - Loại bỏ các sản phẩm có `product_type` là `SLIDES` (dép) và `INNERWEAR` (đồ lót), nhưng giữ lại `SOCKS` (tất/vớ) theo yêu cầu đặc thù.

---

## 4. Kết Quả Thu Thập

- **Đường dẫn file lưu**: `harvest/dirtycoins/output/dirtycoins_products_full.json`
- **Số lượng**:
  - Tổng số sản phẩm thời trang độc nhất thu thập: **225 sản phẩm**.
  - Các biến thể chi tiết (size/màu/kho/giá/ảnh biến thể): **Đầy đủ và chính xác**.
- **Hình ảnh**: Giữ nguyên URL tuyệt đối của CDN Haravan (`https://cdn.hstatic.net/`), không tải ảnh về đĩa để tránh tốn tài nguyên.

---

## 5. Scripts Tham Khảo

- **Script Discovery**: `experience/dirtycoins/dirtycoins_scraper.py`
- **Script Harvest**: `experience/dirtycoins/product_harvester.py`
