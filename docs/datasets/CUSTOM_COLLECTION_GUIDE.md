# Custom Data Collection Guide

> Hướng dẫn này dành cho team khi tự chụp ảnh hoặc gán nhãn data thủ công.  
> Đọc kỹ schema trong file của từng phase trước khi thu thập.

---

## Checklist trước khi bắt đầu

- [ ] Đọc `BODY_PIPELINE.md` (Phase 1A) hoặc `CATALOG_ENCODER.md` (Phase 1B) tùy phase
- [ ] Cài đặt môi trường: `uv sync`
- [ ] Chuẩn bị thiết bị: camera ≥ 12MP hoặc điện thoại flagship
- [ ] Chuẩn bị nền trắng (backdrop hoặc tường trắng) cho catalog items
- [ ] Đặt file vào đúng thư mục `data/custom/<phase>/`
- [ ] Chạy validate sau khi thu thập xong

---

## Phase 1A — Chụp ảnh body (full-body)

### Setup chụp ảnh

```
Khoảng cách: 2–3m từ camera đến người
Chiều cao camera: ngang thắt lưng hoặc thấp hơn (~1m) để chụp toàn thân
Nền: tường trắng, xám nhạt, hoặc ngoài trời sáng đồng đều
Ánh sáng: đứng quay mặt về phía cửa sổ hoặc dùng đèn studio 2 bên
```

### Tư thế chuẩn

```
✅ Đứng thẳng, nhìn thẳng vào camera
✅ Tay thả lỏng dọc theo người (không che body)
✅ Hai chân rộng bằng vai
✅ Đầu và chân đều trong khung hình
✅ Quần áo bó sát (áo thun + legging / jeans slim-fit)

❌ Tránh: Tay chéo ngực, tay trên hông
❌ Tránh: Quần áo oversize che body shape
❌ Tránh: Ngược sáng (đứng giữa cửa sổ và camera)
❌ Tránh: Bị cắt chân hoặc đỉnh đầu
```

### Quy trình gán nhãn body shape

1. Load ảnh vào `scripts/label_body_shape_interactive.py` (rule-based helper)
2. Script hiển thị ảnh và hỏi vai/eo/hông (cm) hoặc dùng YOLO tự động
3. Rule engine tính body shape theo `src/outfitmatch/body/shape_rules.py`
4. Xác nhận hoặc override thủ công
5. Output ghi vào `data/custom/body/body_labels.csv`

### Quy tắc naming ảnh

```
body_custom_<3-digit-id>.jpg
Ví dụ: body_custom_001.jpg, body_custom_002.jpg, ...
```

---

## Phase 1B — Chụp ảnh catalog items

### Setup chụp ảnh

```
Nền: tờ carton trắng hoặc lightbox
Ánh sáng: 2 đèn LED softbox 2 bên (hoặc cạnh cửa sổ sáng)
Góc: thẳng từ trên xuống (flat-lay) hoặc treo lên hanger thẳng
Khoảng cách: item chiếm 60–80% frame
```

### Flat-lay vs Hanger

| Loại item | Nên dùng |
|---|---|
| Tops, dresses, outerwear | Flat-lay hoặc hanger |
| Bottoms | Flat-lay (trải phẳng) |
| Shoes, bags | Flat-lay hoặc prop stand |
| Accessories | Flat-lay |

### Quy trình gán nhãn catalog

1. Chụp ảnh, lưu vào `data/custom/catalog/images/`
2. Mở `data/custom/catalog/catalog_metadata.csv` (tạo nếu chưa có)
3. Điền theo schema: `item_ID, image_path, text, category1, category2, color, source, split`
4. Viết `text` caption theo template: `"[color] [material] [fit/style] [category] [details]"`
5. Assign split: 70% train, 15% val, 15% test (hoặc random)

### Quy tắc naming ảnh

```
item_custom_<5-digit-id>.jpg
Ví dụ: item_custom_00001.jpg
```

---

## Phase 1C — Tạo outfit sets

### Option A: Kết hợp từ catalog có sẵn

```python
# Dùng script helper để create outfit từ items đã label
uv run python scripts/create_outfit_interactive.py \
    --catalog data/raw/catalog/catalog_metadata.parquet \
    --out data/custom/outfits/outfits.jsonl
```

Script hiển thị items theo category, bạn chọn top + bottom + shoes rồi rate compatible/not.

### Option B: Import từ screenshot

1. Chụp/screenshot outfit từ Pinterest, OOTD apps
2. Tìm item tương tự trong catalog hoặc thêm custom item
3. Điền `data/custom/outfits/outfits.jsonl` theo schema
4. Label `compatible=true` (outfit từ nguồn = đã được styled)

### Tạo negative samples (compatible=false)

Để cân bằng dataset, cần 50% negative. Cách nhanh nhất:

```bash
uv run python scripts/generate_negative_outfits.py \
    --outfits data/custom/outfits/outfits.jsonl \
    --n-negatives 100
```

Script random-pairs items từ categories khác nhau và mark `compatible=false`.

---

## Workflow tổng hợp

```
1. Thu thập ảnh / items
        ↓
2. Đặt vào data/custom/<phase>/
        ↓
3. Gán nhãn (thủ công hoặc script helper)
        ↓
4. Validate:
   uv run python scripts/validate_custom_data.py --phase <1A|1B|1C>
        ↓
5. Merge vào raw (khi đã pass validate):
   uv run python scripts/merge_custom_data.py --phase <1A|1B|1C>
        ↓
6. Commit DVC:
   dvc add data/raw/
   git add data/raw.dvc data/raw/.gitignore
   git commit -m "data: add custom <phase> samples"
```

---

## Quy tắc chung

1. **Không bao giờ commit ảnh lên git** — chỉ commit `.dvc` files
2. **Không sửa `data/raw/`** trực tiếp — chỉ sửa `data/custom/` rồi dùng merge script
3. **ID phải unique toàn bộ** — không trùng với raw data (`body_custom_*`, `item_custom_*`)
4. **Ghi rõ `source`** — tên người collect hoặc nguồn scrape (để kiểm soát license)
5. **Split stratified** — đảm bảo val/test có đủ mỗi class
