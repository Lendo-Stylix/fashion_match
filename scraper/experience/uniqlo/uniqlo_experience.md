# Uniqlo.com — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `uniqlo.com` (khu vực Việt Nam).

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: Hệ thống storefront tùy chỉnh của **Fast Retailing**, hoạt động như một Single Page Application (SPA) gọi REST API nội bộ phía backend.
- **Dữ liệu**: Hỗ trợ bộ API phiên bản v5 khá sạch và đầy đủ thông tin:
  - **Taxonomy API**: `https://www.uniqlo.com/vn/api/commerce/v5/vi/products/taxonomies?withSubcategories=true`
  - **Listing API**: `https://www.uniqlo.com/vn/api/commerce/v5/vi/products?path={gender_id},{class_id},{category_id}&genderId={gender_id}&offset={offset}&limit={limit}&imageRatio=3x4&httpFailure=true`
  - **Detail API**: `https://www.uniqlo.com/vn/api/commerce/v5/vi/products/{productId}?httpFailure=true`
- **Hình ảnh**: Lưu trữ trên CDN của Uniqlo dưới tên miền `https://image.uniqlo.com/`.

---

## 2. Thách Thức & Giải Giải Pháp Kỹ Thuật

### A. Lỗi 400 Bad Request (Missing Client ID)
- **Vấn đề**: Khi thực hiện các request bằng Python `urllib` thông thường lên API, server trả về JSON lỗi `{"status": "nok", "error": {"message": "invalid or missing client id"}}`.
- **Giải pháp**: Phân tích request headers từ Chrome DevTools và bổ sung hai header bắt buộc:
  - `x-fr-clientid: uq.vn.web-spa`
  - `x-fr-client-version: 3.2506.1`

### B. Loại Trừ Các Sản Phẩm Trẻ Em, Giày Dép, Đồ Lót
- **Vấn đề**: Uniqlo bán rất nhiều sản phẩm em bé (Kids & Baby), giày dép (Shoes/Sandals), và đồ lót nam nữ (Underwear/Bra/Innerwear). Cần phải loại trừ các loại này.
- **Giải pháp**:
  - **Loại trừ từ gốc**: Trong phase Discovery, khi duyệt cây danh mục (Taxonomy), lọc bỏ hoàn toàn các danh mục có parent hoặc chính danh mục đó chứa từ khóa `underwear`, `bra`, `shoes`, `innerwear` (trừ tất/vớ `socks`).
  - **Loại trừ ở mức sản phẩm**: Sử dụng bộ lọc từ khóa (`EXCLUDE_KEYWORDS`) để kiểm tra tiêu đề sản phẩm để loại bỏ các trường hợp đặc biệt khác (ví dụ: sản phẩm chứa từ khóa "trẻ em", "bé trai", "bé gái").

### C. Đồng Bộ Hóa Dữ Liệu Khác Biệt Giá và Khuyến Mãi
- **Vấn đề**: Cấu trúc giá của Uniqlo lưu trong object `prices` chứa `base` và `promo`. Một số sản phẩm giảm giá sẽ có giá trị trong `promo` khác `None`.
- **Giải pháp**: Ánh xạ động:
  - Nếu `promo` có giá trị: `price = promo['value']`, `compare_at_price = base['value']`.
  - Nếu `promo` bằng `None`: `price = base['value']`, `compare_at_price = None`.

### D. Tối Ưu Tốc Độ Thu Hoạch (ThreadPoolExecutor)
- **Vấn đề**: Số lượng sản phẩm hợp lệ lên tới hơn 660 sản phẩm. Nếu cào tuần tự sẽ mất khoảng 22-25 phút và có nguy cơ bị timeout.
- **Giải pháp**: Sử dụng `ThreadPoolExecutor` với `max_workers = 4` kết hợp delay `0.2s` sau mỗi batch để chạy song song. Thời gian cào thực tế giảm xuống chỉ còn chưa đầy **1.5 phút** mà không hề bị rate limit hoặc block IP.

---

## 3. Cấu Trúc File Kết Quả

- **Đường dẫn**: `harvest/uniqlo/output/uniqlo_products_full.json`
- **Thông tin thu hoạch**:
  - **Chi tiết sản phẩm**: Đầy đủ Chất liệu (`composition`), Form dáng (`Form dáng`), Hướng dẫn giặt ủi (`washingInformation`), Nguồn gốc xuất xứ (`countriesOfOrigin`).
  - **Variants**: Ánh xạ đầy đủ `sku` dạng `484508-00-003-000` (mã màu và mã size đầy đủ), map màu swatches và size tương ứng.
  - **Hình ảnh**: Lưu các liên kết ảnh CDN tuyệt đối định dạng `3x4` của Uniqlo.
