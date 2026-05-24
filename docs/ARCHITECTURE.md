# OutfitMatch — System Architecture (v3.1-lite)

> **Agents: đọc file này trước khi viết code.** Nó định nghĩa boundaries giữa các module,
> data flow, và các invariant mọi module phải tôn trọng.
> Canonical spec ở [`Kien_truc_v3.1.md`](../Kien_truc_v3.1.md).

---

## 1. System Overview — 4 Tầng v3.1-lite

```
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 1: OUTFIT KNOWLEDGE BASE (offline — build 1 lần)        │
│  OutfitTransformer-labse (frozen) + FITB/Beam → 5–20K outfit  │
│  Gemini Flash metadata tagging → occasion / style / body enum │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 2: CONVERSATIONAL STYLIST (Qwen3-VL-8B + LoRA nhẹ)      │
│  Parse intent · ask follow-up · call search_outfits tool      │
│  Validate outfit_id · sinh giải thích tiếng Việt              │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 3: RETRIEVAL ENGINE (Qdrant — filter-first)             │
│  Filter occasion/style/body/price/has_vn_store                │
│  Sort theo compatibility_score → Top 30–50 outfit             │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 4: PERSONALIZATION (Quiz Re-rank — MVP)                 │
│  5-question quiz → PreferenceProfile → additive re-rank       │
│  → Top 3–5 outfit + giải thích tiếng Việt                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Module Responsibilities

| Module | Responsibility | Must NOT do |
|---|---|---|
| `src/outfitmatch/vocab.py` | Single source of truth for all enum values | Define UI labels (dùng `*_LABELS_VI`) |
| `src/outfitmatch/kb/schema.py` | `ItemRecord` + `OutfitRecord` data types | Business logic, I/O |
| `src/outfitmatch/kb/embedding.py` | Trích item embedding qua OT-labse | Filter / tag outfit |
| `src/outfitmatch/kb/generation.py` | FITB+Beam (70%) + random+score (30%) | Score / tag outfit |
| `src/outfitmatch/kb/scoring.py` | Re-score mọi outfit bằng OT compatibility | Generate / tag outfit |
| `src/outfitmatch/kb/tagging.py` | Gemini Flash metadata tagging | Score outfit, gọi encoder |
| `src/outfitmatch/kb/qdrant_index.py` | Index KB lên Qdrant + payload indexes | Generate / score outfit |
| `src/outfitmatch/stylist/tools.py` | `search_outfits` tool definition (enum từ vocab) | Model loading, inference |
| `src/outfitmatch/stylist/validation.py` | Extract + validate outfit_id trong response | Business logic |
| `src/outfitmatch/stylist/model.py` | Qwen3-VL-8B + LoRA loading + inference | Dataset loading |
| `src/outfitmatch/stylist/data.py` | Conversation dataset cho LoRA fine-tune | Inference |
| `src/outfitmatch/quiz/schema.py` | `QuizAnswers` + `PreferenceProfile` + `quiz_to_profile` | Re-ranking logic |
| `src/outfitmatch/quiz/rerank.py` | Preference-based outfit re-rank | Quiz UI, dataset loading |
| `src/outfitmatch/metrics/outfit.py` | `fitb_accuracy` + `compatibility_auc` (pure math) | I/O, model loading |
| `src/outfitmatch/pipeline.py` | Wire Tầng 2–4 thành E2E `recommend_outfit` | Training logic |

---

## 3. Controlled Vocabulary Invariant

**File:** `src/outfitmatch/vocab.py` — nguồn sự thật duy nhất cho mọi enum.

Cả 3 nơi sau PHẢI dùng cùng giá trị từ `vocab.py`:
1. Gemini Flash LLM-tagging prompt (build KB).
2. `search_outfits` tool parameters cho Qwen3-VL.
3. Qdrant payload index field values.

**Rule:** Giá trị nội bộ luôn là English `snake_case`. Tiếng Việt chỉ xuất hiện trong
`*_LABELS_VI` dicts và UI `*_vi` schema fields.

**Tuyệt đối không đổi tên** một enum value đã có — sẽ vô hiệu hoá toàn bộ KB.
Có thể thêm value mới; không được đổi value cũ.

---

## 4. Knowledge Base Schema

Một outfit (`OutfitRecord`) trong KB:

```jsonc
{
  "outfit_id": "OF_00001",
  "schema_version": "3.1",
  "items": [
    {
      "item_id": "item_custom_00001",
      "category": "top",                        // ITEM_CATEGORY enum
      "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
      "item_embedding": [/* OT-labse dim — xác minh từ checkpoint */],
      "store": {
        "store_id": "canifa_vn",
        "store_name": "Canifa",
        "product_url": "https://canifa.com/...",
        "price_vnd": 299000,
        "in_stock": true
      }
    }
  ],
  "outfit_embedding": [/* cùng dim với item_embedding */],
  "compatibility_score": 0.0,               // ALWAYS re-scored sau khi generate
  "occasion": ["office", "cafe_hangout"],   // OCCASION enum (primary conditioning)
  "style": ["minimalist", "korean"],        // STYLE enum (primary conditioning)
  "body_shapes_fit": ["pear", "hourglass"],
  "season": ["transitional"],
  "color_palette": ["beige", "navy"],
  "price_total_vnd": 850000,
  "price_tier": "mid",
  "has_vn_store": true,
  "stylist_explanation_vi": "...",
  "gen_method": "fitb_beam"                  // "fitb_beam" | "random_scored"
}
```

> **`occasion` + `style` là 2 trường conditioning hạng nhất.** Hậu-MVP muốn nâng lên
> token huấn luyện `[OCC_x]` / `[STYLE_x]` (Phụ lục A) chỉ cần đọc trực tiếp 2 field này —
> không phải migrate KB. `schema_version="3.1"` để trace.

---

## 5. Retrieval Design (Tầng 3)

v3.1-lite **không dùng query vector** cho Qdrant. Thay vào đó:

1. Qwen3-VL gọi `search_outfits(occasion, style, body_shape, price_max, exclude_colors)`.
2. Qdrant **filter** theo metadata (occasion, style, body_shapes_fit, price_tier,
   `has_vn_store=True`, exclude_colors).
3. Kết quả **sort theo `compatibility_score` precomputed** (giảm dần) + diversity penalty.
4. Top 30–50 outfit trả về Tầng 4.

Cách này tránh lỗ hổng "user query → outfit embedding space" của v3.0.

**Qdrant collection:** `outfits`. Payload indexes trên: `occasion`, `style`,
`body_shapes_fit`, `price_tier`, `season`, `has_vn_store`.

```python
qdrant.create_collection(
    collection_name="outfits",
    vectors_config=models.VectorParams(
        size=OUTFIT_EMBED_DIM,  # xác minh từ OT-labse checkpoint — KHÔNG hardcode
        distance=models.Distance.COSINE,
    ),
)
for field in ["occasion", "style", "body_shapes_fit",
              "price_tier", "season", "has_vn_store"]:
    qdrant.create_payload_index("outfits", field, models.PayloadSchemaType.KEYWORD)
