# Degrey.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `degrey.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Haravan** e-commerce backend (sử dụng cấu trúc dữ liệu và API tương tự Shopify).
- **Dữ liệu**: Hỗ trợ endpoint public `/collections/all/products.json?limit=250&page={page}` trả về danh sách đầy đủ sản phẩm, ảnh CDN, và biến thể (variants) dạng JSON mà không cần tải trang HTML chi tiết.
- **Thách thức chính**:
  - Tách màu sắc và kích thước chính xác từ cấu trúc sản phẩm đơn giản của Haravan (chỉ chứa một tùy chọn `SIZE` duy nhất cho quần áo, trong khi màu sắc phân chia thành các sản phẩm riêng biệt).
  - Trích xuất thông tin đặc tính sản phẩm (Chất liệu, Form dáng, Kiểu dáng, Họa tiết) từ bảng dữ liệu HTML nhúng trong `body_html`.
  - Tuân thủ các quy tắc loại trừ (không cào đồ lót, trẻ em, giày dép, mỹ phẩm) và yêu cầu giữ nguyên liên kết ảnh CDN không tải cục bộ.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Endpoint Danh Sách Sản Phẩm

Haravan hỗ trợ lấy toàn bộ danh sách sản phẩm của bộ sưu tập `all` dạng JSON:
```
GET https://degrey.vn/collections/all/products.json?limit=250&page={page}
```

- **Đặc tính**: Danh sách trả về đầy đủ các thông tin của biến thể như `option1` (chứa kích thước S/M/L/XL), giá tiền (`price`, `compare_at_price`), ảnh biến thể (`image_id`), và số lượng tồn kho (`inventory_quantity`). Vì vậy, toàn bộ quá trình thu thập thông tin chỉ mất một lượt tải API duy nhất, không cần gửi yêu cầu đến từng trang chi tiết (PDP), tối ưu hóa băng thông và thời gian chạy.

---

## 3. Thách Thức Kỹ Thuật & Giải Pháp

### A. Trích Xuất Màu Sắc Thông Minh (Color Extraction)
- **Vấn đề**: Các sản phẩm khác màu (ví dụ: *Áo thun Degrey TC Oversize màu NAVY* và *Áo thun Degrey TC Oversize màu TRẮNG*) được đăng tải dưới dạng các ID sản phẩm độc lập. Thuộc tính biến thể chỉ chứa kích cỡ (S/M/L) mà không chỉ định rõ màu sắc.
- **Giải pháp**: Thiết lập bộ lọc đa tầng để phân giải màu sắc:
  1. Duyệt danh sách các cụm từ màu sắc đã biết (ví dụ: `WAX XÁM`, `TRẮNG SỌC ĐEN`, `ĐEN VÀNG`, `NAVY`, `TRẮNG`, `ĐEN`) có sắp xếp theo chiều dài giảm dần (longest-match first) để so khớp chính xác với tiêu đề sản phẩm.
  2. Sử dụng Regex tìm mẫu `màu <color>` và loại bỏ các từ dừng thừa (như "thêu", "logo", "oversize").
  3. Trích xuất từ trường `Màu sắc` trong bảng thông số thuộc tính mô tả.
  4. Trích xuất từ hậu tố SKU (ví dụ: `TANKNEWLOGONAVY` -> `NAVY`).
  5. Đưa màu sắc thu được về thuộc tính chuẩn `option1` của biến thể, và chuyển kích thước sang `option2`.

### B. Trích Xuất Thông Số Sản Phẩm Tự Động (Spec Parsing)
- **Vấn đề**: Các thuộc tính chi tiết không nằm ở trường metadata riêng biệt mà được trình bày dạng bảng `<table>` bên trong mô tả sản phẩm `body_html`.
- **Giải pháp**: Sử dụng thư viện `BeautifulSoup` để tìm kiếm thẻ `<table>` trong tài liệu. Duyệt qua từng hàng `<tr>` và kiểm tra các ô cột `<td>` chứa các từ khóa đặc trưng (như `Chất liệu`, `Kiểu dáng`, `Form`, `Họa tiết`, `Màu sắc`, `Sản xuất`). Sau đó ánh xạ thành một đối tượng thông số chi tiết chuẩn hóa. Khi không có bảng, áp dụng Regex fallback để quét qua nội dung văn bản thuần của mô tả.

### C. Lọc Các Danh Mục Ngoại Lệ
- **Vấn đề**: Cần lọc bỏ các mặt hàng thuộc nhóm đồ lót, giày dép, mỹ phẩm, trẻ em.
- **Giải pháp**:
  - Áp dụng bộ lọc từ khóa phủ định trên tiêu đề, loại sản phẩm và nhãn.
  - Bộ lọc đã phát hiện và loại trừ thành công mặt hàng `Áo thun Degrey Sport Bra màu GREEN - SPOBRAGREEN` do có từ khóa `"bra"` thuộc nhóm đồ lót (underwear), đảm bảo dữ liệu thu được hoàn toàn sạch sẽ.

---

## 4. Kết Quả Thu Thập

- **File Discovery**: `discovery/degrey/output/scraped_products.json`
- **File Harvest**: `harvest/degrey/output/degrey_products_full.json`
- **Hình ảnh**: Lưu trữ URL tuyệt đối của CDN Haravan (`https://cdn.hstatic.net/...`).
- **Thống kê**:
  - Tổng số sản phẩm độc nhất thu thập được: **49**
  - Đã lọc bỏ: **1** (Sport Bra - đồ lót)
  - Phân loại ngành hàng:
    - Áo Thun: 26 sản phẩm
    - Quần Dài: 6 sản phẩm
    - Áo Sơ Mi: 1 sản phẩm
    - Phụ Kiện: 1 sản phẩm
    - Áo Polo: 2 sản phẩm
    - Quần Shorts: 2 sản phẩm
    - Áo Khoác: 5 sản phẩm
    - Balo & Túi: 3 sản phẩm
    - Áo Hoodie & Nỉ & Len: 3 sản phẩm
