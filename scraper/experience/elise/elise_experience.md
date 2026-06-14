# Elise.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `elise.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: **Magento 2** storefront.
- **Backend API**: **GraphQL API** tại `https://elise.vn/graphql`.
- **CDN Hình Ảnh**: `https://elise.vn/media/catalog/product/`

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. API GraphQL Lấy Sản Phẩm Theo Danh Mục
Sử dụng GraphQL query gửi POST request đến `/graphql` để truy xuất sản phẩm phân trang theo ID danh mục (`category_id`):

```graphql
query($catId: String!, $pageSize: Int!, $page: Int!) {
  products(filter: {category_id: {eq: $catId}}, pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      id
      name
      sku
      url_key
      price_range {
        minimum_price {
          regular_price { value }
          final_price { value }
        }
      }
      image { url }
      configurable_options { ... }
      variants { ... }
    }
  }
}
```

---

## 3. Thách Thức & Giải Pháp

### A. Tách biệt màu sắc
- **Vấn đề**: Trong Magento, các màu sắc khác nhau của một sản phẩm thường được quản lý như các sản phẩm cha độc lập (có `url_key` riêng) và biến thể (`variants`) chỉ thay đổi về kích thước.
- **Giải pháp**: Xử lý mỗi sản phẩm cha như một thực thể độc lập. Trích xuất màu sắc bằng cách phân tích tên sản phẩm hoặc thuộc tính `color` nếu có sẵn.

---

## 4. Kết Quả

- **File output**: `harvest/elise/output/elise_products_full.json`
- **Số lượng**: 978 sản phẩm độc nhất, 2920 variants.
