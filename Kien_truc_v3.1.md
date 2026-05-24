# 🎨 Kế hoạch Kiến trúc v3.1-lite — AI Stylist Cá nhân hóa (MVP)
## Phong cách Châu Á — Thị trường Việt Nam

**Ngày lập kế hoạch:** 22/05/2026
**Phiên bản:** 3.1-lite (kế thừa & thu hẹp có chủ đích từ v3.0)
**Quan hệ với v3.0:** v3.1-lite là **phạm vi MVP 3 tháng / 3 dev**. Toàn bộ tham vọng đầy đủ
của v3.0 (500K outfit, GNN, token huấn luyện, full fine-tune) được giữ lại trong
**Phụ lục A — Tầm nhìn 6 tháng**, không bị loại bỏ, chỉ bị hoãn.

> **Triết lý:** Chất lượng output đến từ **sự tập trung**, không phải quy mô.
> Một catalog tinh gọn nhưng sạch + retrieval vững + stylist hội thoại tốt
> sẽ cho trải nghiệm tốt hơn 500K outfit nhiễu. MVP phải **chạy E2E thật,
> trung thực, không fallback giả tạo**.

---

## 📋 Phần 0: Executive Summary

Hệ thống kết hợp **3 công nghệ AI cốt lõi** (giảm từ 4 so với v3.0):

| Công nghệ | Vai trò | Trạng thái MVP |
|-----------|---------|----------------|
| **OutfitTransformer-labse** | Knowledge Base Builder | Frozen — sinh KB; fine-tune Polyvore để đo metric |
| **Qwen3-VL-8B + LoRA** | Conversational Stylist | Fine-tune LoRA nhẹ (3–5K hội thoại) |
| **Qdrant + RAG** | Retrieval Engine | Metadata-filter + sort theo compatibility |
| ~~GNN~~ | ~~Personalization~~ | **Hoãn sang Phụ lục A** — MVP dùng quiz re-rank |

### Thay đổi cốt lõi so với v3.0

| Tầng | v3.0 | v3.1-lite (MVP) | Lý do |
|---|---|---|---|
| 1 — KB | OT+CLIP → **500K** outfit, 7 nguồn | OT-labse **frozen**, FITB+Beam → **5–20K** outfit, chỉ store VN | 3 dev/3 tháng không crawl nổi 255K+ item; chất lượng > số lượng |
| 2 — Stylist | Fine-tune Qwen3-VL **100K** convs, 4×A100 | Qwen3-VL-8B + **LoRA nhẹ 3–5K** convs | Chấp nhận reasoning yếu hơn để kịp timeline; vẫn có "phần fine-tune" cho báo cáo |
| 3 — RAG | Vector search (query vector chưa định nghĩa) | **Filter metadata trước → sort theo `compatibility_score`** | Xóa lỗ hổng "query text → outfit-embedding space" |
| 4 — Personalization | GNN LightGCN, 10K user | **Quiz 5 câu → re-rank rule-based** | MVP không có user thật → GNN không học được gì |

### Điểm khác biệt cốt lõi (giữ nguyên từ v3.0)

- ✅ Tập trung **phong cách châu Á** (K-fashion, minimalism Việt) — qua nguồn data + nhãn LLM.
- ✅ Hiểu **đặc điểm người Việt** (chiều cao, tone da, khí hậu nhiệt đới).
- ✅ **Hội thoại tự nhiên** — biết hỏi lại khi thiếu thông tin.
- ✅ **Giải thích được lý do** recommend (không black-box).
- ✅ Mỗi item recommend đều có **store VN + giá VND + link mua** rõ ràng.

---

## 🏛️ Phần 1: Kiến trúc Hệ thống

```
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 1: OUTFIT KNOWLEDGE BASE (Offline — build 1 lần)         │
│  OutfitTransformer-labse (frozen) + FITB/Beam → KB 5–20K outfit│
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 2: CONVERSATIONAL AI STYLIST (Qwen3-VL-8B + LoRA nhẹ)    │
│  Parse intent, hỏi lại, tool-calling, giải thích               │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 3: RETRIEVAL ENGINE (RAG)                                │
│  Qdrant: filter metadata → sort theo compatibility_score        │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 4: PERSONALIZATION (Quiz re-rank — MVP)                  │
│  Quiz 5 câu → preference → re-rank.  [GNN → Phụ lục A]         │
└──────────────────────────────────────────────────────────────┘
```