```

---

## 6. Hallucination Prevention (Tầng 2)

Sau khi Qwen3-VL sinh response, extract mọi `OF_NNNNN` reference và verify từng id
tồn tại trong KB:

```python
from outfitmatch.stylist.validation import validate_response

ok, invalid_ids = validate_response(response_text, valid_outfit_id_set)
if not ok:
    # KHÔNG hiển thị response; yêu cầu Qwen sinh lại
    ...
```

Bước này enforce trong `pipeline.py`. **Không được skip.**

---

## 7. E2E Inference Pipeline

```
Step 1  User: text + (optional) ảnh + đã làm quiz onboarding
Step 2  Qwen3-VL parse → {height, weight, skin_tone, occasion, style, missing_info[]}
Step 3  [Đủ info?] ──No──▶ Qwen hỏi lại (quay lại Step 1)
         │ Yes
Step 4  Qwen gọi search_outfits(filters) → Qdrant filter+sort → 30–50 outfit
Step 5  Tầng 4 re-rank theo PreferenceProfile từ quiz → Top 3–5
Step 6  Validation layer verify mọi outfit_id ref
Step 7  Qwen sinh giải thích tiếng Việt cá nhân hoá
Step 8  Hiển thị (ảnh + store + giá + link) + ghi nhận feedback
```

---

## 8. Body Shape Handling (Tầng 2 §4.4 — thận trọng)

- **Body shape:** ưu tiên suy từ `height/weight` (+ số đo nếu user nhập) hoặc quiz.
  Ảnh selfie thường chỉ có mặt/nửa người → **không đủ** để xác định pear/apple/hourglass;
  ảnh chỉ coi là tín hiệu phụ. v3.1-lite **không** chạy pose detection.
- **Skin tone:** user **tự chọn** từ bảng màu (`warm/neutral/cool`) thay vì AI đoán
  từ ảnh — tránh sai do ánh sáng và tránh vấn đề bias/privacy.

---

## 9. Grading Targets (DoD cho academic deliverable)

| Metric | Target | Đo bằng |
|---|---|---|
| Recall@5 (Qdrant retrieval) | encoder baseline + 5pp | `outfits` collection filter+sort |
| FITB accuracy | ≥ 55% | OT-labse trên Polyvore (`Kien_truc_v3.1.md` §3.6) |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore |
| Body-cond. Precision@5 | + 10pp vs non-conditional | Ablation Tầng 3 |
| E2E latency | < 5–8s GPU / cloud (streaming) | đo trên GPU |
| LLM-as-judge (Gemini) | mean ≥ 3.5 / 5 | Gemini chấm output E2E |

Bốn ablation bắt buộc (`Kien_truc_v3.1.md` §8):
1. **Encoder variants** — OT-labse zero-shot vs OT-labse fine-tuned Polyvore.
2. **Body conditioning on/off** — Tầng 3 filter body_shape.
3. **Occasion conditioning on/off** — Tầng 3 filter occasion.
4. **Greedy vs Beam decoding** — Tầng 1 KB build (`generation.py`).

---

## 10. Python 3.13 Constraints (hard rules)

| KHÔNG dùng | Dùng thay |
|---|---|
| `mediapipe` | _(v3.1 không pose-extract; bỏ luôn)_ |
| `faiss-cpu` pip | `qdrant-client` + Docker |
| `black` / `flake8` / `isort` | `ruff` |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |
| `AutoModelForCausalLM` cho Qwen3-VL | `Qwen3VLForConditionalGeneration` |
| `evaluation_strategy` trong TrainingArguments | `eval_strategy` (tên mới) |

---

## 11. Definition of Done (XP rule)

Feature DONE khi:
1. PR merged to `dev` với ≥ 1 peer review.
2. `pytest` coverage ≥ 70% cho module đụng tới, CI xanh.
3. Docstring trên public functions + entry `docs/feature.md`.
4. Reproducible: `uv sync && make demo` chạy từ scratch.
