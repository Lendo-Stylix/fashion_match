# OutfitMatch — System Architecture (v3.1-lite)

> **Agents: đọc file này trước khi viết code.** Nó định nghĩa boundaries giữa các module,
> data flow, và các invariant mọi module phải tôn trọng.
> Canonical spec ở [`Kien_truc_v3.1.md`](../Kien_truc_v3.1.md).

---

## 1. System Overview — 4 Tầng v3.1-lite

```
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 1: OUTFIT GRAPH KB (offline — build 1 lần)             │
│  OutfitTransformer-labse (frozen) → item embedding           │
│  pair_scoring + graph.py → sparse item-compatibility graph   │
│  (category/gender/formality gated, top-K) → item_edges.parquet│
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 2: CONVERSATIONAL STYLIST (Qwen3-VL-8B + LoRA nhẹ)      │
│  Parse intent · ask follow-up · call search_outfits tool      │
│  Validate outfit_id · sinh giải thích tiếng Việt              │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 3: RETRIEVAL ENGINE (Qdrant items filter + traversal)  │
│  Filter seed item (top/dress) theo gender/formality→occasion │
│  Graph traversal ráp clique → OutfitRecord → Top 30–50        │
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
| `src/outfitmatch/kb/catalog.py` | Load scraped catalog rows → `ItemRecord` | Score / build graph |
| `src/outfitmatch/kb/embedding.py` | Trích item embedding qua OT-labse | Filter / tag outfit |
| `src/outfitmatch/kb/pair_scoring.py` | Bounded edge weight giữa 2 item node | Decide edge existence |
| `src/outfitmatch/kb/graph.py` | Sparse item-compat graph (category/gender/formality gated) | Score weight, I/O |
| `src/outfitmatch/kb/graph_store.py` | `item_edges.parquet` + Qdrant `items` node index | Generate edges |
| `src/outfitmatch/kb/traversal.py` | Clique-safe outfit assembly từ seed item | I/O, filtering |
| `src/outfitmatch/kb/assemble_record.py` | Derive `OutfitRecord` tags từ assembled items | Traversal logic |
| `src/outfitmatch/kb/graph_eval.py` | `GraphReport` (coverage/coherence/reuse) | Build graph |
| `src/outfitmatch/kb/generation.py` | _(legacy materialized)_ FITB+Beam + random+score | Score / tag outfit |
| `src/outfitmatch/kb/scoring.py` | _(legacy materialized)_ re-score outfit | Generate / tag outfit |
| `src/outfitmatch/kb/tagging.py` | Gemini item semantic tagging for graph KB | Score outfit, gọi encoder |
| `src/outfitmatch/kb/qdrant_index.py` | _(legacy materialized)_ index `outfits` collection | Generate / score outfit |
| `src/outfitmatch/retrieval.py` | Tầng 3: seed filter + traversal + post-filter | Training, model loading |
| `src/outfitmatch/stylist/tools.py` | `search_outfits` tool definition (enum từ vocab) | Model loading, inference |
| `src/outfitmatch/stylist/validation.py` | Extract + validate outfit_id trong response | Business logic |
| `src/outfitmatch/stylist/model.py` | Qwen3-VL-8B + LoRA loading + inference | Dataset loading |
| `src/outfitmatch/stylist/data.py` | Conversation dataset cho LoRA fine-tune | Inference |
| `src/outfitmatch/quiz/schema.py` | `QuizAnswers` + `PreferenceProfile` + `quiz_to_profile` | Re-ranking logic |
| `src/outfitmatch/quiz/rerank.py` | Preference-based outfit re-rank | Quiz UI, dataset loading |
| `src/outfitmatch/metrics/outfit.py` | `fitb_accuracy` + `compatibility_auc` (pure math) | I/O, model loading |
| `src/outfitmatch/metrics/retrieval.py` | `recall_at_k` + graph-native `fitb_recall_at_k` | I/O, model loading |
| `src/outfitmatch/pipeline.py` | Wire Tầng 2–4 thành E2E `recommend_outfit` | Training logic |

---

## 3. Controlled Vocabulary Invariant

**File:** `src/outfitmatch/vocab.py` — nguồn sự thật duy nhất cho mọi enum.

Cả 3 nơi sau PHẢI dùng cùng giá trị từ `vocab.py`:
1. Gemini Flash LLM-tagging prompt (build KB) / item formality + gender inference.
2. `search_outfits` tool parameters cho Qwen3-VL.
3. Qdrant `items` payload index field values (graph seed filter).

**Rule:** Giá trị nội bộ luôn là English `snake_case`. Tiếng Việt chỉ xuất hiện trong
`*_LABELS_VI` dicts và UI `*_vi` schema fields.

**Tuyệt đối không đổi tên** một enum value đã có — sẽ vô hiệu hoá toàn bộ KB.
Có thể thêm value mới; không được đổi value cũ.

---

## 4. Knowledge Base Schema

Graph KB lưu **item node** (`ItemRecord`) + **canonical edge** (`item_edges.parquet`).
`OutfitRecord` được **dẫn xuất khi traversal** (không materialize trước):

```jsonc
// ItemRecord (node) — nguồn dữ liệu chính
{
  "item_id": "item_custom_00001",
  "category": "top",                        // ITEM_CATEGORY enum
  "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
  "item_embedding": [/* OT-labse dim — xác minh từ checkpoint */],
  "gender": "women",                        // GENDER enum (men|women|unisex|kid)
  "formality": "smart_casual",              // FORMALITY enum
  "body_shapes_fit": ["pear", "rectangle"], // Gemini item semantic tags
  "season": ["summer", "transitional"],     // Gemini item semantic tags
  "stylist_notes_vi": "Áo dáng suông dễ phối.",
  "store": {
    "store_id": "canifa_vn",
    "store_name": "Canifa",
    "product_url": "https://canifa.com/...",
    "price_vnd": 299000,
    "colors": ["beige", "navy"],
    "in_stock": true
  }
}

