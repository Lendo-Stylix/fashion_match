# Levents.asia — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép lại toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp khi thu thập dữ liệu tự động từ `levents.asia`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Storecake** (Một giải pháp CMS thương mại điện tử do Pancake.vn phát triển).
- **Dữ liệu**: Storecake lưu cấu hình giao diện và API tập trung. Trang web tải sản phẩm không qua render HTML tĩnh mà gọi API backend trực tiếp thông qua phương thức POST.
- **Thách thức chính**:
  - Không hỗ trợ endpoint `.json` dạng tĩnh (như Shopify/Haravan).
  - Cần lấy chính xác các mã UUID như `site_id`, `category_id` và cấu trúc payload POST để truy vấn dữ liệu từ API.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Endpoint Danh Sách & Chi Tiết Sản Phẩm

Storecake sử dụng một endpoint chung cho việc tải danh sách sản phẩm (đã kèm đầy đủ thông tin chi tiết và biến thể):
```
POST https://levents.asia/view/products
```

### 2.2. Cấu Trúc Payload POST

Để gọi API thành công, cần gửi payload JSON dạng POST với các tham số bắt buộc sau:
- `site_id`: `"af59cab4-c62d-4826-8e90-807ce1c501df"` (ID của cửa hàng Levents trên hệ thống Storecake).
- `category_id`: `"all_products"` (Để lấy toàn bộ sản phẩm).
- `limit`: Số lượng sản phẩm cần lấy trên mỗi trang (ví dụ: `100`).
- `page`: Trang cần tải (bắt đầu từ `1`).
- `get_dom`: Đặt thành `false` để nhận dữ liệu JSON thô (raw JSON) thay vì chuỗi HTML render sẵn.

---

## 3. Thách Thức & Giải Pháp

### A. Lọc Sản Phẩm Không Phù Hợp
- **Vấn đề**: Levents bán các sản phẩm thời trang Unisex cùng một số phụ kiện đi kèm. Theo yêu cầu dự án, chúng ta cần loại bỏ các sản phẩm giày dép (như "Levents® Everstar Slide") và các sản phẩm quà tặng / khuyến mãi đi kèm (như "[Hàng tặng không thu tiền] Levents® XL Cup").
- **Giải pháp**: 
  - Lọc bỏ sản phẩm có tiêu đề chứa từ khóa giày dép (`slides`, `slide`, `dép`, `giày`, `shoes`).
  - Lọc bỏ sản phẩm bắt đầu bằng `[Hàng tặng` hoặc chứa `quà tặng`.
  - Giữ lại các sản phẩm tất/vớ thời trang (`socks`, `tất`, `vớ`) như ngoại lệ được cho phép.

### B. Trích Xuất Ảnh Thông Tin Sản Phẩm (Infographic / Size Guide)
- **Vấn đề**: Bản thân Levents sử dụng các infographic chứa bảng kích cỡ và mô tả chi tiết sản phẩm dạng ảnh (được hiển thị khi click vào "Thông tin sản phẩm"). Chúng ta cần lấy đúng URL của ảnh này.
- **Giải pháp**: Ảnh này được lưu trữ trong danh sách mô tả ngắn của sản phẩm (`short_description`). Chúng ta quét qua mảng `short_description` của sản phẩm, tìm kiếm thẻ `<img>` và trích xuất đường dẫn ảnh `src` (nằm trên CDN `https://content.pancake.vn/...`).

### C. Ánh Xạ Thuộc Tính Biến Thể (Color & Size Options)
- **Vấn đề**: Biến thể (`variations`) của Storecake được lưu dưới dạng danh sách các cặp khóa-giá trị trong trường `fields` (ví dụ: `[{"name": "Size", "value": "Size 1"}, {"name": "Color", "value": "Black"}]`). Cần ánh xạ đúng sang `option1` (màu sắc) và `option2` (kích cỡ).
- **Giải pháp**: Viết hàm duyệt qua `fields` của từng variant, kiểm tra xem tên trường có chứa chữ "màu"/"color" để lấy giá trị Color, hoặc "size"/"kích" để lấy giá trị Size, đảm bảo ánh xạ động chính xác.

---

## 4. Kết Quả

- **Số lượng**: 73 sản phẩm độc nhất (loại trừ 1 dép lê và 1 cup quà tặng), kèm đầy đủ hàng ngàn biến thể.
- **Ảnh**: Giữ nguyên URL tuyệt đối của CDN Pancake.vn, không tải ảnh về máy để tối ưu tài nguyên.
- **File Output**: `harvest/levents/output/levents_products_full.json`.
