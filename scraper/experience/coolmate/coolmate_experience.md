# Coolmate.me — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `coolmate.me`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Next.js 14+ App Router** (RSC - React Server Components).
- **CDN Hình Ảnh**: `https://media.coolmate.me` (các đường dẫn ảnh bắt đầu bằng `/image/`).

---

## 2. Kiến Trúc Dữ Liệu & Giải Pháp Kỹ Thuật

### A. Lỗi HTTP 500 Khi Gọi RSC Header trực tiếp
- **Vấn đề**: Gọi endpoint `/collection/{slug}?page={n}` với header `RSC: 1` bị chặn hoặc trả về lỗi **HTTP 500 Internal Server Error**.
- **Giải pháp**: Gửi request lấy HTML thông thường bằng header chuẩn của trình duyệt. Dữ liệu hydration được lưu trong các khối script dưới dạng `self.__next_f.push`.
- **Nội soi payload**: Dùng Regex để bắt các block `self.__next_f.push`, ghép chúng lại, unescape toàn bộ chuỗi (thay thế `\"` bằng `"` và `\\` bằng `\`) rồi quét chuỗi `{"serverData":` và cân bằng dấu ngoặc nhọn `{}` để giải nén JSON.

### B. Map CDN Hình Ảnh
- **Vấn đề**: Ảnh swatch màu và ảnh variant trả về dạng relative path như `/image/2026/...`.
- **Giải pháp**: Prepend subdomain `https://media.coolmate.me` để khôi phục URL ảnh tuyệt đối hoạt động bình thường.

---

## 3. Kết Quả

- **File output**: `harvest/coolmate/output/coolmate_products_full.json`
- **Số lượng**: 377 sản phẩm độc nhất, 5939 variants.