### Tại sao vẫn tách tầng?

1. **Tầng 1:** OutfitTransformer là mô hình *discriminative* — chỉ chấm điểm/xếp hạng,
   không sinh outfit mới. Nó dựng KB offline để các tầng sau retrieve.
2. **Tầng 2:** VLM không thể nhớ hàng chục nghìn outfit trong weights → cần "bộ nhớ
   ngoài" (Vector DB) + tool-calling.
3. **Tầng 3:** Tách "hiểu yêu cầu" khỏi "tìm outfit" giúp hệ modular, dễ debug.
4. **Tầng 4:** MVP chỉ cần cá nhân hóa nông (quiz). GNN cần lịch sử tương tác dài hạn
   — chỉ có ý nghĩa khi có user thật (xem Phụ lục A).

---

## 🔤 Phần 2: Controlled Vocabulary — nền tảng chống lỗi

> **Lỗi nghiêm trọng nhất của v3.0:** LLM gán nhãn tiếng Việt (`"dáng người quả lê"`)
> trong khi tool-call + Qdrant filter dùng tiếng Anh (`"pear"`) → filter trả về **0 kết quả**.
> v3.1-lite sửa triệt để bằng **một bộ enum DUY NHẤT**.

**File:** `src/outfitmatch/vocab.py` — nguồn sự thật duy nhất, được import bởi cả 3 nơi:
(1) LLM-tagging khi build KB, (2) tham số tool-call của Qwen3-VL, (3) Qdrant payload index.

| Enum | Giá trị nội bộ (English snake_case) |
|---|---|
| `OCCASION` | `office, interview, school, date, cafe_hangout, party, wedding, home_casual, travel` |
| `STYLE` | `minimalist, korean, streetwear, elegant, casual, vintage, sporty, feminine` |
| `BODY_SHAPE` | `pear, apple, hourglass, rectangle, inverted_triangle` |
| `SEASON` | `summer, transitional, winter, rainy` |
| `PRICE_TIER` | `budget, mid, premium` |
| `ITEM_CATEGORY` | `top, bottom, dress, outerwear, shoes, bag, accessory` |
| `SKIN_TONE` | `warm, neutral, cool` |

**Nguyên tắc:**
- Giá trị **nội bộ luôn là English snake_case**. Mọi so khớp (filter, tool-call) dùng giá trị này.
- Tiếng Việt **chỉ xuất hiện ở tầng hiển thị** — qua map nhãn `OCCASION_LABELS_VI = {"office": "đi làm", ...}`
  và các field `*_vi` trong schema.
- `BODY_SHAPE` khớp đúng `src/outfitmatch/preference/schema.py` đã có (`BODY_FALLBACK`).
- Mọi enum đều có thể bổ sung giá trị, nhưng **không đổi tên** giá trị đã dùng (tránh vỡ KB cũ).

---

## 🗄️ Phần 3: Tầng 1 — Outfit Knowledge Base

### 3.1 Mục tiêu
Tạo KB outfit **chất lượng cao, gán nhãn metadata đầy đủ** để Tầng 3 retrieve.
Quy mô MVP: **5–20K outfit** (không chốt cứng — phụ thuộc lượng item thu được ở Sprint 0;
ưu tiên chất lượng hơn số lượng).

### 3.2 Schema 1 outfit

```jsonc
{
  "outfit_id": "OF_00001",
  "schema_version": "3.1",
  "items": [
    {
      "item_id": "item_custom_00001",
      "category": "top",                       // ITEM_CATEGORY enum
      "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
      "item_embedding": [/* dim theo checkpoint — xác minh, xem 3.5 */],
      "store": {
        "store_id": "canifa_vn",
        "store_name": "Canifa",
        "product_url": "https://canifa.com/...",
        "price_vnd": 299000,
        "in_stock": true
      }
    }
    /* ... các item khác ... */
  ],

  "outfit_embedding": [/* ... */],
  "compatibility_score": 0.0,                  // OT chấm — LUÔN re-score outfit cuối

  // === 2 trường conditioning chính (controlled vocabulary) ===
  "occasion": ["office", "cafe_hangout"],      // OCCASION enum
  "style":    ["minimalist", "korean"],        // STYLE enum

  // === metadata phụ: filter nhanh + hiển thị ===
  "body_shapes_fit": ["pear", "hourglass"],    // BODY_SHAPE enum
  "season": ["transitional"],                  // SEASON enum
  "color_palette": ["beige", "navy"],
  "price_total_vnd": 850000,
  "price_tier": "mid",                         // PRICE_TIER enum
  "has_vn_store": true,

  "stylist_explanation_vi": "Set blazer oversized màu be phối quần ống rộng, tạo silhouette dài hợp dáng quả lê. Tối giản kiểu Hàn, hợp môi trường công sở.",

  "gen_method": "fitb_beam"                    // "fitb_beam" | "random_scored"
}
```

