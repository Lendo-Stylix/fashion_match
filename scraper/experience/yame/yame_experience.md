# yame.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép lại toàn bộ kinh nghiệm thực tế, giải pháp kỹ thuật và bài học rút ra trong quá trình cào dữ liệu tự động từ website `yame.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Shopify** e-commerce backend (gần đây đã chuyển từ hệ thống tự phát sang Shopify).
- **Dữ liệu**: Hỗ trợ endpoint public `/products.json?limit=250&page={page}` chứa đầy đủ dữ liệu chi tiết của sản phẩm và biến thể (variants), cho phép lấy trực tiếp thay vì cào HTML hoặc tương tác trình duyệt.
- **Thách thức chính**:
  - **Lọc Đồ Lót / Brand False Positive**: Yame.vn có nhiều dòng sản phẩm mang thương hiệu "Non Branded". Substring check cho keyword đồ lót `"bra"` đã bắt nhầm `"Non Branded"`, làm bỏ sót hầu hết sản phẩm của hãng.
  - **Sắp Xếp Biến Thể Đơn Sắc**: Yame.vn không tạo các biến thể màu sắc trong cùng một Product ID. Thay vào đó, mỗi màu sắc được đăng dưới dạng một Product ID riêng biệt và tên màu nằm trực tiếp trong Product Title (Ví dụ: "Màu Trắng 11", "Màu Đen 99").
  - **Trích Xuất Thông Số Sắc Sảo**: Thông tin chất liệu, phom dáng nằm rải rác trong `body_html` dưới 2 dạng: Cấu trúc thẻ HTML `<li><strong>Chất liệu:</strong>...</li>` và dạng văn bản đánh số `3. Chất liệu:...`.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. API Lấy Danh Sách & Chi Tiết Sản Phẩm
Shopify hỗ trợ lấy danh sách toàn bộ sản phẩm của store thông qua:
```
GET https://yame.vn/products.json?limit=250&page={page}
```
Mỗi trang chứa tối đa 250 sản phẩm với đầy đủ thông tin:
- Tiêu đề (`title`), handle, loại sản phẩm (`product_type`), tags.
- Mô tả định dạng HTML (`body_html`).
- Options (Size / Kích Cỡ).
- Biến thể (`variants`): `sku`, `price`, `compare_at_price`, `available` và các trường `option1` (Size).
- Hình ảnh (`images`): URL tuyệt đối của CDN Shopify.

---

## 3. Thách Thức & Giải Giải Pháp Kỹ Thuật

### A. Sửa Lỗi Nhận Diện Nhầm Đồ Lót (False Positive "bra" inside "Non Branded")
- **Vấn đề**: Từ khóa loại trừ `"bra"` (áo ngực) vô tình khớp với `"Non Branded"` (nhãn hiệu của Yame).
- **Giải pháp**: Thay vì dùng substring check đơn giản, sử dụng regex với ranh giới từ `\bbra\b` hoặc `\bkids\b` để đảm bảo chỉ loại bỏ khi là từ đứng độc lập.
```python
en_under_kws = [r'\bbra\b', r'\bunderwear\b', r'\binnerwear\b']
if any(re.search(kw, title_l) for kw in en_under_kws):
    return True
```

### B. Map Kích Thước & Màu Sắc Từ Tiêu Đề
- **Vấn đề**: Do màu sắc nằm trong tiêu đề và có thể xuất hiện nhiều lần (ví dụ: "Phối Màu... Màu Xanh Lá"), việc bắt regex đơn giản sẽ bị sai lệch.
- **Giải pháp**:
  1. Tách chuỗi theo từ khóa ` Màu ` cuối cùng trong tiêu đề (`re.split` theo ` Màu ` và lấy phần tử cuối).
  2. Cắt bỏ các phần đuôi mô tả phom dáng (như `Dáng Rộng`, `Phom Boxy`, `Form Hộp`, `F4`, `F5`) để lấy được tên màu sạch (ví dụ: `Xanh Dương Nhạt`, `Trắng 11`, `Đen 99`).
  3. Đưa tên màu này vào `option1` và đưa kích cỡ (Size) vào `option2` trong danh sách variants để chuẩn hóa theo cấu trúc của Aristino.

### C. Trích Xuất Thông Số Sản Phẩm (Specifications)
- **Vấn đề**: Định dạng mô tả của Yame rất đa dạng (HTML list vs plain text).
- **Giải pháp**:
  1. Sử dụng regex để tìm cấu trúc thẻ đặc thù: `<li>\s*<strong>Chất liệu:</strong>\s*(.*?)</li>`
  2. Nếu không tìm thấy, fallback về quét dòng văn bản thô theo cụm từ khóa `(?:Chất liệu|Thành phần):\s*(.*)` để lấy thông số thành phần vải (ví dụ: 94% Cotton, 6% Spandex).
  3. Trích xuất phom dáng trực tiếp từ tiêu đề thông qua chỉ thị `Dáng [^-\(\)\"]+` (ví dụ: `Dáng Hộp F5`, `Dáng Vừa Vặn F3`).

---

## 4. Kết Quả Thu Thập

- **Đường dẫn file lưu**: `harvest/yame/output/yame_products_full.json`
- **Số lượng**:
  - Tổng số sản phẩm thời trang độc nhất thu thập: **1.402 sản phẩm**.
  - Các biến thể chi tiết (size/màu/giá/ảnh biến thể): **5.393 variants**.
- **Hình ảnh**: Lưu URL tuyệt đối của CDN Shopify, không tải ảnh về đĩa để tránh tốn tài nguyên.

---

## 5. Scripts Tham Khảo

- **Script Discovery**: `experience/yame/yame_scraper.py`
- **Script Harvest**: `experience/yame/product_harvester.py`
