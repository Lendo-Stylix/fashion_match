# CityCycle.store — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết kinh nghiệm kỹ thuật, cấu trúc hạ tầng, thách thức và giải pháp phát hiện được trong quá trình tự động cào dữ liệu từ website `citycycle.store`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Nhanh.vn** (Hệ thống quản lý bán hàng và e-commerce đa kênh phổ biến tại Việt Nam).
- **Đặc trưng URL**:
  - Danh mục sản phẩm (Category): Có cấu trúc kết thúc bằng `-pc[ID_DANH_MỤC].html` (Ví dụ: `/tshirt-pc185564.html`).
  - Trang chi tiết sản phẩm (PDP): Có cấu trúc kết thúc bằng `-p[ID_SẢN_PHẨM].html` (Ví dụ: `/ao-thun-contours-v2-p38396737.html`).
- **Hình ảnh**: Lưu trữ trên CDN của Nhanh.vn (`https://pos.nvncdn.com/`). Giữ nguyên URL tuyệt đối của ảnh thay vì tải về máy.

---

## 2. Kiến Trúc Dữ Liệu & Giải Pháp Kỹ Thuật

### A. Phân Trang & Khám Phá Sản Phẩm (Discovery)
- Nhanh.vn sử dụng tham số query chuẩn `?page=N` để phân trang trên các danh mục.
- Tổng số trang (`totalPages`) được trích xuất bằng cách tìm thẻ có class `totalPages` hoặc phân tích nội dung thẻ hiển thị số sản phẩm `labelPages` (Ví dụ: `1 - 24 / 84` -> 4 trang).
- Script tự động quét qua 13 danh mục chính (T-shirt, Polo, Sweater, Pants, Accessory, v.v.), loại trừ thư mục `Underwear` (trừ tất, vớ, đồ bơi) và các sản phẩm không thuộc phạm vi yêu cầu.

### B. Ánh Xạ Biến Thể (Variant & Options Mapping)
- **Thách thức**: HTML trang chi tiết sản phẩm không nhúng trực tiếp JSON chứa cấu trúc variant.
- **Giải pháp**: 
  - Màu sắc được hiển thị dưới dạng swatch (`.color a`). Thẻ `<a>` của mỗi màu chứa thuộc tính `data-pids` chứa danh sách ID variant phân tách bằng dấu phẩy (Ví dụ: `data-pids="38396738,38396739,38396740"` cho màu "Chì").
  - Kích thước hiển thị trong `.size a`. Danh sách kích thước (Ví dụ: `["M", "L", "XL"]`) ánh xạ tương ứng 1-1 theo thứ tự với danh sách variant ID trong `data-pids`.
  - Từ đó, chúng ta kết hợp chính xác từng cặp Màu sắc/Kích thước với ID variant tương ứng.

### C. Lấy Tồn Kho Thực Tế (Live Stock Query)
- **Thách thức**: Tồn kho chi tiết của các kích cỡ không có sẵn trong HTML và không thay đổi theo click.
- **Giải pháp**: Phát hiện API endpoint POST `/product/checkinventory` chấp nhận payload url-encoded chứa danh sách variant ID cần kiểm tra (Ví dụ: `ps[0][id]=ID1&ps[0][storeId]=24295`).
- API trả về JSON chứa số lượng tồn kho chính xác của từng variant.
- Harvester thu thập toàn bộ variant ID của toàn bộ sản phẩm và gọi API này theo lô (batch of 50) để cập nhật tồn kho cuối cùng, tối ưu hóa tốc độ và giảm tải cho máy chủ.

### D. Trích Xuất Thông Số Sản Phẩm (Specifications Parsing)
- Chi tiết mô tả nằm trong thẻ `<section class="pviewcontent">`.
- Trích xuất thông tin kỹ thuật bằng biểu thức chính quy (Regex):
  - **Chất liệu**: Tìm từ khóa `Chất liệu:` hoặc `Chất vải:` hoặc từ khóa thay thế (ví dụ: Cotton, Nỉ, Len).
  - **Kiểu dáng**: Tìm từ khóa `Kiểu dáng:` hoặc `Form dáng:` hoặc từ khóa dáng rộng (Oversized, Boxy).
  - **Hình in**: Tìm từ khóa `Hình in:` hoặc hiệu ứng in.

---

## 3. Kết Quả Thu Thập

- **Tổng số sản phẩm cào thành công**: 140 sản phẩm độc nhất.
- **Tổng số variants**: 775 variants.
- **Tệp đầu ra**: [citycycle_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/citycycle/output/citycycle_products_full.json)
- **Kinh nghiệm thực chiến**: Việc kết hợp parse tĩnh HTML để lấy cấu trúc variant cùng gọi API POST để cập nhật tồn kho là giải pháp tối ưu nhất cho nền tảng Nhanh.vn, tránh hoàn toàn việc phải giả lập click trình duyệt nặng nề.