> **`occasion` + `style` là 2 trường conditioning hạng nhất**, lưu dưới dạng enum sạch.
> Hậu-MVP muốn nâng lên token huấn luyện `[OCC_x]`/`[STYLE_x]` (Phụ lục A) chỉ cần đọc
> trực tiếp 2 field này — **không phải migrate KB**. `schema_version` để trace.

### 3.3 Nguồn dữ liệu (MVP — chỉ store có nguồn & giá rõ ràng)

| Loại | Nguồn | Ghi chú |
|---|---|---|
| **Store VN** | YODY, Canifa, Format, The Blues, Libé, Elise, Owen, HNOSS | Có sẵn trong `docs/datasets/STORE_CATALOG_VN.md` |
| **International chain tại VN** | Uniqlo VN, Zara VN, H&M VN | Có cửa hàng/website chính thức tại VN → user mua được ngay |

**Loại khỏi MVP:** Musinsa, ZOZOTOWN, Taobao, YesStyle, Pinterest/Instagram.
Lý do: (1) anti-scraping mạnh + vi phạm TOS; (2) ảnh Pinterest/IG là **ảnh nguyên bộ trên
người**, không phải ảnh từng item rời — OutfitTransformer cần ảnh per-item, muốn dùng phải
thêm cả pipeline segmentation (ngoài scope MVP); (3) không có "phương pháp lấy hàng về VN"
rõ ràng. Các nguồn này nằm trong Phụ lục A.

> **Phân định data (xác nhận):** "Chỉ store VN" áp cho **catalog/KB** (thứ user được
> recommend và mua). OT-eval cho grading dùng **Polyvore** (public benchmark). LoRA cho
> Qwen3-VL dùng **hội thoại synthetic** sinh bằng Gemini. Ba luồng data độc lập.

Pipeline thu thập store đã được mô tả chi tiết trong `docs/datasets/STORE_CATALOG_VN.md`
(scrape JSON → normalize → CSV/Parquet → Qdrant payload) — v3.1-lite tái dùng nguyên.

### 3.4 Quy trình build KB

**Bước 1 — Ingestion & Preprocessing.** Cào item từ store VN → normalize về schema chuẩn
(`docs/datasets/STORE_CATALOG_VN.md`). Resize ảnh về kích thước Vision Encoder của OT;
ghép `title_vi + desc_vi` cho nhánh text (giữ nguyên tiếng Việt — LaBSE xử lý đa ngôn ngữ).

**Bước 2 — Item Embedding Extraction (offline, 1 lần).** Chạy mọi item qua encoder của
OutfitTransformer-labse → vector đại diện. Lưu vào Parquet.

**Bước 3 — Candidate Generation.** Hai phương pháp:

- **70% — Iterative FITB + Beam Search** (bộ "chuẩn mực, an toàn"):
  1. Random chọn 1 *anchor* (Top hoặc Dress).
  2. Với mỗi slot còn trống (`[BLANK_<category>]`), OT sinh query vector → search DB
     category đó → lấy Top-K, **Top-K sampling** (chọn ngẫu nhiên trong K để đa dạng).
  3. Beam Search (beam=3): giữ 3 nhánh tốt nhất mỗi bước.
  4. Rule category bắt buộc: `(1 top + 1 bottom + 1 shoes)` **hoặc** `(1 dress + 1 shoes)`;
     `outerwear / bag / accessory` optional.
- **30% — Random Sampling + OT Scoring** (bộ "phá cách, trendy"):
  - Ghép ngẫu nhiên theo rule category, để OT chấm điểm lọc.
  - **Pre-filter:** thay vì ngưỡng CLIP 0.4 (sai khái niệm — CLIP đo *độ giống*, không
    đo *độ hợp*), dùng rule category + một vòng OT scoring rẻ để loại combo "thảm họa".

