# Phase 1A — Body Pipeline Dataset

> **Sprint:** S3 (data collection), S6 (body-aware training)  
> **Mục đích:** Train body shape classifier (5 classes) và body-aware embedding (ViBE-style contrastive)

---

## 1. Label Schema

### File: `data/raw/body/body_labels.csv`

| Column | Type | Valid values | Required | Ví dụ |
|---|---|---|---|---|
| `image_id` | string | unique | ✅ | `body_001` |
| `image_path` | string | relative to `data/raw/body/images/` | ✅ | `body_001.jpg` |
| `body_shape` | enum | `hourglass` · `pear` · `apple` · `rectangle` · `inverted_triangle` | ✅ | `hourglass` |
| `height_cm` | float | 140–210 | ❌ (optional) | `165.0` |
| `weight_kg` | float | 40–150 | ❌ (optional) | `58.0` |
| `gender` | enum | `female` · `male` · `non_binary` | ❌ | `female` |
| `skin_tone_hex` | string | `#RRGGBB` (từ mặt/cổ/tay) | ❌ | `#C68642` |
| `source` | string | tên dataset/người collect | ✅ | `custom_nhom` |
| `split` | enum | `train` · `val` · `test` | ✅ | `train` |

**Ví dụ 1 row:**
```csv
image_id,image_path,body_shape,height_cm,weight_kg,gender,skin_tone_hex,source,split
body_001,body_001.jpg,hourglass,165.0,58.0,female,#C68642,custom_nhom,train
```

---

## 2. Quy tắc phân loại 5 body shapes

Dựa trên tỉ lệ vai (`S`), eo (`W`), hông (`H`) — đây là các quy tắc **rule-based v0** trong `src/outfitmatch/body/shape_rules.py`:

| Shape | Điều kiện (ưu tiên từ trên xuống) |
|---|---|
| **Apple** | `W ≥ S` và `W ≥ H` — eo là phần rộng nhất |
| **Inverted Triangle** | `S/H > 1.05` — vai rộng hơn hông >5% |
| **Pear** | `S/H < 0.95` — hông rộng hơn vai >5% |
| **Hourglass** | `S ≈ H` và `W/max(S,H) ≤ 0.80` — vai=hông, eo thắt |
| **Rectangle** | `S ≈ H` và `W/max(S,H) > 0.80` — tất cả gần bằng nhau |

**Cách đo nhanh từ ảnh (không có dụng cụ):**
- Đứng thẳng mặt vào camera, tay thả lỏng
- Khoảng cách vai = từ mép vai trái đến mép vai phải (ngang)
- Khoảng cách hông = phần rộng nhất của hông
- Eo = phần hẹp nhất giữa ngực và hông

---

## 3. Yêu cầu ảnh

| Tiêu chí | Yêu cầu |
|---|---|
| **Background** | Đồng màu (trắng/xám nhạt) hoặc ngoài trời sáng rõ |
| **Góc chụp** | Thẳng mặt (front view) — body đầy đủ từ đầu đến chân |
| **Khoảng cách** | Toàn thân nằm trong khung, không bị cắt chân/đầu |
| **Quần áo** | Bó sát hoặc áo thun/quần jeans — tránh áo oversize che body |
| **Resolution** | Tối thiểu 512×1024px |
| **Format** | `.jpg` hoặc `.png` |
| **Ánh sáng** | Đủ sáng, không ngược sáng |
| **Tư thế** | Đứng thẳng, hai chân rộng bằng vai |

---

## 4. Cấu trúc thư mục

```
data/custom/body/
├── images/
│   ├── body_custom_001.jpg
│   ├── body_custom_002.jpg
│   └── ...
└── body_labels.csv          # Schema ở mục 1
```

---

## 5. Thu thập từ nguồn mở

### Nguồn khuyến nghị (đã kiểm tra)

| Dataset | Ảnh | Body diversity | Link |
|---|---:|---|---|
| **SHHQ-1.0** | 40K | Cao — đa dạng body | Request từ tác giả |
| **DeepFashion2** | 491K | Trung bình | [Github](https://github.com/switchablenorms/DeepFashion2) |
| `ryushinn/DeepFashion-Inshop-Filtered` | 52K | Thấp (model-thin bias) | `hf.co/datasets/ryushinn/DeepFashion-Inshop-Filtered` |

**Bias warning:** DeepFashion có bias nặng về người mẫu cao gầy. Cần oversample các body shapes `apple`, `pear`, `rectangle` khi train.

---

## 6. Target distribution (chống bias)

Mỗi body shape class phải chiếm **≥ 15%** của tổng training set:

| Shape | Target % | Min rows (nếu tổng 5K) |
|---|---|---|
| Hourglass | ≥ 15% | 750 |
| Pear | ≥ 15% | 750 |
| Apple | ≥ 15% | 750 |
| Rectangle | ≥ 15% | 750 |
| Inverted Triangle | ≥ 15% | 750 |

Nếu một class < 15%, dùng augmentation (flip ngang, brightness jitter) hoặc thu thập thêm.

---

## 7. Validation script

```bash
uv run python scripts/validate_custom_data.py --phase 1A
```

Script kiểm tra:
- Tất cả `image_path` tồn tại
- `body_shape` trong 5 classes hợp lệ
- Không có `image_id` duplicate
- In distribution report

---

## 8. Skin tone labels (Sprint 6 — tùy chọn)

Nếu có thể, label thêm `skin_tone_hex` để train color-aware recommendation:

```
Fitzpatrick 1 (rất sáng):  #FBEFD5 → #FAE0C1
Fitzpatrick 2 (sáng):       #F5D5AE → #EEC68A
Fitzpatrick 3 (trung bình): #D4A76A → #C68642
Fitzpatrick 4 (nâu trung):  #A0613C → #7D4E2C
Fitzpatrick 5 (nâu đậm):    #5A3120 → #3D1F10
Fitzpatrick 6 (rất đậm):    #2A1209 → #1A0B05
```

Cách label: crop mặt/cổ → lấy median pixel trong vùng skin → convert RGB→HEX.
