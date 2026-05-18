# Phase 1D — Evaluation Dataset (User Study + LLM-as-Judge)

> **Sprint:** S8, S9 (evaluation + final report)  
> **Mục đích:** Thu thập user ratings và LLM-judge scores để evaluate outfit recommendation quality

---

## 1. User Study — Label Schema

### File: `data/raw/user_study/responses.csv`

| Column | Type | Valid values | Required | Ví dụ |
|---|---|---|---|---|
| `response_id` | string | unique | ✅ | `resp_001` |
| `outfit_id` | string | ref to outfits.jsonl | ✅ | `outfit_00001` |
| `user_id` | string | anonymized | ✅ | `user_anon_042` |
| `body_shape` | enum | 5 shapes | ✅ | `hourglass` |
| `occasion` | enum | 8 occasions | ✅ | `casual` |
| `rating_style` | int | 1–5 (Likert) | ✅ | `4` |
| `rating_fit` | int | 1–5 (Likert) | ✅ | `4` |
| `rating_occasion` | int | 1–5 (Likert) | ✅ | `5` |
| `rating_overall` | int | 1–5 (Likert) | ✅ | `4` |
| `comment` | string | free text, optional | ❌ | `"Love the color combo"` |
| `timestamp` | ISO8601 | `YYYY-MM-DDTHH:MM:SS` | ✅ | `2026-05-18T10:30:00` |

### Likert Scale Definition

| Score | Meaning |
|---|---|
| 1 | Rất tệ / Hoàn toàn không phù hợp |
| 2 | Tệ |
| 3 | Trung bình |
| 4 | Tốt |
| 5 | Rất tốt / Phù hợp hoàn toàn |

### 4 Rating Dimensions

- **rating_style**: Outfit có hợp thời trang không?
- **rating_fit**: Outfit có phù hợp với body shape được nhận dạng không?
- **rating_occasion**: Outfit có phù hợp dịp/occasion không?
- **rating_overall**: Bạn có muốn mặc outfit này không?

---

## 2. LLM-as-Judge Schema

### File: `data/raw/user_study/llm_judge.csv`

| Column | Type | Required | Ví dụ |
|---|---|---|---|
| `judge_id` | string | ✅ | `judge_001` |
| `outfit_id` | string | ✅ | `outfit_00001` |
| `body_shape` | enum | ✅ | `hourglass` |
| `occasion` | enum | ✅ | `casual` |
| `score_style` | float | ✅ | `4.2` |
| `score_fit` | float | ✅ | `3.8` |
| `score_occasion` | float | ✅ | `4.5` |
| `score_overall` | float | ✅ | `4.0` |
| `reasoning` | string | ✅ | `"The wrap dress flatters an hourglass figure..."` |
| `model` | string | ✅ | `gemini-2.0-flash` |
| `timestamp` | ISO8601 | ✅ | `2026-05-18T10:30:00` |

---

## 3. Survey Form (Google Forms template)

**Section 1: Background**
```
Q1: Bạn tự đánh giá body shape của mình là gì?
    ○ Hourglass  ○ Pear  ○ Apple  ○ Rectangle  ○ Inverted Triangle
    ○ Không biết

Q2: Bạn thường mặc đồ cho dịp nào nhiều nhất? (chọn 1)
    ○ Casual  ○ Formal  ○ Business  ○ Sport  ○ Party  ○ Other
```

**Section 2: Outfit Rating** (lặp lại cho mỗi outfit, tối thiểu 5 outfits/người)
```
[Hiện ảnh outfit]

Q3: Outfit này có hợp thời trang không?
    1 (Rất tệ) ○ ○ ○ ○ ○ 5 (Rất tốt)

Q4: Outfit này có phù hợp với body type [body_shape] không?
    1 (Không phù hợp) ○ ○ ○ ○ ○ 5 (Rất phù hợp)

Q5: Outfit này có phù hợp cho dịp [occasion] không?
    1 (Không phù hợp) ○ ○ ○ ○ ○ 5 (Rất phù hợp)

Q6: Nhìn chung, bạn có muốn mặc outfit này không?
    1 (Không muốn) ○ ○ ○ ○ ○ 5 (Rất muốn)

Q7: Nhận xét thêm (tùy chọn): [text input]
```

---

## 4. Target sample size

| Metric | Target |
|---|---|
| Số người tham gia | ≥ 30 người |
| Outfits mỗi người rate | ≥ 5 outfits |
| Total responses | ≥ 150 rows |
| Outfits được cover | ≥ 50 outfits khác nhau |
| LLM judge rows | ≥ 200 (tất cả outfits trong test set) |

---

## 5. Cấu trúc thư mục

```
data/raw/user_study/
├── responses.csv          # User study Likert ratings
├── llm_judge.csv          # Gemini judge scores
└── outfit_images/         # Rendered outfit collages (3x1 grid)
    ├── outfit_00001.jpg
    └── ...
```

---

## 6. Tạo outfit collage cho survey

Script render 3 ảnh items thành 1 collage để dùng trong survey:

```bash
uv run python scripts/render_outfit_collages.py \
    --outfits data/raw/outfits/outfits.jsonl \
    --catalog-images data/raw/catalog/images/ \
    --out-dir data/raw/user_study/outfit_images/ \
    --n-outfits 50
```

---

## 7. Composite score (Grading target)

```
composite = 0.4 × rating_overall_mean + 0.3 × rating_fit_mean + 0.3 × rating_occasion_mean
```

**Target:** `composite ≥ 3.8 / 5.0` trên tập 30+ respondents.