**Bước 4 — Re-scoring (BẮT BUỘC cho cả 2 phương pháp).** Mọi outfit cuối đều được OT chấm
lại `compatibility_score`. FITB greedy/beam chỉ tối ưu *cục bộ từng bước* → không đảm bảo
hài hòa toàn cục; phải re-score. Chỉ giữ outfit có `score ≥ ngưỡng` (chốt ngưỡng ở Sprint 3
dựa phân phối điểm thực tế).

**Bước 5 — LLM Metadata Enrichment.** OT chỉ cho điểm + vector, không biết outfit này hợp
dịp nào. Dùng **Gemini Flash** (không phải GPT-4o/Qwen-72B — rẻ hơn, đã có hạ tầng
`diskcache` trong dự án) gán nhãn cho outfit qua ảnh các item:

```text
Bạn là Stylist chuyên nghiệp tại Việt Nam. Phân tích bộ trang phục (các ảnh item)
và trả JSON đúng format. Các trường occasion/style/body_shapes_fit/season PHẢI
chọn từ danh sách enum cho sẵn (không tự bịa giá trị mới):
  occasion: [office, interview, school, date, cafe_hangout, party, wedding, home_casual, travel]
  style:    [minimalist, korean, streetwear, elegant, casual, vintage, sporty, feminine]
  body_shapes_fit: [pear, apple, hourglass, rectangle, inverted_triangle]
  season:   [summer, transitional, winter, rainy]
{
  "occasion": [...], "style": [...], "body_shapes_fit": [...],
  "season": [...], "color_palette": [...],
  "stylist_explanation_vi": "..."
}
```

Chỉ tag outfit có `compatibility_score` qua ngưỡng → tiết kiệm chi phí API.
**Validate output:** mọi giá trị enum trả về phải nằm trong `vocab.py`, nếu không → log
warning + bỏ qua giá trị lạ (không để giá trị rác lọt vào KB).

**Bước 6 — Lưu KB** vào Parquet + index lên Qdrant (Phần 5).

### 3.5 Lưu ý kỹ thuật về OutfitTransformer-labse

