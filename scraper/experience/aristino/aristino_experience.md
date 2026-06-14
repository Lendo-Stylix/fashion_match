# Aristino.com — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `aristino.com`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Shopify** e-commerce backend.
- **Dữ liệu**: Hỗ trợ endpoint chuẩn `/collections/{collection-slug}/products.json` trả về JSON trực tiếp mà không cần qua HTML scraping.
- **Thách thức chính**: Tránh cào các sản phẩm đồ lót (trừ đồ bơi/tất), giày dép, đồ trẻ em theo yêu cầu của hệ thống.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. Endpoint Danh Sách Sản Phẩm

Shopify hỗ trợ lấy danh sách sản phẩm theo collection dưới dạng JSON:
```
GET https://aristino.com/collections/{collection-slug}/products.json?limit=250&page={page}
```

Các collection chính được cào:
- `all` (Tất cả sản phẩm) hoặc các danh mục con cụ thể như `ao-so-mi-nam`, `ao-thun-nam`, `ao-polo-nam`, `quan-tay-nam`.

---

## 3. Thách Thức & Giải Pháp

### A. Lọc Danh Mục & Sản Phẩm Không Phù Hợp
- **Vấn đề**: Aristino bán cả đồ lót nam, tất/vớ và một số phụ kiện khác. Chúng ta cần loại trừ đồ lót và giày dép, trẻ em nhưng giữ lại tất/vớ và đồ bơi.
- **Giải pháp**: Sử dụng một danh sách từ khóa loại trừ (`EXCLUDE_KEYWORDS`) để kiểm tra tiêu đề và phân loại của sản phẩm trước khi lưu.

### B. Map Kích Thước & Màu Sắc Variant
- **Vấn đề**: Shopify lưu các option của variant dưới dạng `option1`, `option2`, `option3`. Cần xác định chính xác option nào là màu sắc và option nào là kích thước để đưa về chuẩn project.
- **Giải pháp**: Duyệt qua danh sách `options` của product để tìm chỉ số (index) của option chứa chữ "màu" hoặc "size", sau đó trích xuất tương ứng từ variant.

---

## 4. Kết Quả

- **File output**: `harvest/aristino/output/aristino_products_full.json`
- **Hình ảnh**: Lưu URL tuyệt đối củ CDN Shopify.
- **Số lượng**: 49 sản phẩm độc nhất, 289 variants.
