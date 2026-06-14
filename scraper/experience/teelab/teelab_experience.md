# Teelab (teelab.vn) — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ phân tích kỹ thuật, các thách thức và giải pháp thu được trong quá trình thiết lập crawler tự động cho cửa hàng thời trang `teelab.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Hạ tầng & Platform**: Sử dụng hệ thống quản lý e-commerce **Sapo Web / Bizweb** (phát hiện qua cấu trúc CDN hình ảnh `bizweb.dktcdn.net` và các trường dữ liệu JSON đặc thù của Sapo).
- **Dữ liệu**: Khác với các website tự phát, Sapo Web cung cấp các endpoint JSON công khai tương tự như Shopify cho phép truy cập dữ liệu sạch mà không cần render trình duyệt.
- **Thách thức chính**:
  - Tách lọc và loại bỏ sản phẩm đồ lót (trunk underwear) và dép (sandals) nằm lẫn trong phân loại phụ kiện.
  - Phân tích cấu trúc mô tả sản phẩm (HTML description) để bóc tách thông tin chất liệu, form dáng, họa tiết (kỹ thuật).
  - Ánh xạ tùy chọn (options) màu sắc và kích thước của từng biến thể chính xác theo chuẩn dữ liệu dự án.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Public JSON Catalog Endpoint
Tương tự Shopify, Sapo Web hỗ trợ endpoint public cho phép lấy toàn bộ sản phẩm và thông tin chi tiết (bao gồm cả mô tả HTML và toàn bộ mảng biến thể) theo trang:
```http
GET https://teelab.vn/products.json?limit=250&page={page}
```

> [!TIP]
> Do Teelab chỉ có khoảng 120 sản phẩm hoạt động, toàn bộ catalog sản phẩm có thể được thu thập trọn vẹn chỉ trong 1 lần gọi duy nhất với `limit=250`. Điều này giúp giảm thiểu tối đa băng thông, tốc độ cào cực kỳ nhanh và loại bỏ hoàn toàn rủi ro bị chặn IP.

---

## 3. Thách Thức & Giải Pháp Kỹ Thuật

### A. Loại bỏ sản phẩm không hợp lệ (Exclusion Filters)
Teelab phân loại phụ kiện (`Phụ kiện (AC)`) chung cho cả balo, mũ, vớ, đồ lót (boxer/trunk underwear) và dép (sandals). Chúng ta áp dụng bộ lọc từ khóa thông minh:
- **Footwear/Dép**: Loại bỏ các sản phẩm chứa chữ `dép`, `sandals` (như sản phẩm `Teelab Alter Oversized Leather Monogram Sandals AC109`).
- **Underwear/Đồ lót**: Loại bỏ các sản phẩm chứa chữ `underwear`, `boxer`, `trunk` (như sản phẩm `Teelab Alter Combo 3 Trunk Underwear AC098`).
- **Exceptions**: Giữ lại các sản phẩm vớ/tất (ví dụ `Teelab Alter Oversized Cotton Iconic Logo Socks AC057`).

### B. Bóc tách thông tin kỹ thuật (Specs Parser)
Mô tả chi tiết sản phẩm của Teelab nằm trong thẻ `content` dạng HTML. Cấu trúc mô tả cực kỳ chuẩn chỉ:
```html
<p>Thông tin sản phẩm:&nbsp;</p>
<p>- Chất liệu: Cotton</p>
<p>- Form: Oversized&nbsp;</p>
<p>- Màu sắc: Đen<br />
<p>- Kỹ thuật: In</p>
```
Chúng ta sử dụng BeautifulSoup để làm sạch HTML và áp dụng biểu thức chính quy (Regex) để trích xuất:
- **Chất liệu**: Tìm từ khóa `Chất liệu|Chất liệu|Chất liệu` (Hỗ trợ nhiều biến thể Unicode dựng sẵn và tổ hợp).
- **Form dáng**: Tìm từ khóa `Form|Phom|Dáng|Kiểu dáng`.
- **Họa tiết**: Tìm từ khóa `Kỹ thuật|Kỹ thuật`.

### C. Chuẩn hóa hình ảnh CDN
Tất cả hình ảnh của Teelab được lưu trữ trên CDN Sapo `bizweb.dktcdn.net`. Chúng ta giữ nguyên liên kết tuyệt đối (ví dụ `https://bizweb.dktcdn.net/100/575/016/products/ss066-2026-06-04t110627-290.jpg`), thay thế các URL dạng tương đối bắt đầu bằng `//` thành `https://` để đảm bảo lưu trữ chuẩn xác.

---

## 4. Kết Quả & Tài Nguyên

- **Consolidated Scraper**: [teelab_scraper.py](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/experience/teelab/teelab_scraper.py)
- **Product Harvester**: [product_harvester.py](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/teelab/product_harvester.py)
- **File Discovery JSON**: [scraped_products.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/discovery/teelab/output/scraped_products.json)
- **File Harvest JSON**: [teelab_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/teelab/output/teelab_products_full.json)
- **Thống kê**:
  - Tổng số sản phẩm trên trang: 120
  - Loại bỏ do bộ lọc (2 Underwear, 1 Sandals): 3
  - Số lượng URL sản phẩm lưu trữ: 117
  - Số lượng biến thể map màu/size: 1.133
  - Toàn bộ hình ảnh lưu dưới dạng liên kết tuyệt đối CDN Sapo.
