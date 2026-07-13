# Diagnostic Report — Demo outfit không khớp KB / giá giống nhau

**Ngày:** 2026-07-13
**Trigger:** Output từ `scripts/stylist/run_inference_device.py` (prompt "đám cưới, 1 triệu")
**Verdict:** **KHÔNG phải model hallucinate.** 3 bug ở **Tầng 3 retrieval + data**, không phải Tầng 2 stylist.

---

## 1. Triệu chứng (những gì user thấy)

```
occasion=wedding, body_shape=pear, price_max=1000000
→ 5 outfit: OF_00001..OF_00005, TẤT CẢ price=295,000 VND,
  style=['casual','sporty'], store=YODY
  items = "top + bottom + shoes + outerwear + bag" (generic, không có title)
```

3 dấu hiệu đáng ngờ:
1. `style=['casual','sporty']` KHÔNG khớp `occasion=wedding` (đám cưới cần `formal`/`elegant`)
2. 5 outfit cùng giá chính xác 295,000 VND
3. `OF_00001..OF_00005` sequential — không phải ID ổn định

---

## 2. Bằng chứng chẩn đoán

### 2.1 Query thẳng KB, KHÔNG có price_max → outfit HỢP LÝ

```
occasion=wedding (no price cap):
  OF_00001 price=2,088,000 style=['casual','feminine','korean','sporty']
      [dress] Jumpsuit Ngắn Sathy (Rubies, formal, 450k)
      [shoes] Giày Cao Gót Cơ Bản (YODY, smart_casual, 499k)
      [outerwear] Áo Khoác Blazer Nữ Olia (Rubies, formal, 640k)
      [bag] Vest Nữ Gile (YODY, formal, 499k)
  → outfit formal đa dạng, đa store, giá thực tế
```

→ Graph KB **hoạt động đúng** khi không có price cap. Bug nằm ở pipeline filter.

### 2.2 Query demo CHÍNH XÁC (có price_max=1M) → outfit rẻ bất thường

```
occasion=wedding, price_max=1000000, body_shape=pear:
  Tất cả 5 outfit: 4×49,000 + 99,000 = 295,000 VND
  items: Áo Dài Tay Túi Ốp (49k), Chân Váy Ôm Công Sở (49k),
         Dép Cao Gót Vuông (49k), Set Vest Croptop (49k),
         Túi Xách Công Sở (99k)
```

Giá 49k **được scrape hợp lệ** từ YODY (`item_store_links.parquet` xác nhận). Đây là **giá variant tối thiểu / sale clearance** trên product page YODY — không phải bug scrape, nhưng là **outlier kéo total xuống thấp bất thường**.

### 2.3 Catalog price distribution (5,618 rows)

| Metric | Giá trị |
|---|---|
| items ≤ 60,000 VND | **1,125** (20%) |
| items ≤ 100,000 VND | **1,441** (26%) |
| median | 390,000 VND |
| p10 / p90 | 49,000 / 1,450,000 VND |

→ 26% catalog dưới 100k (hầu hết là tất, sticker, phụ kiện — nhưng có cả áo/váy 49k outlier).

---

## 3. 3 nguyên nhân gốc (TẤT CẢ non-model)

### Bug #1 — `price_max=1,000,000` quá hẹp cho wedding (TRIGGER CHÍNH)

- Outfit wedding thật (formal dress + blazer + heels) giá **2–2.4M VND**
- Với cap=1M, retrieval **loại hết outfit formal hợp lý**, chỉ giữ combo rẻ 295k
- Đây là lý do 5 outfit đều 295k — **chỉ combo đó** vừa dưới 1M
- **Fix demo script:** bỏ/giảm `price_max` mặc định, hoặc tăng lên 3M cho wedding

### Bug #2 — Store-level `style_tags` áp dụng cho mọi item (`assemble_record._outfit_styles`)

```python
# src/outfitmatch/kb/assemble_record.py::_outfit_styles
store = STORES_BY_ID.get(store_id)        # config.py: YODY style_tags=("casual","sporty")
styles.update(store.style_tags)           # → áp cho MỌI item YODY, kể cả formal
```

- Item YODY formality=`formal` vẫn bị gán style `['casual','sporty']`
- → Output hiển thị `style=['casual','sporty']` dù items là formal công sở
- **Fix:** dùng item-level style nếu có, hoặc kết hợp formality-derived style

