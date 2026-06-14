# Underarmour.com.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết kinh nghiệm kỹ thuật, các phân tích hệ thống, thách thức và giải pháp áp dụng trong quá trình tự động thu thập dữ liệu từ website bán hàng chính thức của **Under Armour Việt Nam** (`underarmour.com.vn`).

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Shopify** e-commerce platform.
- **Phương thức truy cập**: Sử dụng hệ thống API storefront công khai v1 của Shopify (`/products.json?limit=250&page={page}`).
- **Thuận lợi**: Truy xuất được cấu trúc JSON gốc có độ chính xác cao, đầy đủ thông tin về các variant (màu sắc, kích thước, SKU, giá, trạng thái kho hàng) và các trường dữ liệu phụ trợ mà không cần render trình duyệt giả lập.
- **Thách thức chính**: 
  - Lọc bỏ số lượng lớn sản phẩm Giày dép (Under Armour có tỉ trọng giày chạy bộ, giày tập luyện cực lớn trên store).
  - Loại bỏ các loại đồ lót nam/nữ (Boxerjock, Sports Bra/Áo ngực thể thao) nhưng phải giữ lại các phụ kiện tất/vớ thể thao (Socks) và đồ bơi.
  - Phân tích cú pháp mô tả HTML (`body_html`) để bóc tách thông số kỹ thuật (Chất liệu vải pha, form dáng, mã sản phẩm nội bộ và công nghệ đặc trưng như HeatGear, Iso-Chill).

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Endpoint Danh Sách Sản Phẩm
Hệ thống sử dụng endpoint feed sản phẩm chuẩn của Shopify:
```http
GET https://underarmour.com.vn/products.json?limit=250&page={page}
```
Query này trả về trực tiếp danh sách 250 sản phẩm trên mỗi page. Hệ thống có tổng cộng **1.254 sản phẩm** trên toàn bộ store trực tuyến, phân trang thành 6 trang.

---

## 3. Thách Thức & Giải Pháp Kỹ Thuật

### A. Chiến Lược Lọc Phân Loại Nghiêm Ngặt (Exclusion Filters)
Theo yêu cầu dự án, chúng ta cần loại bỏ các sản phẩm không thuộc phạm vi thời trang may mặc người lớn thông thường. Các bộ lọc được xây dựng như sau:
1. **Loại bỏ Trẻ em (Kids)**: Tìm kiếm các từ khóa `trẻ em`, `bé trai`, `bé gái`, `sơ sinh`, `em bé`, `trẻ nhỏ` và các kích cỡ trẻ em `y `, `y-`, `youth`, `kid` trong cả tiêu đề, tags và handle để loại bỏ 100% đồ trẻ em.
2. **Loại bỏ Giày dép (Footwear)**: Under Armour bán rất nhiều giày dép. Các từ khóa lọc bao gồm `giày`, `dép`, `sandal`, `sneaker`, `slides`, `shoes`, `footwear`, `slip-on` và `quai ngang`.
3. **Loại bỏ Đồ lót (Underwear) nhưng giữ Tất & Đồ bơi**: 
   - Trước tiên, kiểm tra các từ khóa ngoại lệ giữ lại: `tất`, `vớ`, `socks`, `đồ bơi`, `swimwear`, `swim`. Nếu khớp, bỏ qua bộ lọc đồ lót tiếp theo.
   - Nếu không thuộc ngoại lệ, tiến hành lọc bỏ các từ khóa đồ lót: `đồ lót`, `quần lót`, `áo lót`, `sịp`, `boxer`, `boxerjock`, `brief`, `panties`, `bra`, `sports bra` (áo ngực thể thao).
4. **Loại bỏ Mỹ phẩm (Cosmetics)**: Lọc các từ khóa hóa mỹ phẩm/trang điểm.

### B. Map Kích Thước & Màu Sắc Variant Linh Hoạt
- **Vấn đề**: Shopify lưu variant dạng phẳng (`option1`, `option2`, `option3`). Vị trí của Color và Size có thể thay đổi tùy cấu hình sản phẩm (Ví dụ: Option 1 có thể là Size ở một số sản phẩm và Color ở các sản phẩm khác).
- **Giải pháp**: Quét mảng định nghĩa `options` của sản phẩm gốc để tìm vị trí chính xác của trường Màu sắc và Kích thước, sau đó ánh xạ động vào `option1` (Color) và `option2` (Size) của variant đích.

### C. Bóc Tách Thông Số Kỹ Thuật (Specifications Parsing)
- **Vấn đề**: Dữ liệu thông số kỹ thuật nằm lồng trong các thẻ `<li>` hoặc đoạn văn của `body_html` dưới dạng văn bản tiếng Việt.
- **Giải pháp**: Xây dựng thuật toán phân tích cú pháp kết hợp BeautifulSoup và Regular Expression:
  - Trích xuất mã sản phẩm/Style Code từ các dòng chứa `Mã sản phẩm` hoặc `Style #`.
  - Nhận diện thành phần chất liệu (ví dụ: `60% Cotton / 40% Polyester`) bằng cách quét ký tự `%` đi kèm các từ khóa sợi vải.
  - Bóc tách form dáng (như `Oversize`, `Fitted`, `Loose`, `Rộng rãi`) và công nghệ đi kèm (`HeatGear`, `Storm`).

---

## 4. Kết Quả Thu Thập

- **Tổng số sản phẩm quét**: 1.254 sản phẩm.
- **Số sản phẩm bị loại bỏ**: 
  - Đồ trẻ em (Kids): 17 sản phẩm.
  - Giày dép (Footwear): 510 sản phẩm (Tỷ lệ cực kỳ cao do đặc thù hãng thể thao).
  - Đồ lót/Sports Bra (Underwear): 52 sản phẩm.
  - Mỹ phẩm (Cosmetics): 7 sản phẩm.
- **Số sản phẩm may mặc thành công**: **668 sản phẩm** độc nhất.
- **Tổng số variant thu thập**: **2.999 variants** (bao gồm đầy đủ màu sắc/kích cỡ thực tế).
- **Đường dẫn lưu trữ**: [underarmour_products_full.json](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/loc_scraper/harvest/underarmour/output/underarmour_products_full.json).
- **Hình ảnh**: Lưu trữ URL CDN tuyệt đối từ Shopify (`https://cdn.shopify.com/s/files/...`), chống tải tệp hình ảnh cục bộ để tối ưu dung lượng đĩa.
