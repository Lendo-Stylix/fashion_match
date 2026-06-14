# GUMAC.vn — Kinh Nghiệm Thực Chiến Cào Dữ Liệu

Tài liệu này ghi chép toàn bộ kinh nghiệm kỹ thuật, các thách thức và giải pháp thu thập được trong quá trình tự động cào dữ liệu từ `gumac.vn`.

---

## 1. Nhận Diện Nền Tảng & Hạ Tầng

- **Platform**: React SPA storefront giao tiếp với REST CMS API.
- **Backend API**: `https://cms.gumac.vn/api/v1`
- **CDN Hình Ảnh**: `https://cms.gumac.vn`
- **Đặc điểm**: Danh sách sản phẩm của GUMAC gồm 731 sản phẩm, được quản lý tập trung và phân trang qua CMS API.

---

## 2. Kiến Trúc API Đã Khám Phá

### 2.1. API Danh Sách Sản Phẩm (Tất Cả Sản Phẩm)
Chúng ta có thể lấy toàn bộ sản phẩm của Gumac bằng cách phân trang trực tiếp:
```
GET https://cms.gumac.vn/api/v1/products?page={page}&limit=20
```

**Response trả về:**
```json
{
  "data": [
    {
      "id": 58874,
      "name": "Chân váy bút chì xẻ",
      "slug": "vd12037",
      "category": { "id": 20213, "slug": "chan-vay-doc-quyen-online", "name": "Chân Váy..." },
      "colors": [ ... ],
      "sizes": [ ... ]
    }
  ],
  "meta": { "totalPages": 37, "limit": 20, "total": 731, "page": 1 }
}
```

---

## 3. Thách Thức & Giải Pháp

### A. Giá sản phẩm bằng 0
- **Thách thức**: CMS API của Gumac ở endpoint danh sách không trả về giá tiền (price/compare_at_price).
- **Giải pháp**: Phù hợp với dữ liệu mẫu hiện tại, toàn bộ sản phẩm của GUMAC được cào với giá mặc định là 0.

### B. Cấu trúc màu sắc & hình ảnh variant phức tạp
- **Thách thức**: Gumac lưu mảng hình ảnh tương ứng với từng màu sắc của sản phẩm trong mảng `colors[i].media.gallery`.
- **Giải pháp**: Duyệt qua từng màu, lấy danh sách ảnh của màu đó (nối thêm CDN prefix `https://cms.gumac.vn` nếu là URL tương đối) và gán cho các variant tương ứng với màu sắc đó.

---

## 4. Kết Quả

- **File output**: `harvest/gumac/output/gumac_products_full.json`
- **Số lượng**: 711 sản phẩm độc nhất, 5018 variants.
