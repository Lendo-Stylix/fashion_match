# badrabbitclub.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `badrabbitclub.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Haravan** e-commerce backend (cùng hạ tầng SaaS với Degrey, Dirtycoins).
- **Dữ liệu**: Hỗ trợ endpoint public `/collections/all/products.json?limit=250&page={page}` trả về danh sách đầy đủ sản phẩm, ảnh CDN, và biến thể (variants) dưới dạng JSON mà không cần tải trang HTML chi tiết.
- **Thách thức chính**:
  - Tách màu sắc và kích thước chính xác từ cấu trúc sản phẩm Haravan.
  - Phân tích và trích xuất đặc tính sản phẩm (Chất liệu, Form dáng, Kỹ thuật, Phụ kiện, Họa tiết) từ chuỗi văn bản mô tả sản phẩm `body_html` vốn có tính đồng nhất cao (theo cấu trúc danh sách liệt kê có dấu đầu dòng).
  - Tuân thủ các quy tắc loại trừ (không cào đồ lót, trẻ em, giày dép, mỹ phẩm) và yêu cầu giữ nguyên liên kết ảnh CDN không tải cục bộ.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Endpoint Danh Sách Sản Phẩm

Haravan hỗ trợ lấy toàn bộ danh sách sản phẩm của bộ sưu tập `all` dạng JSON:
```
GET https://badrabbitclub.vn/collections/all/products.json?limit=250&page={page}
```

- **Đặc tính**: Danh sách trả về đầy đủ các thông tin của biến thể như `option1` (chứa màu sắc) và `option2` (chứa kích thước), giá tiền (`price`, `compare_at_price`), ảnh biến thể (`image_id`), và số lượng tồn kho (`inventory_quantity`). Nhờ đó, toàn bộ quá trình thu thập thông tin chỉ mất một lượt tải API duy nhất, không cần gửi yêu cầu đến từng trang chi tiết (PDP), tối ưu hóa băng thông và thời gian chạy.

---

## 3. Thách Thức Kỹ Thuật & Giải Pháp

### A. Phân Tích Thông Số Sản Phẩm Tự Động (Specification Extraction)
- **Vấn đề**: Bad Rabbit trình bày thông số chi tiết dưới dạng danh sách bullet point trong mô tả sản phẩm `body_html` chứ không phải bảng `<table>`.
- **Giải pháp**: Thiết kế bộ parser nâng cao:
  - Thay thế các tag HTML xuống dòng (`<br>`, `</p>`, `</div>`) thành ký tự `\n` để phân chia dòng rõ ràng.
  - Sử dụng Regex bóc tách từng dòng, loại bỏ các ký tự dấu đầu dòng (`•`, `-`, `–`, `*`) và tìm các từ khóa đại diện (`Form dáng:`, `Chất liệu:`, `Màu sắc:`, `Kỹ thuật:`, `Phụ kiện:`, `Họa tiết:`).
  - Áp dụng Regex fallback để quét qua nội dung văn bản thuần nếu các thuộc tính cốt lõi bị trống.

### B. Ánh Xạ Biến Thể Động (Dynamic Variant Option Mapping)
- **Vấn đề**: Thứ tự lưu trữ của Color và Size trong options có thể thay đổi tùy thuộc vào cấu hình sản phẩm trên admin trang web.
- **Giải pháp**: Sử dụng cơ chế phát hiện chỉ mục tự động:
  - Quét qua mảng `options` của product để tìm vị trí index của tùy chọn chứa chữ "màu" hoặc "color" (màu sắc), và tùy chọn chứa chữ "size" hoặc "kích" (kích thước).
  - Ánh xạ chính xác biến thể tương ứng sang `option1` (Color) và `option2` (Size). Nếu không tìm thấy, tự động trích xuất màu sắc dự phòng từ tiêu đề hoặc thông số mô tả sản phẩm và đặt Size mặc định là `"FREESIZE"`.

### C. Lọc Các Danh Mục Ngoại Lệ
- **Vấn đề**: Bad Rabbit là một thương hiệu thời trang đường phố unisex có một số sản phẩm balo/túi/áo có chứa từ "baby" (ví dụ: `BALO BLOSSOM BABY RABBIT REGULAR BACKPACK` hay `ao-thun-kid-rabbit-regular-tee`). Cần phân biệt rõ ràng giữa các sản phẩm dành cho trẻ em (cần loại bỏ) và các sản phẩm của người lớn có chứa từ khóa này trong thiết kế/tên gọi nhân vật (cần giữ lại).
- **Giải pháp**:
  - Dùng bộ lọc loại trừ trẻ em dựa trên các từ khóa cụ thể như `"bé trai"`, `"bé gái"`, `"trẻ em"`, `"sơ sinh"`, `"em bé"`, `"kids"`, `"baby"`, `"boy"`, `"girl"`, `"child"`, `"children"`.
  - Thiết lập các trường hợp loại trừ ngoại lệ cho phong cách thời trang người lớn như `"baby tee"`, `"baby-tee"`, và các màu sắc như `"baby pink"`, `"baby blue"`.
  - Đối với `"ao-thun-kid-rabbit-regular-tee"`, hệ thống tự động kiểm tra bảng size và phát hiện sản phẩm có các kích cỡ người lớn (`XS`, `S`, `M`, `L`, `XL`), đồng thời đây là tên nhân vật ("Kid Rabbit"), do đó được giữ lại một cách chính xác.
  - Các balo trẻ em (`BALO BLOSSOM BABY RABBIT REGULAR BACKPACK`) đã được loại bỏ thành công.

---

## 4. Kết Quả Thu Thập

- **File Discovery**: [scraped_products.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/discovery/badrabbit/output/scraped_products.json)
- **File Harvest**: [badrabbit_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/badrabbit/output/badrabbit_products_full.json)
- **Hình ảnh**: Chỉ lưu trữ URL tuyệt đối của CDN Haravan (`https://cdn.hstatic.net/...`), không tải hình ảnh về cục bộ để tối ưu bộ nhớ.
- **Thống kê**:
  - Tổng số sản phẩm độc nhất thu thập được: **45**
  - Tổng số variants thu thập được: **215**
  - Phân loại ngành hàng:
    - Áo Thun: 26 sản phẩm
    - Balo & Túi: 8 sản phẩm
    - Khác (Chân váy): 3 sản phẩm
    - Áo Hoodie & Nỉ & Len: 4 sản phẩm
    - Quần Dài: 2 sản phẩm
    - Áo Khoác: 1 sản phẩm
    - Quần Shorts: 1 sản phẩm