### Bug #3 — `outfit_id` là runtime positional, không ổn định (`to_outfit_record`)

```python
# src/outfitmatch/kb/assemble_record.py::to_outfit_record
outfit_id=f"OF_{index:05d}",    # index = vị trí trong list trả về
```

- Reset mỗi lần gọi → luôn `OF_00001..OF_00005`
- Không phải hallucinate (outfit thật từ graph), nhưng **không stable ID**
- **Fix (optional):** UUID5 của sorted item_ids → ID ổn định qua các lần chạy

---

## 4. Gì KHÔNG phải lỗi

| Triệu chứng | Phải lỗi không? | Lý do |
|---|---|---|
| Model hallucinate outfit_id | ❌ KHÔNG | IDs là output retrieval thật từ graph KB |
| Tool_call sai | ❌ KHÔNG | `occasion=wedding` đúng `vocab.py`, schema hợp lệ |
| Item bịa / không có thật | ❌ KHÔNG | 5 item đều có `product_url` YODY thật |
| Graph KB hỏng | ❌ KHÔNG | Query không price_max → outfit formal hợp lý |

→ **Stylist (T3) hoàn toàn đúng việc nó.** Bug nằm ở **downstream retrieval + data + display**.

---

## 5. Đề xuất fix (ưu tiên)

| # | Fix | Layer | Effort | Impact |
|---|---|---|---|---|
| **A** | Demo script: bỏ `price_max` mặc định + cảnh báo khi filter loại >50% seed | script | 🟢 nhỏ | giải quyết triệu chứng chính |
| **B** | `_outfit_styles`: item-level style (từ formality) trước, store-level fallback | retrieval | 🟡 vừa | sửa style mismatch cho mọi occasion |
| **C** | Audit YODY 49k prices: `price_audit.flag_price_outliers` (per-store median) | data | 🟡 vừa | surfacing giá outlier thay vì xoá |
| **D** | `outfit_id` = `OF_`+8-hex(uuid5(sorted item_ids)) → stable ID | schema | 🟢 nhỏ | ID nhất quán qua runs |
| **E** | Hiển thị item `title_vi` + `product_url` trong output demo | script | 🟢 nhỏ | user thấy item cụ thể |

**Đã apply A + B + C + D + E (commit kế tiếp, verified):**
- A/E: `run_inference_device.py` (commit f18fdd8)
- B: `assemble_record._outfit_styles` — style giờ derive từ `formality` (formal→elegant/classic,
  smart_casual→minimalist/korean) merge với store tags, clamp vào `STYLE_SET`.
- C: mới `src/outfitmatch/kb/price_audit.py` (`flag_price_outliers` + `audit_prices`) + test
  `tests/kb/test_price_audit.py`. Catalog KHÔNG có cột `original_price_vnd` — chỉ `price_vnd` +
  `sale_price_vnd` (428 non-null) — nên audit thực chất là **price-outlier** (item < 20% median
  store) chứ không phải original-vs-sale. Outlier KHÔNG bị xoá (hàng thật), chỉ surfaced.
- D: mới `src/outfitmatch/kb/ids.py` (`stable_outfit_id`) — `to_outfit_record` + `_make_outfit`
  dùng id ổn định; `validation.py` regex nới rộng `\bOF_[0-9A-Za-z]{5,}\b` để vẫn match id hex.

**Lưu ý còn lại (không phải bug):** `price_max=1,000,000` trong demo là do **model tự generate**
(tool_call của T3), không phải hardcode. FIX A chỉ cảnh báo; muốn outfit wedding đúng (2-3M) thì
cần thư giãn budget trong prompt/system hoặc thêm re-rank theo price tier. Đây là hướng tương lai.

---

## 6. Bài học (cho báo cáo thuyết trình)

Điểm nhấn DL quan trọng cho slide:
> **Hallucination detection phải tách bạch model vs pipeline.** Khi output sai, lỗi thường ở
> downstream (retrieval filter, data quality, display) chứ không phải model. Trong case này,
> model T3 + LoRA hoạt động hoàn hảo (tool_call đúng schema, enum đúng vocab) — bug nằm ở
> `price_max` filter quá hẹp + store-level style tags. Đây là lý do benchmark OutfitMatch đo
> **Tool F1** (model behavior) tách biệt với **retrieval quality** (downstream).

---

*Hết báo cáo chẩn đoán. Xem `scripts/stylist/run_inference_device.py` (commit kế tiếp) cho fix A + E.*
