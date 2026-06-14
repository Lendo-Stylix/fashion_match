# Owen.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép chi tiết toàn bộ quá trình nghiên cứu, thiết kế kiến trúc, các thách thức kỹ thuật và giải pháp xử lý trong quá trình tự động thu thập dữ liệu từ `owen.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Magento 2** thương mại điện tử truyền thống.
- **Phát hiện quan trọng**: Mặc dù trang storefront render HTML phía máy chủ, trang web này cung cấp một cổng API GraphQL công khai đầy đủ chức năng tại `https://owen.vn/graphql`.
- **Lợi ích kiến trúc**: Tránh việc dùng trình duyệt tự động hóa (Selenium/Playwright) tải HTML nặng nề, giúp tăng tốc độ cào gấp 20 lần và loại bỏ rủi ro bị chặn IP bởi các hệ thống bảo mật CDN.

---

## 2. Kiến Trúc API GraphQL Đã Khám Phá

### 2.1. Truy Vấn Danh Mục (Category Tree)
Chúng ta lấy danh sách các Category ID của dự án bằng truy vấn GraphQL sau:
```graphql
{
  categoryList {
    id
    name
    children {
      id
      name
      url_path
    }
  }
}
```
Các danh mục chính được lọc để cào:
- **Áo (ID 41)**: Polo (`59`), Sơ Mi (`60`), T-Shirt (`56`), Veston (`58`), Jacket (`62`), Len (`57`), Bộ đồ (`2472`), Blazer (`2743`), Nỉ (`3471`).
- **Quần (ID 40)**: Quần Tây (`54`), Quần Short (`52`), Quần Khaki (`55`), Quần Jeans (`53`), Quần Jogger (`101`), Quần Nỉ (`3470`).
- **Phụ Kiện (ID 42)**: Tất (`100`), Dây Lưng (`64`), Ví Da (`65`), Cà Vạt (`66`).

### 2.2. Truy Vấn Chi Tiết Sản Phẩm & Variants
Sử dụng query `products` lọc theo `category_id`, hỗ trợ phân trang sạch sẽ qua variables `pageSize` và `currentPage`:
```graphql
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      id
      name
      sku
      url_key
      description { html }
      price_range { ... }
      image { url }
      media_gallery { url disabled }
      ... on ConfigurableProduct {
        configurable_options { ... }
        variants {
          product {
            id
            sku
            name
            stock_status
            price_range { ... }
            image { url }
          }
          attributes { label code value_index }
        }
      }
    }
  }
}
```

---

## 3. Thách Thức Kỹ Thuật & Giải Pháp Thực Chiến

### A. Các Sản Phẩm Đơn Giản (Simple Products) Không Có Variants
- **Vấn đề**: Các phụ kiện (tất, dây lưng, ví, cà vạt) là sản phẩm đơn giản trong Magento nên GraphQL không trả về dữ liệu `variants`.
- **Giải pháp**: Nếu mảng `variants` trống sau khi parse, tự động sinh một bản ghi variant mặc định với kích thước `"FREESIZE"`, lấy màu sắc từ thông tin sản phẩm hoặc tiêu đề và gán giá/hình ảnh của sản phẩm cha.

### B. Thiếu SKU Cho Sản Phẩm Trong Dữ Liệu Trả Về từ API
- **Vấn đề**: Nhiều sản phẩm cha và sản phẩm đơn giản trả về trường `sku` rỗng hoặc `null` trong response GraphQL.
- **Giải pháp**: Viết hàm `infer_sku` thông minh sử dụng Regex để tìm các chuỗi khớp với định dạng mã sản phẩm tiêu chuẩn của Owen (ví dụ: `TA252530`, `BELT261059`, `VD233254`, `QJS241269`) từ tiêu đề sản phẩm.

### C. Lọc Ảnh Lỗi / Ảnh Placeholder
- **Vấn đề**: Một số variant hoặc sản phẩm đi kèm các URL hình ảnh mặc định (placeholder của Magento).
- **Giải pháp**: Lọc bỏ toàn bộ các URL chứa cụm từ `/placeholder/`. Nếu ảnh của variant là placeholder, tự động kế thừa ảnh đại diện của sản phẩm cha.

### D. Lỗi Encode Console trên Windows
- **Vấn đề**: In ký tự tiếng Việt có dấu ra console Windows gây crash mã hóa.
- **Giải pháp**: Reconfigure stdout của Python thành UTF-8 bằng `sys.stdout.reconfigure(encoding='utf-8')`.

---

## 4. Kết Quả Thu Thập

- **File output**: `harvest/owen/output/owen_products_full.json`
- **Số lượng sản phẩm**: 1.132 sản phẩm độc nhất.
- **Số lượng variant**: 5.704 variants.
- **Độ chính xác dữ liệu**: Đạt chuẩn chi tiết tối đa, đầy đủ màu sắc, kích thước, trạng thái kho hàng (`stock_status`), và chất liệu/kiểu dáng được trích xuất từ phần mô tả.
