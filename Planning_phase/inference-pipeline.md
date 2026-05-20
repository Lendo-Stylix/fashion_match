# Inference Pipeline — OutfitMatch

> **Branch:** Model  
> **Updated:** 2026-05-20  
> **Source:** Corrected from `inference-pipeline.txt` based on `docs/ARCHITECTURE.md`

---

## Tổng quan

Nhận vào **text prompt + (optional) ảnh selfie** của người dùng, trả về **top-3~5 outfit set** phù hợp với vóc dáng, dịp và sở thích.

Mục tiêu latency: **< 3 giây trên CPU**.

---

## Luồng 6 bước

```
[INPUT]
User: text prompt  +  (optional) selfie image
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────┐
│  Step 1: Preference Structuring (Layer 0)   │
│  SLM / Gemini phân tích prompt              │
│  → StructuredPreference {hard, soft}        │
│    hard → HardConstraint (màu/loại/chất     │
│            liệu tránh, fit bias)             │
│    soft → SoftPreference {style,color,fit}  │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Step 2: Body Shape Extraction (Layer 1)    │
│  (chỉ khi có ảnh selfie)                    │
│  YOLO-pose → 17 keypoints COCO              │
│  → shoulder/hip/waist ratios                │
│  → 5-class rule classifier                  │
│  → body_shape: pear/apple/hourglass/        │
│                rectangle/inverted_triangle  │
│  → apply_body_fallback nếu hard rỗng        │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Step 3: Catalog Retrieval (Layer 2+3)      │
│  3a. Hard filter: Qdrant payload filter     │
│      (categories_exclude, colors_avoid,     │
│       body_shape filter nếu có)             │
│  3b. Semantic ANN search:                   │
│      Query text → fashionSigLIP encoder     │
│      → 768-dim query vector                 │
│      → Qdrant cosine search                 │
│      → candidate pool per category slot     │
│         (tops, bottoms, dresses, ...)       │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Step 4: Outfit Composition + Scoring       │
│         (Layer 4 — OutfitTransformer)       │
│  4a. Group candidates theo category slot   │
│  4b. Tổ hợp outfit set dựa trên top outfit │
│      templates (VN/Châu Á/Âu/Global)        │
│  4c. OutfitTransformer forward:             │
│      [CLS][item×N][BODY][OCC][PREF×K]       │
│      → compatibility score mỗi outfit set  │
│  4d. Rank & deduplicate by score            │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Step 5: Customization (Layer 5 — optional) │
│  POST /customize-item nếu user muốn         │
│  thay một item trong outfit                 │
│  → Qdrant filter + composer re-rank         │
│  → replacement item list                   │
└─────────────────────────────────────────────┘
         │
         ▼
[OUTPUT]
Top 3–5 outfit sets, mỗi set gồm:
  - item list (image + metadata)
  - compatibility score
  - body_shape used (nếu có)
  - occasion tag
```

---

## Chi tiết từng bước

### Step 1 — Preference Structuring

| Component | Chi tiết |
|---|---|
| Module | `src/outfitmatch/preference/structuring.py` |
| Model | Gemini API (hoặc stub nếu key không có) |
| Input | `instruction: str`, `body_shape: str` |
| Output | `StructuredPreference` |
| Cache | SHA256(`EXTRACTOR_VERSION \| instruction`) → `diskcache` |
| Version | `EXTRACTOR_VERSION = "v1"` — bump = cache invalidated |

**Xử lý thiếu thông tin:**
- Nếu prompt thiếu occasion → soft.style mặc định `"casual"`
- Nếu không có ảnh → body_shape = `""` → không áp dụng body filter
- Nếu `hard.is_empty()` → `apply_body_fallback(pref, body_shape)` điền `fit_bias`

---

### Step 2 — Body Shape Extraction

| Component | Chi tiết |
|---|---|
| Module | `src/outfitmatch/body/` |
| Model | YOLOv8-pose (`yolov8n-pose.pt`) |
| Input | `PIL.Image` (selfie) |
| Output | `body_shape: str` (5 classes) |
| Fallback | Nếu không detect được pose → `body_shape = ""` |

**Tại sao optional:** Ảnh selfie có thể chứa thông tin cá nhân nhạy cảm — người dùng có quyền không cung cấp.

---

### Step 3 — Catalog Retrieval

| Component | Chi tiết |
|---|---|
| Module | `src/outfitmatch/encoders/` + Qdrant client |
| Encoder | `Marqo/marqo-fashionSigLIP` → 768-dim |
| VectorDB | Qdrant Docker `:6333`, collection `catalog` |
| Filter | Payload filter: `categories_exclude`, `colors_avoid`, `body_shapes` |
| Search | Cosine ANN, top-K per slot (K=50 mặc định) |

**Điểm khác vs. inference-pipeline.txt gốc:**  
Step gốc dùng tag-based lookup truyền thống → đây thay bằng **semantic ANN** (chính xác hơn, kết hợp được hard filter của Qdrant).

---

### Step 4 — Outfit Composition + Scoring

| Component | Chi tiết |
|---|---|
| Module | `src/outfitmatch/train/composer.py` |
| Model | `OutfitTransformer` (4-layer, 8-head, d=512) |
| Tokens | `[CLS]` + `[item×N]` + `[BODY]?` + `[OCC]?` + `[PREF_g×K]?` |
| Output | Scalar compatibility score per outfit set |
| Templates | Top outfit templates để tạo candidate set combinations |

**Merge với step gốc:**  
Step 5 (grouping) + Step 6 (OutfitTransformer scoring) trong txt gốc được **merge thành Step 4** vì chúng là một forward pass liên tục.

---

### Step 5 — Customization (optional)

| API | `POST /customize-item` |
|---|---|
| Input | `{outfit_id, item_slot, target_attrs}` |
| Process | Qdrant filter theo target_attrs + composer re-rank |
| Output | Danh sách replacement items cho slot đó |

---

## Điểm đã sửa so với inference-pipeline.txt gốc

| # | Vấn đề gốc | Sửa |
|---|---|---|
| A | 2 SLM riêng biệt (agent1 keyword + agent2 form) | 1 `PromptStructurer` (Gemini) → `StructuredPreference` trực tiếp |
| B | Retrieval step 3 chỉ dùng tag-based lookup | Thêm semantic ANN (fashionSigLIP + Qdrant cosine) |
| C | Step 4 "ranking theo giá/brand" — không rõ nguồn data | Loại bỏ; ranking = OutfitTransformer compatibility score |
| D | Body shape chỉ dùng trong step 2, không kết nối step sau | Body shape → `[BODY]` token trong OutfitTransformer + payload filter Qdrant |
| E | Step 5 (grouping) và Step 6 (scoring) tách rời | Merge thành 1 forward pass của OutfitTransformer |
| F | 7 bước với logic trùng lặp | Hợp nhất thành 6 bước rõ ràng theo layer architecture |

---

## API Endpoints

```
POST /recommend
  Body: {image_b64?: str, height?: float, weight?: float, occasion?: str, instruction?: str}
  Response: {outfits: [{items: [...], score: float, body_shape: str}], latency_ms: int}

POST /search
  Body: {query_text: str}
  Response: {items: [{item_ID, image_url, text, score}]}

POST /customize-item
  Body: {outfit_id: str, item_slot: str, target_attrs: dict}
  Response: {replacements: [{item_ID, image_url, score}]}
```