// OutfitRecord (derived từ traversal, assemble_record.py)
{
  "outfit_id": "OF_00001",
  "schema_version": "3.1",
  "items": [/* clique item nodes */],
  "compatibility_score": 0.0,               // mean pairwise edge weight
  "occasion": ["office", "cafe_hangout"],   // derive từ formality (FORMALITY_OCCASIONS)
  "style": ["minimalist", "korean"],        // derive từ store style_tags
  "body_shapes_fit": ["pear"],             // intersect từ item semantic tags
  "season": ["transitional"],              // intersect từ item semantic tags
  "color_palette": ["beige", "navy"],
  "price_total_vnd": 850000,
  "price_tier": "mid",
  "has_vn_store": true,
  "gen_method": "graph_traversal"
}
```

> **`occasion` + `style` vẫn là 2 trường conditioning hạng nhất** nhưng **derived**:
> `occasion` từ `formality` band (`FORMALITY_OCCASIONS` trong `vocab.py`), `style` từ
> store `style_tags`. `body_shapes_fit` / `season` được Gemini tag ở **item node** rồi
> `assemble_record.py` lấy **intersection bảo thủ** trên các item đã tag. `schema_version="3.1"`
> để trace.

---

## 5. Retrieval Design (Tầng 3)

v3.1-lite **không dùng query vector** cho Qdrant. Graph traversal thay vì materialized sort:

1. Qwen3-VL gọi `search_outfits(occasion, style, body_shape, price_max, exclude_colors)`.
2. Qdrant **filter seed item** (anchor `top` / `dress`) trên collection `items` theo
   `gender`, `formality` (→ occasion qua `formalities_for_occasion`), `in_stock`,
   `has_vn_store`. Fallback: scan graph trực tiếp khi Qdrant không sẵn sàng.
3. **Graph traversal** (`traversal.py`) ráp clique-safe outfit từ seed; `assemble_record.py`
   dẫn xuất `OutfitRecord` (occasion/style/body_shapes_fit/season/color/price). Post-filter
   `style`, `price_max`, `exclude_colors` trên record đã dẫn.
4. Rank theo mean pairwise edge weight + dedup → Top 30–50 outfit → Tầng 4.

Cách này tránh lỗ hổng "user query → outfit embedding space" của v3.0 và giữ invariant
gender/formality tự động (outfit = clique trong graph đã gated).

**Qdrant collection:** `items` (graph path). Payload indexes trên: `category`, `gender`,
`formality`, `price_tier`, `has_vn_store`, `in_stock`, `store_id`.

```python
qdrant.create_collection(
    collection_name="items",
    vectors_config=models.VectorParams(
        size=ITEM_EMBED_DIM,  # xác minh từ OT-labse item embedding — KHÔNG hardcode
        distance=models.Distance.COSINE,
    ),
)
for field in ["category", "gender", "formality", "price_tier",
              "has_vn_store", "in_stock", "store_id"]:
    qdrant.create_payload_index("items", field, models.PayloadSchemaType.KEYWORD)
```

> **Legacy materialized path** (`outfits` collection, `qdrant_index.py`) vẫn giữ để so
> sánh nhưng KHÔNG phải đường dẫn chính.

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
Step 4  Qwen gọi search_outfits(filters) → Qdrant `items` seed filter
         → graph traversal ráp clique → 30–50 outfit
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
| Recall@5 (graph FITB) | regression guard (full-sweep ≈ 0.98) | `fitb_recall_at_k`: mask 1 item, traversal recover top-5 |
| Catalog coverage (diversity) | ≥ 0.60 full-sweep | `GraphReport.catalog_coverage` |
| Coherence violations | = 0 (hard) | `GraphReport` (edge gate regression) |
| FITB accuracy | ≥ 55% | OT-labse trên Polyvore (`Kien_truc_v3.1.md` §3.6) |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore |
| Body-cond. Precision@5 | PENDING item semantic tagging | (chưa đo cho graph MVP) |
| E2E latency | < 5–8s GPU / cloud (streaming) | đo trên GPU |
| LLM-as-judge (Gemini) | mean ≥ 3.5 / 5 | Gemini chấm output E2E |

Bốn ablation bắt buộc (`Kien_truc_v3.1.md` §8):
1. **Encoder variants** — OT-labse zero-shot vs OT-labse fine-tuned Polyvore.
2. **Body conditioning on/off** — PENDING item semantic tagging.
3. **Occasion conditioning on/off** — seed filter `formalities_for_occasion` (`eval_graph`).
4. **Greedy vs Beam** — `AssemblyConfig(beam=1)` vs `beam=3` (`eval_graph`).

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