- Checkpoint: [`fkuyumcu/OutfitTransformer-labse`](https://huggingface.co/fkuyumcu/OutfitTransformer-labse)
  — kiến trúc custom `outfit-cir-transformer`, cần `trust_remote_code=True`.
- Tag `complementary-item-retrieval` → **có hỗ trợ FITB/CIR** (xác nhận khả thi cho Bước 3).
- **Rủi ro domain shift:** checkpoint train trên **Polyvore (thời trang Tây), ngôn ngữ
  en/tr** — chưa thấy tiếng Việt / thời trang Á. Điểm compatibility trên item VN mang
  "gu Tây". Chấp nhận cho MVP, ghi nhận là hạn chế đã biết (xem Phần 10).
- **Xác minh trước khi code:** dim của `item_embedding` / `outfit_embedding` — **không
  giả định 768**. Đọc config checkpoint ở Sprint 1, đặt thành biến config cho Qdrant.

### 3.6 OT cho grading (tách biệt với việc build KB)

OT dùng **frozen** để build KB. Nhưng để báo cáo **FITB accuracy** & **Compatibility AUC**
(tiêu chí chấm điểm), v3.1-lite cho phép **fine-tune nhẹ OT trên Polyvore** (FITB/compat
chuẩn — *không* liên quan token `[OCC]`/`[PREF]`). Đây là phương án cứu grading nếu
checkpoint zero-shot không đạt target. Việc fine-tune này độc lập, không ảnh hưởng KB đã build.

---

## 🤖 Phần 4: Tầng 2 — Conversational Stylist (Qwen3-VL-8B)

### 4.1 Model & 4 vai trò

**Model:** `Qwen/Qwen3-VL-8B-Instruct` (kiến trúc `qwen3_vl`) + **LoRA nhẹ**.

| Vai trò | Mô tả |
|---|---|
| Intent Parser | "Em cao 1m60 nặng 55kg" → `{height:160, weight:55}` |
| Body Analyzer | Ảnh (nếu có) → ước lượng `body_shape` *thận trọng* — xem 4.4 |
| Conversational Agent | Hỏi lại khi thiếu thông tin (occasion, budget, style) |
| Outfit Explainer | Giải thích lý do recommend, cá nhân hóa |

### 4.2 Fine-tuning (LoRA nhẹ)

- **Dữ liệu:** 3–5K hội thoại synthetic, sinh bằng Gemini theo 7 loại mẫu (hỏi lại / phân
  tích ảnh / recommend+giải thích / từ chối lịch sự / multi-turn / edge case / tool-calling).
  Spot-check chất lượng thủ công ~5%.
- **Chấp nhận:** reasoning MVP yếu hơn bản full-finetune 100K của v3.0 — đánh đổi để kịp
  timeline. Vẫn đủ để báo cáo môn học có "phần fine-tune".

```python
from transformers import Qwen3VLForConditionalGeneration   # KHÔNG phải Qwen2VL...
from peft import LoraConfig, get_peft_model

model = Qwen3VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen3-VL-8B-Instruct", torch_dtype="bfloat16", device_map="auto",
)
lora_config = LoraConfig(
    r=16, lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
# TrainingArguments: dùng `eval_strategy` (tên mới), KHÔNG `evaluation_strategy`
```

**Deploy:** quantize 4-bit (`BitsAndBytesConfig`, nf4) qua đúng class VL
(`Qwen3VLForConditionalGeneration`, *không* `AutoModelForCausalLM`) → ~8GB VRAM cho demo.

### 4.3 Tool-calling — chống hallucination

Định nghĩa `search_outfits` với **tham số dùng đúng enum `vocab.py`**:

```python
search_outfits_tool = {
  "type": "function",
  "function": {
    "name": "search_outfits",
    "description": "Tìm outfit phù hợp từ Knowledge Base",
    "parameters": {
      "type": "object",
      "properties": {
        "occasion":   {"type": "string", "enum": [...OCCASION...]},
        "style":      {"type": "string", "enum": [...STYLE...]},
        "body_shape": {"type": "string", "enum": [...BODY_SHAPE...]},
        "skin_tone":  {"type": "string", "enum": [...SKIN_TONE...]},
        "price_max":  {"type": "integer", "description": "Ngân sách tối đa (VND)"},
        "exclude_colors": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["occasion"]
    }
  }
}
```

**Validation layer (bắt buộc):** sau khi Qwen sinh response, trích mọi `outfit_id` và
kiểm tra tồn tại trong KB. Nếu có id "bịa" → không hiển thị, trả message xin lỗi + search lại.

```python
def validate_response(response, valid_outfit_ids):
    ids = extract_outfit_ids(response)
    invalid = [i for i in ids if i not in valid_outfit_ids]
    return (len(invalid) == 0), invalid
```

### 4.4 Body analysis — thận trọng

- **Body shape:** ưu tiên suy từ `height/weight` (+ số đo nếu user nhập) hoặc quiz.
  Ảnh selfie thường chỉ có mặt/nửa người → **không đủ** để xác định pear/apple/hourglass;
  chỉ coi ảnh là tín hiệu phụ.
- **Skin tone:** cho user **tự chọn từ bảng màu** (`warm/neutral/cool`) thay vì để AI đoán
  từ ảnh — tránh sai do ánh sáng và tránh vấn đề bias/quyền riêng tư (xem Phần 10, Rủi ro 5).

---

## 🔍 Phần 5: Tầng 3 — Retrieval Engine (RAG)

### 5.1 Qdrant

Collection `outfits`. Payload index trên các trường filter nhanh:
`occasion`, `style`, `body_shapes_fit`, `price_tier`, `season`, `has_vn_store`.

```python
qdrant.create_collection(
    collection_name="outfits",
    vectors_config=models.VectorParams(
        size=OUTFIT_EMBED_DIM,            # xác minh từ checkpoint — KHÔNG hardcode 768
        distance=models.Distance.COSINE,
    ),
)
for field in ["occasion", "style", "body_shapes_fit", "price_tier", "season", "has_vn_store"]:
    qdrant.create_payload_index("outfits", field, models.PayloadSchemaType.KEYWORD)
```

### 5.2 Retrieval = Filter trước, Sort sau

> v3.0 dùng `query_vector=user_embedding` nhưng **chưa định nghĩa** `user_embedding` map
> vào không gian outfit-embedding thế nào. v3.1-lite bỏ lỗ hổng này:

**Quy trình:**
1. Qwen3-VL gọi `search_outfits(occasion, style, body_shape, price_max, exclude_colors)`.
2. Qdrant **filter** theo metadata (occasion, style, body_shape, price_tier, `has_vn_store=true`,
   loại `exclude_colors`).
3. **Sort** kết quả theo `compatibility_score` precomputed (giảm dần) + diversity penalty.
4. Trả Top ~30–50 outfit → Tầng 4 re-rank.

MVP **không cần vector search mơ hồ** — filter + sort theo điểm precomputed là đủ, trung
thực và dễ debug. (Vector search outfit-outfit có thể bổ sung sau, xem Phụ lục A.)

---

## 🎯 Phần 6: Tầng 4 — Personalization (Quiz re-rank)

> GNN bị hoãn: MVP không có user thật → không có lịch sử tương tác để GNN học.
> Train GNN trên interaction bịa là logic vòng tròn. GNN đầy đủ → Phụ lục A.

**MVP — cold-start bằng quiz:**
1. **Onboarding quiz 5 câu:** style yêu thích / dịp mặc thường xuyên / 3 màu ưa thích /
   ngân sách / chiều cao-cân nặng.
2. Map câu trả lời → **preference profile** (style ưu tiên, màu ưu tiên, `price_tier`).
3. **Re-rank rule-based:** outfit nào khớp style/màu/budget từ quiz được cộng điểm; sort lại
   Top ~30–50 → Top 3–5.
4. **Feedback (like/skip/mua)** được *lưu lại* phục vụ GNN tương lai, nhưng MVP chưa dùng.

---

## 🔄 Phần 7: Pipeline Inference E2E

```
Step 1  User nhập text + (optional) ảnh + đã làm quiz onboarding
          ↓
Step 2  Qwen3-VL parse → {height, weight, skin_tone, occasion, style, missing_info[]}
          ↓
Step 3  [Đủ info?] ──No──▶ Qwen hỏi lại (quay lại Step 1)
          │ Yes
          ↓
Step 4  Qwen gọi tool search_outfits(filters)  →  Qdrant filter + sort  →  30–50 outfit
          ↓
Step 5  Tầng 4: re-rank theo preference từ quiz  →  Top 3–5
          ↓
Step 6  Validation layer check outfit_id  →  Qwen3-VL sinh giải thích cá nhân hóa
          ↓
Step 7  Hiển thị (ảnh + store + giá + link) + ghi nhận feedback
```

---

## 📊 Phần 8: Mapping vào Rubric chấm điểm

Tham chiếu `docs/ARCHITECTURE.md §9`.

| Metric (DoD) | v3.1-lite đo thế nào | Trạng thái |
|---|---|---|
| Recall@5 (retrieval) | encoder retrieval eval | ✅ Đo được |
| FITB accuracy ≥ 55% | OT-labse eval trên **Polyvore**; fine-tune nhẹ nếu chưa đạt | ✅ Có phương án cứu (Phần 3.6) |
| Compatibility AUC ≥ 0.85 | OT-labse eval trên **Polyvore**; fine-tune nhẹ nếu chưa đạt | ✅ Có phương án cứu (Phần 3.6) |
| Body-cond. Precision@5 +10% | Ablation bật/tắt filter `body_shape` ở Tầng 3 | ✅ Đo được |
| E2E latency | **Đổi target:** chạy trên **GPU / cloud API**, cho phép nới nhẹ thời gian (mục tiêu ~<5–8s, ưu tiên streaming UX) | ⚠️ Cần xác nhận lại với giảng viên |
| LLM-as-judge (Gemini) ≥ 3.5/5 | Gemini chấm output E2E | ✅ Đo được |

**Ablations bắt buộc:** (1) encoder variants; (2) body conditioning on/off; (3) occasion
conditioning on/off; (4) greedy vs beam decoding (đã có sẵn trong pipeline build KB Phần 3.4).

> **Lưu ý latency:** Qwen3-VL-8B **không thể** đạt <3s trên CPU (cỡ vài phút). Đã thống
> nhất chuyển sang đo trên GPU/cloud và cho phép nới thời gian — cần chốt lại con số mục
> tiêu với giảng viên ở Sprint 0.

---

## 🗓️ Phần 9: Roadmap 10 tuần (Sprint 0–9, 3 dev)

Phân vai gợi ý: **Dev A** = Data/KB (Tầng 1), **Dev B** = Model/Stylist (Tầng 2),
**Dev C** = Retrieval/Infra/UI (Tầng 3, 4, API, demo).

| Sprint | Tuần | Nội dung chính | DoD |
|---|---|---|---|
| 0 | 1 | Setup; chốt `vocab.py`; **spike thu thập data** → chốt số item thực tế; xác nhận target latency với giảng viên | Repo chạy `make demo`; vocab.py merged |
| 1–2 | 2–3 | Tầng 1: crawl store VN + normalize + trích item embedding; xác minh dim checkpoint | Catalog VN sạch; embedding lưu Parquet |
| 3–4 | 4–5 | Tầng 1: sinh KB (FITB+Beam, random+score, **re-score**) + Gemini tagging; (song song) OT fine-tune Polyvore | KB 5–20K outfit có nhãn enum hợp lệ |
| 5 | 6 | Tầng 3: index Qdrant + retrieval filter+sort; đo Recall@5 | `/search` hoạt động; Recall@5 đạt target |
| 6–7 | 7–8 | Tầng 2: sinh 3–5K convs + LoRA Qwen3-VL + tool-calling + validation layer | Qwen gọi tool đúng; 0 hallucination lọt validation |
| 8 | 9 | Tầng 4: quiz + re-rank; ráp pipeline E2E; FastAPI + Gradio | `/recommend` E2E chạy; demo Gradio |
| 9 | 10 | Eval (LLM-judge, 4 ablations); polish; báo cáo; demo cuối | Mọi metric đo xong; báo cáo nộp |

*Roadmap này là bản phác — sẽ được chi tiết hóa thành kế hoạch task ở bước writing-plans.*

---

## ⚠️ Phần 10: Rủi ro & Giải pháp

| # | Rủi ro | Giải pháp |
|---|---|---|
| 1 | Qwen-VL "bịa" outfit không có trong KB | Bắt buộc tool-calling (chỉ output `outfit_id`); **validation layer** check id; fallback message xin lỗi |
| 2 | Data store VN ít, mô tả nghèo, ảnh lộn xộn | Auto-caption ảnh bằng VLM; ưu tiên store có ảnh per-item sạch; **spike Sprint 0** để chốt quy mô thực tế trước khi cam kết KB size |
| 3 | OT-labse domain shift (Polyvore Tây → item VN) | Chấp nhận cho MVP, ghi nhận là hạn chế; cân nhắc fine-tune OT trên data Á ở Phụ lục A |
| 4 | Vocabulary mismatch (lỗi v3.0) | **Đã sửa tận gốc:** `vocab.py` là nguồn enum duy nhất; LLM-tagging có validate enum |
| 5 | Bias theo body type; rủi ro privacy khi đoán skin tone từ ảnh | Skin tone cho user **tự chọn**; thu thập data đa dạng body type; cho phép user report "không hợp dáng tôi" |
| 6 | Latency cao (VLM trong hot path) | Chạy GPU/cloud; quantize 4-bit; **streaming response**; cache query phổ biến |
| 7 | KB size không đạt do data VN hạn chế | KB size để **dạng range linh hoạt 5–20K**, không chốt cứng; chất lượng ưu tiên hơn số lượng |

---

## 📎 Phụ lục A: Tầm nhìn 6 tháng (kế thừa v3.0)

Các hạng mục dưới đây **bị hoãn khỏi MVP** nhưng là hướng phát triển sau khi sản phẩm
deploy thật và có user. Chi tiết đầy đủ giữ trong `Kien_truc_v3.md`.

| Hạng mục | Nội dung hoãn |
|---|---|
| **KB quy mô lớn** | Mở rộng lên 100K–500K outfit; thêm nguồn Musinsa/ZOZOTOWN/Taobao/YesStyle + pipeline segmentation ảnh outfit nguyên bộ từ Pinterest/IG |
| **Token huấn luyện** | Train OutfitTransformer với token `[CLS][BODY][OCC][PREF×N][item×N]` (conditional Bradley-Terry) để KB occasion/style-aware từ gốc — schema v3.1 đã mở sẵn cho việc này |
| **Full fine-tune Qwen** | Qwen3-VL-8B/32B fine-tune trên 50K–100K hội thoại chất lượng cao; có thể distillation từ model lớn |
| **Tầng 4 GNN** | LightGCN/GraphSAGE/GAT personalization khi đã có ≥10K user với lịch sử tương tác thật; đồ thị User–Outfit–Item; cold-start qua quiz đã có ở MVP |
| **Tối ưu deploy** | Model distillation (Qwen3-VL-4B), caching nâng cao, async search/re-rank |

---

*Hết — v3.1-lite. Đây là tài liệu kiến trúc canonical duy nhất của dự án.
Toàn bộ tham vọng đầy đủ của bản v3.0 đã được tổng hợp vào Phụ lục A bên trên.*
