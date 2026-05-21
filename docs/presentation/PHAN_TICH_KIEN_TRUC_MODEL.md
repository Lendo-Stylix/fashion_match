# OutfitMatch — Phân tích Kiến trúc Model (Tài liệu thuyết trình 30 phút)

> **Môn:** DPL302m — Deep Learning · **Dự án:** OutfitMatch — Body & Occasion-Aware Fashion Recommender
> **Phương pháp luận:** Scrum (sprint 1 tuần) + XP practices · **Đối tượng:** Hội đồng chấm môn Deep Learning
> Tài liệu phân tích từ tầng kiến trúc tổng thể xuống tới tầng layer/tensor sâu nhất, cho cả 3 quá trình:
> **(1) Data Collection & Pre-processing — (2) Training — (3) Inference.**

---

## MỤC LỤC

0. Bối cảnh Scrum/XP — vì sao kiến trúc được thiết kế như vậy
1. Tổng quan hệ thống — bài toán & kiến trúc 6 tầng
1b. Related Work — 4 cụm paper nền + research gap
2. Data Collection & Pre-processing (tầng sâu nhất)
3. Training Pipeline (tầng sâu nhất)
4. Model Architecture — phân tích tới tầng layer/tensor
5. Inference Pipeline (tầng sâu nhất)
6. Evaluation, Ablation & Definition of Done
6b. Đo lường Performance từng tầng
7. Bản đồ Sprint ↔ Kiến trúc
8. Trạng thái hiện tại của code vs thiết kế (trung thực)
9. Kịch bản trình bày 30 phút

---

## 0. BỐI CẢNH SCRUM/XP — VÌ SAO KIẾN TRÚC ĐƯỢC THIẾT KẾ NHƯ VẬY

Toàn bộ kiến trúc OutfitMatch **không phải tự nhiên mà có** — nó là hệ quả trực tiếp của việc nhóm chọn **Scrum + XP** làm phương pháp luận. Khi trình bày, đây là "sợi chỉ đỏ" xuyên suốt: mỗi quyết định kiến trúc đều phục vụ một nguyên tắc Scrum/XP.

### 0.1 Ánh xạ Sprint → Tầng kiến trúc

Nhóm có 3 developer, 10 tuần, mỗi tuần là 1 sprint. Mỗi sprint giao đúng **một tầng kiến trúc** chạy được (incremental delivery). Vì vậy hệ thống được **cắt theo tầng (layer)** chứ không cắt theo file:

| Nguyên tắc Scrum/XP | Hệ quả lên kiến trúc |
|---|---|
| **Incremental delivery** — mỗi sprint phải có thứ chạy được | Hệ thống chia 6 tầng độc lập (Layer 0–5), mỗi tầng demo riêng được |
| **Simple design / YAGNI** | Body classifier dùng **rule-based** thay vì train CNN; không làm virtual try-on, không SMPL |
| **TDD** | `metrics/`, `config.py`, `data/` là **pure function / contract thuần** → test trước, code sau |
| **Collective ownership + pair programming** | Mọi tầng giao tiếp qua **interface ABC** (`BaseEncoder`, `BaseFashionDataset`) → 2 người hiểu 1 module |
| **Continuous Integration** | 1 CLI `om-exp run <config.yaml>` → reproducible, chạy được trên CI GitHub Actions |
| **Small releases / experiment cycles** | Mỗi sprint = **1 experiment cycle** quét lưới (grid) trên đúng 1 trục biến thiên |

### 0.2 Khái niệm cốt lõi: "Sprint = Experiment Cycle"

Đây là điểm sáng tạo của dự án và **nên nhấn mạnh khi thuyết trình**:

> Trong dự án DL bình thường, ta train một model rồi tinh chỉnh. Ở đây, **mỗi sprint là một thí nghiệm có kiểm soát (controlled experiment)**: quét một lưới cấu hình thay đổi *đúng một biến*, giữ nguyên mọi biến còn lại.

Mỗi thí nghiệm = **một file YAML** được nạp bởi `ExperimentConfig` (pydantic). Một CLI duy nhất `om-exp` chạy nó, log toàn bộ metric + config lên **Weights & Biases**. `wandb.group` = tên sprint, `wandb.job_type` = trục thí nghiệm → biểu đồ so sánh tự sinh.

**Triết lý kiểm thử kép (XP):**
- **Code hạ tầng (harness)** — `config`, `data`, `metrics`, `eval` — kiểm thử bằng **TDD / unit test** (≥70% coverage).
- **Model** — encoder, composer — **không** test bằng unit test (kết quả ngẫu nhiên), mà kiểm bằng **metric-gate**: phải vượt ngưỡng định trước (vd Recall@5 ≥ baseline + 5%) mới được sang sprint kế tiếp. Đây chính là "Definition of Done" cho kết quả ML.

---

## 1. TỔNG QUAN HỆ THỐNG

### 1.1 Bài toán

> **Input:** ảnh selfie người dùng (tùy chọn) + chiều cao + cân nặng + dịp (occasion) + câu mô tả phong cách (free-text).
> **Output:** Top 3–5 **bộ outfit** (mỗi bộ gồm nhiều item: áo, quần/váy, giày, phụ kiện) tương thích với **vóc dáng**, **dịp** và **sở thích** người dùng.

Đây là bài toán **Multimodal Deep Learning** giao của 3 lĩnh vực: Computer Vision (ảnh body + ảnh item), NLP (text prompt + caption), và Recommendation/Ranking (tổ hợp & xếp hạng outfit).

### 1.2 Kiến trúc 6 tầng (Layer 0 → Layer 5)

```
INPUT: ảnh selfie + (height, weight) + occasion + style prompt
   │
   ├─► LAYER 0  Preference Structuring   src/preference/
   │            prompt tự do → Gemini → StructuredPreference {hard, soft}
   │
   ├─► LAYER 1  Body Understanding       src/body/
   │            YOLO-pose → 17 keypoints → rule classifier → 5-class body shape
   │
   ▼
LAYER 2  Catalog Encoder                 src/encoders/
         Marqo/marqo-fashionSigLIP — ảnh & text → embedding L2-norm
   │
   ▼
LAYER 3  Vector Store / Retrieval        Qdrant (Docker :6333)
         ANN search + hard-constraint payload filter
   │
   ▼
LAYER 4  Outfit Composer                 src/train/composer.py
         OutfitTransformer — [CLS][item×N][BODY][OCC][PREF×K] → compatibility score
   │
   ▼
LAYER 5  Item Customization              POST /customize-item
         Qdrant filter + composer re-rank
   │
   ▼
OUTPUT: Top 3–5 outfit sets (item list + score + body_shape + occasion)
```

**Nguyên tắc bất biến (XP "Simple design"):** mỗi module có **đúng một trách nhiệm**, giao tiếp qua interface cố định. `data/` chỉ nạp dữ liệu, không gọi model. `encoders/` chỉ nhúng, không đọc dataset. `metrics/` là **pure function**, không I/O. Vi phạm ranh giới này phá vỡ tính tái lập (reproducibility) của thí nghiệm.

### 1.3 Vì sao 6 tầng mà không phải 1 model end-to-end?

| Lý do | Giải thích |
|---|---|
| **Scrum incremental** | Mỗi tầng giao trong 1 sprint, demo độc lập được |
| **Tái sử dụng SOTA** | Tầng 2 dùng encoder pretrained (fashionSigLIP 203M) — không train CV backbone từ đầu |
| **Tách dữ liệu huấn luyện** | Encoder cần cặp (ảnh, caption); composer cần outfit set — 2 dạng dữ liệu khác nhau, train riêng |
| **Khả năng debug** | Lỗi định vị được theo tầng — body sai vs encoder sai vs composer sai |

---

## 1b. RELATED WORK

> Phần này trả lời câu hỏi của hội đồng: *"Đã có ai làm vấn đề này chưa? Bạn khác họ ở chỗ nào?"*
> Nhóm chia related work thành **4 cụm** theo tầng kiến trúc — mỗi cụm gồm 2–3 paper nền, từ đó làm rõ **research gap** mà OutfitMatch lấp đầy.

---

### Cụm 1 — Vision-Language Encoders (nền tảng của Layer 2)

#### CLIP — Radford et al., OpenAI (2021)
> *"Learning Transferable Visual Models From Natural Language Supervision"*

Đây là **kiến trúc nền** của mọi encoder trong dự án. CLIP huấn luyện **dual-tower** (image ViT + text Transformer) trên 400M cặp (ảnh, caption) từ internet bằng **InfoNCE contrastive loss** (softmax chuẩn hóa toàn cục). Kết quả: embedding ảnh và văn bản chia sẻ cùng không gian vector — có thể tìm ảnh bằng query text và ngược lại.

**Giới hạn với bài toán fashion:** domain mismatch — CLIP không thấy đủ ảnh thời trang trong pre-training → Recall@5 thấp trên catalog chuyên biệt. Đây là lý do cần domain-specific encoder.

**Vai trò trong OutfitMatch:** baseline sàn (`openai/clip-vit-base-patch32`) — mọi encoder khác phải vượt qua CLIP-ZS.

---

#### SigLIP — Zhai et al., Google Research (2023)
> *"Sigmoid Loss for Language Image Pre-Training"* · arXiv:2303.15343

SigLIP thay InfoNCE softmax bằng **sigmoid loss thuần cặp** — thay vì chuẩn hóa toàn hàng/cột của ma trận similarity (CLIP), SigLIP coi mỗi cặp (i,j) là **bài toán binary classification độc lập**:

```
L = -mean( logsigmoid(z_ij · s_ij · t + b) )
z_ij = +1 nếu i=j (cặp đúng), −1 nếu i≠j
```

**Đóng góp kỹ thuật quan trọng:** không phụ thuộc vào batch size lớn như CLIP → huấn luyện được trên GPU hạn chế (Colab, Kaggle). Đây là lý do nhóm chọn SigLIP loss cho Component 1.

**Vai trò trong OutfitMatch:** hàm loss fine-tuning encoder (`src/train/contrastive.py`).

---

#### FashionCLIP — Chia et al. (2022)
> `patrickjohncyh/fashion-clip` · 109.5M downloads · MIT license

Fine-tune CLIP trên domain thời trang — tập dữ liệu kết hợp từ nhiều nguồn retail. Cải thiện đáng kể Recall@K trên fashion retrieval so với CLIP vanilla.

**Vai trò trong OutfitMatch:** ablation baseline 2 (FashionCLIP-ZS) trong thí nghiệm encoder axis.

---

#### Marqo fashionSigLIP — Marqo (2023–2024)
> `Marqo/marqo-fashionSigLIP` · 203M params · 8.4M downloads · Apache-2.0

Huấn luyện với **Generalised Contrastive Learning** trên **7 fashion dataset** chuyên biệt (DeepFashion, Polyvore, fashion200k, ...) bằng SigLIP loss. Hiện là SOTA trên fashion retrieval benchmark.

**Đây là encoder PRIMARY** của OutfitMatch — được chọn vì: (1) SigLIP loss khớp với kế hoạch fine-tune, (2) Apache-2.0 cho phép dùng thương mại, (3) performance tốt nhất trong họ fashion encoder.

---

### Cụm 2 — Outfit Compatibility & Composition (nền tảng của Layer 4)

#### Bi-LSTM Compatibility — Han et al. (ACM MM 2017)
> *"Learning Fashion Compatibility with Bidirectional LSTMs"*

Model đầu tiên học **compatibility** giữa các item thời trang. Encode mỗi item thành vector, dùng **Bi-LSTM** xử lý outfit như một chuỗi → output compatibility score. Giới thiệu **Polyvore dataset** (68K outfits, 365K items) và task FITB.

**Giới hạn:** LSTM coi outfit là chuỗi có thứ tự → nhạy cảm với thứ tự item, trong khi outfit thực tế là một **tập hợp** (set). Không có conditioning theo body shape hay occasion.

**Vai trò trong OutfitMatch:** baseline B2 (FashionSigLIP-ZS + Bi-LSTM) để đo hiệu quả của OutfitTransformer.

---

#### Type-Aware Embedding — Vasileva et al. (ECCV 2018)
> *"Learning Type-Aware Embeddings for Fashion Compatibility"*

Mở rộng Polyvore dataset thành **disjoint** (item không trùng train/test → khó) và **nondisjoint** (dễ hơn). Đề xuất type-aware embedding — mỗi cặp item type (áo + quần, giày + túi) học một projection riêng.

**Đóng góp quan trọng nhất với OutfitMatch:** định nghĩa chính xác task FITB và Compatibility, splits, và metric — OutfitMatch thừa kế trực tiếp.

**Vai trò trong OutfitMatch:** nguồn dataset `owj0421/polyvore-outfits` dùng cho Component 3 & 4.

---

#### OutfitTransformer — Sarkar et al. (2022)
> *"OutfitTransformer: Outfit Representations for Fashion Recommendation"* · arXiv:2204.04812

**Kiến trúc tham chiếu trực tiếp** của Layer 4. Đề xuất dùng **Transformer Encoder (Set Transformer)** thay Bi-LSTM cho outfit compatibility:
- Token `[CLS]` tổng hợp toàn outfit.
- Item tokens được xử lý **song song** (không tuần tự) → permutation-invariant.
- SOTA trên Polyvore FITB và compatibility.

**Điểm OutfitTransformer gốc chưa làm:** không có token điều kiện theo body shape (`[BODY]`), occasion (`[OCC]`), hay sở thích cá nhân (`[PREF]`).

**Vai trò trong OutfitMatch:** tái hiện toàn bộ kiến trúc + **mở rộng** bằng 3 loại conditioning token mới — đây là **đóng góp chính của dự án về kiến trúc**.

---

### Cụm 3 — Body-Aware Fashion (nền tảng của Layer 1)

#### ViBE — Hsiao & Grauman (CVPR 2020)
> *"ViBE: Dressing for Diverse Body Shapes"*

Bộ dữ liệu và phương pháp đầu tiên giải quyết **body shape diversity** trong fashion recommendation. Gán nhãn outfit theo 5 body shape (hourglass, pear, apple, rectangle, inverted triangle) + flattering score. Học embedding biết được body-aware compatibility.

**Giới hạn:** dataset gated (cần email tác giả), cần ảnh người thật có annotation → khó tái lập.

**Vai trò trong OutfitMatch:** truyền cảm hứng cho Sprint 6 "ViBE-style body-aware conditioning". Thay vì dùng dataset ViBE, nhóm **dẫn xuất body shape từ pose keypoint** (rule-based) — không cần dataset labeled.

---

#### YOLOv8-pose — Ultralytics (2023)
> `ultralytics` pip package · YOLOv8n-pose.pt · COCO-17 keypoint format

Real-time pose estimation, output 17 keypoints theo chuẩn COCO. Nhẹ (nano variant), chạy tốt trên CPU.

**Lý do chọn thay mediapipe:** `mediapipe` **không có wheel cho Python 3.13** — đây là ràng buộc cứng của môi trường. `ultralytics` là lựa chọn duy nhất khả thi.

**Vai trò trong OutfitMatch:** PoseExtractor trong Layer 1, dẫn xuất body shape.

---

### Cụm 4 — Preference Learning & Ranking (nền tảng của Layer 0 + Component 4)

#### Bradley-Terry Model — Bradley & Terry (1952)
> *"Rank Analysis of Incomplete Block Designs"* · Biometrika

Model thống kê cổ điển cho **pairwise comparison**: xác suất item A "thắng" B khi so sánh đôi:
```
P(A ≻ B) = σ(s_A − s_B)  [sigmoid]
```
Tối ưu bằng negative log-likelihood: `L = −log σ(s_A − s_B)`.

**Vì sao Bradley-Terry phù hợp hơn cross-entropy bình thường:** không cần nhãn tuyệt đối ("outfit này đẹp điểm 4/5") mà chỉ cần **so sánh tương đối** ("outfit A phù hợp hơn B với instruction X") — dữ liệu dễ thu thập, annotation ít tốn kém.

**Vai trò trong OutfitMatch:** `pairwise_bt_loss` trong Component 4, "conditional" vì cả hai forward pass dùng chung token `[PREF]`.

---

#### RLHF / InstructGPT — Ouyang et al., OpenAI (2022)
> *"Training language models to follow instructions with human feedback"* · NeurIPS 2022

Dùng **Bradley-Terry pairwise preference** + RL để align LLM với sở thích người dùng. Điểm chung với OutfitMatch: (1) thu thập preference triplets, (2) dùng pairwise loss để rank, (3) "conditional" — rank thay đổi theo context (instruction).

**Điểm khác:** OutfitMatch không dùng RL — chỉ dùng **supervised preference post-training** (đơn giản hơn, phù hợp với quy mô dự án). Nhưng ý tưởng "instruction-conditional ranking" là tương đồng trực tiếp.

**Vai trò trong OutfitMatch:** cung cấp framework tư duy cho Layer 0 (PromptStructurer → soft preference → conditioning token) và Component 4.

---

### 1b.x Research Gap — OutfitMatch lấp đầy gì?

Bảng sau tóm tắt capability của từng hướng tiếp cận — để slide "motivation" rõ ràng khi thuyết trình:

| Capability | CLIP-ZS | FashionSigLIP | Bi-LSTM (2017) | OutfitTransformer (2022) | **OutfitMatch** |
|---|:---:|:---:|:---:|:---:|:---:|
| Fashion-domain retrieval | ✗ | ✓ | — | — | ✓ (fine-tuned) |
| Outfit compatibility scoring | ✗ | ✗ | ✓ | ✓ | ✓ |
| Set-invariant (permutation) | — | — | ✗ | ✓ | ✓ |
| Body shape conditioning | ✗ | ✗ | ✗ | ✗ | **✓** |
| Occasion conditioning | ✗ | ✗ | ✗ | ✗ | **✓** |
| Free-text preference (soft) | ✗ | ✗ | ✗ | ✗ | **✓** |
| Hard constraint filter | ✗ | ✗ | ✗ | ✗ | **✓** |
| E2E latency < 3s CPU | — | — | — | — | **✓ (target)** |

**Thông điệp khi trình bày:** "Không có một hệ thống nào trước đây tích hợp đồng thời body conditioning + occasion conditioning + free-text preference vào cùng một kiến trúc Transformer. Đây là đóng góp chính."

---

## 2. DATA COLLECTION & PRE-PROCESSING (TẦNG SÂU NHẤT)

Pipeline dữ liệu gồm **7 giai đoạn (stage)**, từ nguồn thô → tensor sẵn sàng huấn luyện. Mỗi stage có input/output/dependency rõ ràng — đây là "định nghĩa Done" của data theo XP.

### 2.1 Stage 1 — Catalog Ingest & Validate (thu thập & kiểm định catalog)

**Nguồn dữ liệu** (open-source, đa dạng để chống bias):

| Nguồn | Dataset HF | Rows | Dung lượng | Vai trò |
|---|---|---:|---:|---|
| HuggingFace | `Marqo/deepfashion-inshop` | 52.6K | 216 MB | Studio white-bg, chất lượng cao |
| HuggingFace | `Marqo/deepfashion-multimodal` | 42.5K | 153 MB | Có caption giàu thuộc tính |
| HuggingFace | `Marqo/fashion200k` | 201.6K | 3.5 GB | Web-scraped, tín hiệu fine-tune quy mô lớn |
| Custom | Thu thập thủ công | tùy | — | Bổ sung diversity |

**Chuẩn hóa về một schema chung** `catalog_metadata.parquet`:

| Cột | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `item_ID` | string | ✅ | Không trùng lặp |
| `image_path` | string | ✅ | File phải tồn tại |
| `text` | string | ✅ | Độ dài 10–200 ký tự |
| `category1` | enum 7 giá trị | ✅ | `tops·bottoms·dresses·outerwear·shoes·bags·accessories` |
| `category2/3` | string | category2 ✅ | Phân loại tinh hơn |
| `color`, `source`, `split` | string/enum | source,split ✅ | `split` ∈ {train, val, test} |

**Kiểm định (XP — "test data như test code"):** `scripts/validate_custom_data.py --phase 1B` kiểm tra: mọi `image_path` tồn tại, `category1` hợp lệ, độ dài `text`, không trùng `item_ID`, và in **distribution report** theo category. Có **target distribution** ép mỗi nhóm chiếm tỉ lệ tối thiểu (tops ≥20%, dresses ≥15%, accessories ≥5%...) — đây là **biện pháp chống bias dữ liệu ngay từ tầng thu thập**.

### 2.2 Stage 2 — Encoder Fine-tuning Data Prep

Tạo **cặp anchor/positive** cho contrastive learning:
- **anchor** = ảnh item · **positive** = caption của *cùng item* · **negative** = các item khác *trong cùng batch* (in-batch negatives — không cần sinh trước).

**Pre-processing ảnh (chỉ tập train):**
```
RandomHorizontalFlip(p=0.5)
ColorJitter(brightness=0.2, contrast=0.2)
RandomCrop(scale=(0.85, 1.0))
→ Resize 224×224
→ Normalize theo mean/std của ImageNet
```
`ColorJitter` còn dùng làm **skin-tone augmentation** (HSV shift) — biện pháp chống bias về dải màu da.

Output: `data/processed/encoder_ft/{train,val,test}.parquet`. Loader `RetrievalDataset` trả về dict `{image: PIL.Image, text: str, category: str, item_ID: str}` (hợp đồng schema cố định, xem §4.1).

### 2.3 Stage 3 — Embed + Index (nạp Qdrant)

Sau khi có encoder đã fine-tune (frozen, eval mode), batch-encode toàn bộ catalog → vector 768 chiều → **L2-normalize** → upsert vào Qdrant collection `catalog` (`size=768, distance=Cosine`). Payload đính kèm: `item_ID, category1, category2, color, body_shapes` — dùng cho **hard-constraint filter** ở inference.

### 2.4 Stage 4 — Outfit Compatibility Data Prep

Nguồn chính: **Polyvore** (`owj0421/polyvore-outfits`, 413.8K rows) — outfit do **stylist người thật** phối.

Dataset này ship sẵn các config ánh xạ 1:1 với metric của dự án:

| Config | Schema `__getitem__` | Phục vụ metric |
|---|---|---|
| `{disjoint,nondisjoint}_compatibility` | `{example_id, items: list[str], label: int∈{0,1}}` | Compatibility AUC |
| `{disjoint,nondisjoint}_fill_in_the_blank` | `{question: list[str], answers: list[str], label: int}` | FITB accuracy |

- **Positive** = outfit của stylist · **Negative** = thay ngẫu nhiên 1 item.
- **disjoint** (17K outfits, item không trùng giữa train/test → khó) vs **nondisjoint** (53K, dễ hơn) — *đây chính là trục thí nghiệm "dataset type"*.

### 2.5 Stage 5 — Occasion Labeling (Weak Supervision bằng Gemini)

Polyvore **không có nhãn occasion** → dùng **weak supervision**:
```
outfit_text = nối mô tả các item
prompt Gemini = "Outfit này phù hợp dịp nào? Chọn: casual/business/formal/sport/party/date"
→ occasion label
```
**Cache (diskcache):** key = `SHA256(EXTRACTOR_VERSION + outfit_description)` → tránh gọi lại API cho cùng outfit. Chi phí ước tính: ~50K calls × Gemini Flash ≈ **$5**, cache tiết kiệm ~95% khi chạy lại.

### 2.6 Stage 6 — Preference Triplet Generation (quan trọng nhất cho Layer 0)

Sinh `triplets.jsonl` cho post-training preference. Mỗi triplet:
```json
{"instruction": "I want a casual minimalist look",
 "body_shape": "pear",
 "pos_items": ["item_001","item_002","item_003"],
 "neg_items": ["item_010","item_011","item_012"]}
```

**Bất biến sống còn — "flip invariant ≥ 30%":** tối thiểu 30% cặp phải là **contrastive flip** — *cùng một cặp outfit*, *instruction đối nghịch*, *label bị lật*:
```
instruction A: "I prefer bright colors"  → pos > neg
instruction B: "I prefer neutral colors" → neg > pos   (label flipped)
```
**Vì sao bắt buộc:** nếu không có flip pairs, composer sẽ học cách *bỏ qua* token `[PREF]` (vì pos luôn > neg bất kể instruction) → ablation `use_pref` không cho thấy cải thiện. Flip pairs ép model học **phân biệt sở thích thực sự**, không memorize.

### 2.7 Stage 7 — Train/Val/Test Splits & chống rò rỉ (data leakage)

| Dataset | Train/Val/Test |
|---|---|
| Encoder FT | 80 / 10 / 10 |
| Outfit compat & FITB | Theo split gốc Polyvore |
| Preference triplets | 80 / 10 / 10 |

**Luật chống rò rỉ:**
1. **Item-level**: `item_ID` xuất hiện ở train thì không được ở test.
2. **Outfit-level**: một outfit set chỉ thuộc đúng 1 split.
3. **Preference**: một `instruction` không được copy giữa train và test.

**Version hóa dữ liệu:** dùng **DVC** + Google Drive remote. **Tuyệt đối không commit ảnh/data thẳng vào git** — mọi thứ trong `data/` đi qua DVC.

### 2.8 Đồ thị phụ thuộc giữa các stage

```
HF Sources → Stage 1 (Catalog Ingest)
                 ├──► Stage 2 (Encoder FT prep) ──► [Train Component 1]
                 ├──► Stage 3 (Embed+Index)  ←── cần encoder checkpoint
                 └──► Stage 4 (Outfit prep) ──► Stage 5 (Occasion) ──► Stage 6 (Triplet) ──► Stage 7 (Splits)
```

---

## 3. TRAINING PIPELINE (TẦNG SÂU NHẤT)

Training gồm **5 component học**, chạy **tuần tự theo phụ thuộc** (output bước trước = input bước sau). Component 5 (body) chạy song song độc lập.

```
[Catalog Data] ─► Component 1 (Encoder FT)
                       │
                       ▼
                Component 2 (Index Build)
                       │
                       ▼
            Component 3 (Composer Base Train)
                       │
            [Triplet Data] ─► Component 4 (Preference Post-train)

[Pose Data] ─► Component 5 (Body Classifier)    ← độc lập, song song
```

### 3.1 Component 1 — Catalog Encoder Fine-tuning

**Mục tiêu:** đưa `Marqo/marqo-fashionSigLIP` từ domain "thời trang chung" → domain "catalog cụ thể của dự án".

**Hàm mất mát — SigLIP Sigmoid Contrastive Loss** (Zhai et al. 2023, arXiv:2303.15343). Trích code thực tế `src/outfitmatch/train/contrastive.py`:

```python
def siglip_loss(img, txt, t=10.0, b=-10.0):
    img = F.normalize(img, dim=1)          # L2-normalize ảnh
    txt = F.normalize(txt, dim=1)          # L2-normalize text
    logits = (img @ txt.T) * t + b         # ma trận tương đồng (N×N), scale t, bias b
    n = img.size(0)
    labels = 2 * torch.eye(n) - 1          # +1 trên đường chéo, −1 ngoài đường chéo
    return -F.logsigmoid(labels * logits).mean()
```

**Phân tích toán học (tầng sâu nhất):**
- `s_ij = <image_i, text_j>` — độ tương đồng cosine (vì đã L2-norm) giữa ảnh `i` và caption `j`.
- `logits_ij = s_ij · t + b` với `t` là temperature, `b` là bias.
- Nhãn `z_ij = +1` nếu `i=j` (cặp đúng), `z_ij = −1` nếu `i≠j` (cặp sai).
- Loss mỗi cặp: `−log σ(z_ij · logits_ij)` — đây là **binary classification độc lập cho từng cặp** (i,j).

**Vì sao SigLIP thay vì CLIP softmax?**
- CLIP dùng softmax → cần **chuẩn hóa toàn cục theo cả hàng và cột** → cần batch lớn.
- SigLIP dùng **sigmoid trên từng cặp độc lập** → ổn định với **batch nhỏ** (rất hợp môi trường Colab/Kaggle GPU hạn chế — phù hợp risk register của nhóm).

**Quy trình fine-tune (progressive unfreezing):**
```
Khởi tạo từ fashionSigLIP → backbone đóng băng
  → unfreeze K transformer layer trên cùng dần dần
  → optimizer: AdamW (chỉ param có requires_grad=True)
  → mỗi step: encode ảnh + text trong batch → siglip_loss → backward → step
  → log train/loss lên W&B
  → đánh giá Recall@1/5/10 trên val set
```

**Metric gate (Definition of Done của Sprint 4):** `Recall@5 ≥ CLIP zero-shot + 5%` — **không đạt thì không được sang Component 2**.

### 3.2 Component 2 — Embedding Index Build

Encoder đã fine-tune (frozen, eval) → batch-encode catalog (batch 256) → vector 768-dim L2-norm → upsert Qdrant. Đây là cầu nối giữa training và inference: model trở thành **index tra cứu được**.

### 3.3 Component 3 — OutfitTransformer Base Training

**Mục tiêu:** dạy OutfitTransformer chấm điểm tương thích (compatibility) của một bộ outfit.

**Phụ thuộc:** cần item embeddings từ encoder đã fine-tune (Component 1) — **encoder bị đóng băng** trong suốt Component 3.

**Quy trình:**
```
Encoder frozen → encode items → item_embeds (B, N, D)
   │
   ▼
OutfitTransformer forward: [CLS] + [item×N] + [BODY]? + [OCC]?
   │
   ▼
Conditional Bradley-Terry pairwise loss:  L = −log σ(score_pos − score_neg)
   │
   ▼
Đánh giá: FITB accuracy + Compatibility AUC
```

**Metric gates:** FITB ≥ 55% · Compatibility AUC ≥ 0.85 · Body-conditional Precision@5 ≥ +10% so với baseline không điều kiện.

### 3.4 Component 4 — Preference Post-training (Layer 0 nâng cao — Sprint 9)

**Mục tiêu:** dạy OutfitTransformer **phản hồi theo token sở thích** `[PREF_style]`, `[PREF_color]`, `[PREF_fit]`.

**Quy trình (trích `train_preference()` thực tế):**
```
Encoder frozen
   │
   ▼ structurer.structure(instruction, body_shape) → StructuredPreference {hard, soft}
   │  với mỗi nhóm soft đang active → encoder.encode_text(phrase) → vector → pref_dict[group]
   │
   ▼ s_pos = composer(pos_items, pos_mask, pref=pref_dict)
   ▼ s_neg = composer(neg_items, neg_mask, pref=pref_dict)
   │
   ▼ loss = pairwise_bt_loss(s_pos, s_neg) = −log σ(s_pos − s_neg)
   │
   ▼ Eval: preference_pairwise_accuracy + instruction_flip_consistency
```

**Conditional Bradley-Terry — phân tích toán học:** Bradley-Terry model về xác suất outfit A "thắng" B: `P(A ≻ B) = σ(s_A − s_B)`. "Conditional" nghĩa là **cả hai forward pass dùng chung một bộ token `[PREF]`** → model học xếp hạng *dưới điều kiện instruction đó*. Tối thiểu hóa `−log σ(s_pos − s_neg)` ⇔ tối đa hóa xác suất outfit người dùng thích được chấm cao hơn.

**Metric gates:** preference_pairwise_accuracy ≥ 0.65 · instruction_flip_consistency ≥ 0.30.

### 3.5 Component 5 — Body Shape Classifier (rule-based, độc lập)

**Quyết định XP "Simple design / YAGNI":** không train CNN — dùng **rule-based** trên tỉ lệ keypoint. Lý do: không tồn tại dataset gán nhãn body-shape trên HuggingFace; rule-based đủ tốt cho MVP, kiểm bằng unit test thay vì train.

```
YOLO-pose → COCO-17 keypoints
   → keypoints_to_measures(): shoulder, hip width; waist = (shoulder+hip)/2·0.85 [proxy]
   → classify_body_shape() → 1 trong 5 lớp
```

### 3.6 Ba bất biến (INVARIANTS) bắt buộc của Training

| # | Bất biến | Hệ quả nếu vi phạm |
|---|---|---|
| **INV-1** | Encoder **đóng băng** trong Component 3 & 4 (`requires_grad=False`) | Feature collapse — embedding sụp đổ |
| **INV-2** | `EXTRACTOR_VERSION` **giống nhau** ở train (sinh triplet) và inference (structuring online) | Train/inference skew — model gặp phân phối khác lúc deploy |
| **INV-3** | Flip pairs ≥ 30% trong `triplets.jsonl` | Composer bỏ qua `[PREF]`, ablation không cho thấy gain |

### 3.7 Experiment Cycle — quét lưới một trục

Mỗi sprint quét lưới trên **đúng một trục**, cố định các trục còn lại:

| Trục | Biến thiên | Giữ cố định |
|---|---|---|
| Model | encoder kind/checkpoint | dataset=deepfashion-inshop, max_rows=5000 |
| Dataset type | hf_id + config | model=fashionSigLIP-ZS, max_rows=10000 |
| Rows (scaling) | max_rows ∈ {5K, 25K, 100K, all} | model=fashionSigLIP-FT, dataset=fashion200k |
| Conditioning | composer.use_body / use_occ | model=fashionSigLIP-ZS, dataset=polyvore-nondisjoint |

Lệnh chạy: `om-exp sweep configs/<axis>/ --out-csv docs/experiments/ablation_<axis>.csv`.
**Bất biến config:** `max_rows` là cách *duy nhất* thay đổi kích thước dataset — cấm hard-code logic cắt slice trong code model/trainer.

---

## 4. MODEL ARCHITECTURE — PHÂN TÍCH TỚI TẦNG LAYER/TENSOR

Đây là phần "deep" nhất — bóc tách từng model tới mức layer, tensor shape, công thức.

### 4.1 Layer 2 — Catalog Encoder (Fashion-SigLIP)

**Interface — `BaseEncoder` (ABC):** mọi encoder phải tuân hợp đồng:
```python
class BaseEncoder(ABC):
    embed_dim: int                                    # đặt trong __init__
    def encode_image(self, images: list[PIL.Image]) -> torch.Tensor   # (N, embed_dim) L2-norm
    def encode_text(self,  texts:  list[str])        -> torch.Tensor   # (N, embed_dim) L2-norm
```
Đây là điểm chốt cho **pair programming / collective ownership**: tầng trên chỉ cần biết interface, không cần biết bên trong là CLIP hay SigLIP. Có 2 hiện thực: `HfClipEncoder` (transformers — CLIP/FashionCLIP) và `OpenClipEncoder` (open_clip — FashionSigLIP). `build_encoder(ModelConfig)` là factory duy nhất được phép tạo encoder.

**Bên trong `HfClipEncoder` (kiến trúc dual-tower):**
```
Image tower: ViT  → get_image_features() → vector D-dim → chia chuẩn L2
Text  tower: Transformer → get_text_features() → vector D-dim → chia chuẩn L2
embed_dim = model.config.projection_dim   (CLIP-base = 512, fashion-clip = 512)
Cả 2 method bọc @torch.no_grad() lúc eval.
```

**Lưu ý kiến trúc quan trọng (nên nói khi thuyết trình):** `embed_dim` của encoder *quyết định* `embed_dim` của composer. fashionSigLIP xuất **768-dim**, CLIP baseline xuất **512-dim**. Trong `runner.py`, composer được khởi tạo bằng `OutfitTransformer(embed_dim=encoder.embed_dim, ...)` — tức **chiều của composer bám theo encoder**. Con số "d=512" trong tài liệu là default theo paper / trường hợp CLIP baseline.

**Các encoder so sánh (Ablation 1):**

| Model | Kiến trúc | Params | Vai trò |
|---|---|---:|---|
| `openai/clip-vit-base-patch32` | CLIP | 151M | Baseline sàn — mọi thí nghiệm phải vượt |
| `patrickjohncyh/fashion-clip` | CLIP domain | 151M | Ablation |
| `Marqo/marqo-fashionCLIP` | CLIP domain | 150M | Ablation |
| **`Marqo/marqo-fashionSigLIP`** | **SigLIP** | **203M** | **PRIMARY — fine-tune** |

### 4.2 Layer 4 — OutfitTransformer (model trọng tâm của dự án)

Đây là **đóng góp kiến trúc chính** — tham chiếu Sarkar et al. 2022 (arXiv:2204.04812). Toàn bộ model gói trong ~58 dòng `src/train/composer.py`. Phân tích từng dòng:

#### 4.2.1 Các thành phần (định nghĩa trong `__init__`)

| Thành phần | Kiểu | Shape | Vai trò |
|---|---|---|---|
| `self.cls` | `nn.Parameter` | `(1, 1, D)` | Token `[CLS]` học được — gom thông tin cả outfit |
| `self.body_proj` | `nn.Linear(D, D)` | — | Chiếu `body_vector` thành token `[BODY]` |
| `self.occ_proj` | `nn.Linear(D, D)` | — | Chiếu `occasion_vector` thành token `[OCC]` |
| `self.pref_proj` | `nn.ModuleDict` | mỗi nhóm 1 `Linear(D,D)` | Token `[PREF_style/color/fit]` riêng từng nhóm |
| `self.encoder` | `nn.TransformerEncoder` | 4 layer | Khối self-attention chính |
| `self.head` | `nn.Linear(D, 1)` | — | Token `[CLS]` đầu ra → 1 scalar điểm |

#### 4.2.2 Cấu hình khối Transformer (tầng sâu nhất)

`nn.TransformerEncoderLayer(d_model=D, nhead=8, dim_feedforward=D*4, batch_first=True)`, xếp chồng `num_layers=4`.

Với `D=512`, mỗi **TransformerEncoderLayer** gồm:
```
1. Multi-Head Self-Attention
   - 8 head, mỗi head có head_dim = 512/8 = 64
   - Q,K,V projection + output projection ≈ 4·D² ≈ 1.05M tham số
   - Residual connection + LayerNorm (post-LN — mặc định PyTorch)
2. Feed-Forward Network (position-wise)
   - Linear(512 → 2048) → ReLU → Linear(2048 → 512)
   - ≈ 2·D·4D ≈ 2.1M tham số
   - Residual connection + LayerNorm
```
→ Mỗi layer ≈ **3.15M params**, ×4 layer ≈ **12.6M**. Cộng `body_proj/occ_proj/pref_proj/head/cls` → tổng khoảng **~13–14M tham số** (tùy số nhóm pref). Đây là model **nhẹ** — chủ ý để đạt mục tiêu E2E latency < 3s trên CPU.

**Điểm tinh tế — KHÔNG có positional encoding:** một outfit là một **tập hợp (set)**, không phải chuỗi có thứ tự (áo + quần ≡ quần + áo). Vì vậy code cố tình **không** thêm positional embedding → model **bất biến hoán vị (permutation-invariant)** trên các item. Self-attention vốn permutation-equivariant; bỏ positional encoding biến nó thành **Set Transformer**. Đây là chi tiết kiến trúc đáng nhấn mạnh.

#### 4.2.3 `forward()` — xây dựng chuỗi token (phân tích từng bước)

Input: `item_embeds (B, N, D)`, `mask (B, N) bool`, tùy chọn `body (B, D)`, `occ (B, D)`, `pref {group: (B, D)}`.

```
Bước 1  toks = [ [CLS] mở rộng (B,1,D) ,  item_embeds (B,N,D) ]
        keep = [ ones(B,1)            ,  mask (B,N)           ]

Bước 2  Nếu có body:  toks += body_proj(body).unsqueeze(1)   → token [BODY]   keep += ones(B,1)
Bước 3  Nếu có occ :  toks += occ_proj(occ).unsqueeze(1)     → token [OCC]    keep += ones(B,1)
Bước 4  Nếu có pref:  với mỗi nhóm g: toks += pref_proj[g](vec)  → token [PREF_g]  keep += ones(B,1)

Bước 5  x   = cat(toks, dim=1)        → (B, L, D)   với L = 1 + N + [BODY?] + [OCC?] + K
        pad = ~cat(keep, dim=1)       → (B, L)      True = vị trí padding cần che

Bước 6  h = encoder(x, src_key_padding_mask=pad)    → self-attention 4 layer

Bước 7  return head(h[:, 0]).squeeze(-1)            → lấy token [CLS], chiếu về scalar (B,)
```

**Chuỗi token đầy đủ:**
```
[CLS]  [item_1] [item_2] ... [item_N]  [BODY]?  [OCC]?  [PREF_style]? [PREF_color]? [PREF_fit]?
  └── gom outfit      └── các item     └── điều kiện vóc dáng / dịp / sở thích (conditioning tokens)
```

**Vì sao "conditioning token" là ý tưởng hay?** Thay vì nối (concat) body/occasion vào từng item rồi chiếu lại, ta đưa chúng vào **như những token bình thường**. Self-attention cho phép **mọi item "nhìn thấy" và bị ảnh hưởng bởi** token `[BODY]`, `[OCC]`, `[PREF]`. Điều kiện hóa trở thành một phần tự nhiên của attention — đúng tinh thần kiến trúc Transformer.

**`src_key_padding_mask`** xử lý outfit có **số item khác nhau** (N biến thiên): vị trí padding bị che, attention bỏ qua chúng. `[CLS]/[BODY]/[OCC]/[PREF]` luôn `keep=True` (không bao giờ bị che).

**Output:** token `[CLS]` sau 4 layer attention → `Linear(D→1)` → **một scalar compatibility score** cho cả outfit. Đây chính là đại lượng được Bradley-Terry loss xếp hạng lúc train, và dùng để rank outfit lúc inference.

#### 4.2.4 Bảng ablation conditioning (Sprint 6)

| Config | `use_body` | `use_occ` | Token thêm vào |
|---|---|---|---|
| `cond_none` | ✗ | ✗ | (không) |
| `cond_body` | ✓ | ✗ | `[BODY]` |
| `cond_body_occ` | ✓ | ✓ | `[BODY]` + `[OCC]` |

→ So sánh trực tiếp tác dụng của body conditioning & occasion conditioning (ablation bắt buộc của môn).

### 4.3 Layer 1 — Body Understanding Pipeline

**Bước 1 — Pose extraction (`PoseExtractor`):** bọc `ultralytics` YOLOv8n-pose. Lazy-load model lần gọi đầu. `extract(image)` → mảng `(17, 2)` keypoint COCO-17, hoặc `None` nếu không phát hiện người.

> **Ràng buộc Python 3.13:** dùng `ultralytics` thay `mediapipe` vì mediapipe **không có wheel cho cp313**. Đây là một quyết định kỹ thuật bắt buộc, ghi trong CLAUDE.md.

**Bước 2 — Keypoints → số đo (`keypoints_to_measures`):**
```python
shoulder = ||kp[5] − kp[6]||      # khoảng cách L-shoulder ↔ R-shoulder (COCO idx 5,6)
hip      = ||kp[11] − kp[12]||    # khoảng cách L-hip ↔ R-hip      (COCO idx 11,12)
waist    = (shoulder + hip) / 2 · 0.85   # proxy — COCO không có keypoint eo
```

**Bước 3 — Rule classifier (`classify_body_shape`) — 5 lớp:**
```python
sh_hip      = shoulder / hip
waist_ratio = waist / max(shoulder, hip)

if waist ≥ shoulder và waist ≥ hip:  → "apple"
if sh_hip > 1.05:                    → "inverted_triangle"   (vai rộng hơn hông)
if sh_hip < 0.95:                    → "pear"                (hông rộng hơn vai)
# vai ≈ hông:
if waist_ratio ≤ 0.80:               → "hourglass"           (eo thắt rõ)
else:                                → "rectangle"
```
Output `body_shape: str` → ghép thành `body_vector` (512-dim) → đưa vào token `[BODY]` của composer, đồng thời là **giá trị fallback** cho hard-constraint filter (xem §4.4).

### 4.4 Layer 0 — Preference Structuring

**Mục tiêu:** biến câu mô tả phong cách tự do của người dùng → cấu trúc máy hiểu được.

`PromptStructurer.structure(instruction, body_shape)`:
```
1. key = SHA256(EXTRACTOR_VERSION | instruction)        → tra diskcache
2. Nếu miss: gọi Gemini với STRUCT_PROMPT → JSON → cache lại
3. Parse JSON → StructuredPreference (pydantic validate)
4. apply_body_fallback(pref, body_shape)
```

**Schema `StructuredPreference`:**
```
StructuredPreference
├── hard: HardConstraint    {colors_avoid, categories_exclude, materials_require, fit_bias, source}
└── soft: SoftPreference    {style, color, fit}   — mỗi trường là cụm từ ngắn ≤ 6 từ
```

**Routing (định tuyến — thiết kế đã chốt):**

| Loại | Định nghĩa | Đi vào tầng nào |
|---|---|---|
| **hard** | Ràng buộc người dùng **nói rõ** (tránh / loại / yêu cầu) | **Layer 3** — Qdrant **payload filter** |
| **soft** | Sở thích mềm | **Layer 4** — mỗi nhóm thành **một token `[PREF_<group>]`** riêng |

**Body fallback** (`apply_body_fallback`): nếu người dùng **không nêu hard constraint nào**, suy ra `fit_bias` từ body shape:
```
pear → structured_top   ·  apple → defined_waist   ·  hourglass → fitted
rectangle → add_curves  ·  inverted_triangle → volume_bottom
source = "body_fallback"
```
→ Hệ thống **luôn có** ràng buộc cứng để lọc, kể cả khi người dùng không nói gì.

**Lý do "N token riêng theo nhóm" thay vì 1 token gộp:** style/color/fit là 3 trục sở thích độc lập. Cho mỗi nhóm một token riêng → composer học attention riêng cho từng trục → ablation `pref_style_only` vs `pref_all_groups` đo được đóng góp từng nhóm.

---

## 5. INFERENCE PIPELINE (TẦNG SÂU NHẤT)

Mục tiêu vận hành: **E2E latency < 3 giây trên CPU**. Luồng 6 bước:

### Step 1 — Preference Structuring (Layer 0)
`instruction` → Gemini (qua cache) → `StructuredPreference {hard, soft}`. Xử lý thiếu thông tin: thiếu occasion → `soft.style="casual"`; không có ảnh → `body_shape=""`; `hard` rỗng → body fallback.

### Step 2 — Body Shape Extraction (Layer 1) — *chỉ khi có ảnh*
YOLO-pose → 17 keypoint → ratio → rule classifier → 1 trong 5 lớp body shape. Không detect được pose → `body_shape=""` (không áp body filter).
> **Quyết định privacy:** ảnh selfie chứa thông tin nhạy cảm → bước này **tùy chọn**, người dùng có quyền không cung cấp.

### Step 3 — Catalog Retrieval (Layer 2 + 3)
- **3a. Hard filter:** Qdrant payload filter (`categories_exclude`, `colors_avoid`, `body_shapes`).
- **3b. Semantic ANN search:** query text → fashionSigLIP encoder → vector 768-dim → Qdrant **cosine search** → candidate pool theo từng category slot (tops, bottoms, dresses, ...), top-K=50 mỗi slot.

### Step 4 — Outfit Composition + Scoring (Layer 4)
- 4a. Nhóm candidate theo category slot.
- 4b. Tổ hợp candidate set dựa trên **outfit templates** (VN / Châu Á / Âu / Global).
- 4c. **OutfitTransformer forward:** `[CLS][item×N][BODY][OCC][PREF×K]` → compatibility score mỗi outfit set.
- 4d. Rank & loại trùng (deduplicate) theo score.

### Step 5 — Customization (Layer 5) — *tùy chọn*
`POST /customize-item` khi người dùng muốn thay 1 item: Qdrant filter theo `target_attrs` + composer re-rank → danh sách item thay thế.

### Step 6 — Output
Top 3–5 outfit set, mỗi set: item list (ảnh + metadata) + compatibility score + body_shape đã dùng + occasion tag.

**Phân bổ ngân sách latency (ước lượng, mục tiêu < 3s CPU):**

| Bước | Thành phần nặng | Ước lượng |
|---|---|---|
| Step 1 | Gemini (cache hit ~0ms; miss ~300–800ms) | gần như 0 nếu cache |
| Step 2 | YOLO-pose inference | ~200–400 ms |
| Step 3 | encode query + ANN search | ~300–600 ms |
| Step 4 | OutfitTransformer forward (model nhẹ ~14M) | ~200–500 ms |
| **Tổng** | | **< 3 s** ✓ |

### API Endpoints
```
POST /recommend       {image_b64?, height?, weight?, occasion?, instruction?} → outfits + latency_ms
POST /search          {query_text}                                           → top-K items
POST /customize-item  {outfit_id, item_slot, target_attrs}                    → replacements
```

---

## 6. EVALUATION, ABLATION & DEFINITION OF DONE

### 6.1 Bảng metric & target chấm điểm

| Metric | Target | Đo bằng |
|---|---|---|
| Recall@5 (retrieval) | CLIP-ZS baseline **+ 5pp** | `evaluate_retrieval()` |
| FITB accuracy | ≥ 55% | `fitb_accuracy()` |
| Compatibility AUC | ≥ 0.85 | `compatibility_auc()` |
| Body-conditional Precision@5 | **+ 10pp** vs non-conditional | ablation composer |
| Preference pairwise accuracy | ≥ 0.70 (`use_pref` > `pref-off`) | Sprint 9 |
| Instruction-flip consistency | ≥ 0.60 | Sprint 9 |
| E2E latency | < 3s CPU | `pipeline.recommend_outfit()` |
| LLM-as-judge (Gemini) | trung bình ≥ 3.5/5 | Sprint 8 |

**Các hàm metric (pure function — TDD):**
- `recall_at_k(sims, k)` — ground truth trên đường chéo (query i ↔ candidate i).
- `mean_average_precision(sims)` — trung bình `1/(rank+1)`.
- `compatibility_auc(scores, labels)` — `roc_auc_score`.
- `preference_pairwise_accuracy(s_pos, s_neg)` — tỉ lệ `s_pos > s_neg`.
- `instruction_flip_consistency(scores_a, scores_b)` — tỉ lệ outfit thắng bị **lật** khi instruction đảo ngược.

### 6.2 Ablation bắt buộc (4 ablation chấm điểm)

1. **Encoder variants:** CLIP-ZS → FashionCLIP → FashionSigLIP-ZS → FashionSigLIP-FT.
2. **Body conditioning on/off:** `cond_none` vs `cond_body`.
3. **Occasion conditioning on/off:** `cond_none` vs `cond_body_occ`.
4. **Decoding:** greedy vs beam search khi dựng outfit.

### 6.3 Definition of Done (luật XP) — một feature DONE khi:
1. PR merge vào `dev` có **≥1 review** đồng đội.
2. `pytest` coverage **≥70%** cho module đã chạm, **CI xanh**.
3. Có **docstring** + 1 entry trong `docs/feature.md`.
4. **Tái lập được:** `uv sync && make demo` chạy từ đầu.

---

## 6b. ĐO LƯỜNG PERFORMANCE TỪNG TẦNG

Kiến trúc nhiều tầng đòi hỏi **đo lường theo từng tầng riêng biệt** — không thể chỉ dùng một metric end-to-end. Lý do: nếu outfit cuối không tốt, không biết lỗi ở encoder (embed sai), composer (scoring sai), hay preference layer (parse prompt sai). Mỗi tầng có bộ metric riêng, tương ứng với bộ **test/eval độc lập** — đây chính là nguyên tắc TDD của XP áp vào đo lường.

### 6b.1 Bảng đo lường tổng hợp — theo từng tầng

| Tầng | Metric chính | Công cụ đo | Baseline so sánh | Target |
|---|---|---|---|---|
| **L0** Preference | JSON parse rate · slot coverage rate · cache hit rate · latency (ms) | instrumentation code · human spot-check | — | ≥95% parse · cache hit ≥80% sau ngày 2 |
| **L1** Body | Keypoint detection rate · 5-class accuracy · confusion matrix 5×5 | unit test + manual annotation ~50 ảnh | Rule-based floor | detection ≥90% · human spot-check ≥85% agree |
| **L2** Encoder | Recall@1/5/10 · mAP · SigLIP loss curve | `evaluate_retrieval()` · W&B | CLIP-ZS baseline | **Recall@5 ≥ CLIP-ZS + 5pp** |
| **L3** Qdrant | Filter precision · ANN search latency · coverage rate sau filter | Qdrant metrics API | Không có filter | Filter không loại quá 40% candidate |
| **L4** Composer | FITB accuracy · Compatibility AUC · Body-cond P@5 · Pref pairwise acc · Flip consistency | `fitb_accuracy()` · `compatibility_auc()` · `preference_pairwise_accuracy()` | Random baseline · Bi-LSTM Han 2017 | FITB ≥55% · AUC ≥0.85 · Body +10pp |
| **E2E System** | Latency (ms) mỗi bước · tổng E2E · LLM-as-judge · User study Likert | `time.perf_counter()` · Gemini API · Google Form | GPT-4V zero-shot stylist | **<3s CPU** · Gemini ≥3.5/5 · User ≥3.5/5 |

---

### 6b.2 Đo chi tiết từng tầng

#### Layer 0 — Preference Structuring

Không có "ground truth" cứng (prompt tự do), nên dùng 3 phương pháp bổ sung:

| Phương pháp | Mô tả | Khi nào chạy |
|---|---|---|
| **Parse success rate** | % instructions → JSON hợp lệ, `StructuredPreference` validate được | Mỗi lần gọi Gemini |
| **Slot coverage** | % trường `hard`/`soft` được điền ≥1 giá trị (không phải tất cả rỗng) | Trên 100 instruction mẫu |
| **Human spot-check** | Lấy ngẫu nhiên 50 instruction, con người đánh giá hard/soft có đúng ý không (scale 1-5) | Một lần trước Sprint 9 |
| **Body fallback rate** | % request phải dùng body fallback → indicator "user không nêu yêu cầu cụ thể" | Log mỗi inference |
| **Cache efficiency** | `cache_hits / total_calls` — tăng nhanh sau vài ngày → gần API cost $0 | W&B log |

**Khi trình bày:** nhấn mạnh đây là điểm khác biệt — thay vì tag-based cứng, dùng **LLM parse prompt tự do**. Chi phí ~$0 sau khi cache warm. Measure luôn cả latency trung bình của Gemini call vs cache hit.

---

#### Layer 1 — Body Shape Classifier

Thách thức: **không có dataset labeled body shape**. Chiến lược đo:

**Định lượng (có thể làm ngay):**
- `keypoint_detection_rate = số ảnh YOLO detect được / tổng ảnh` trên tập test ~100 selfie.
- YOLO trả về `confidence score` cho từng keypoint → plot distribution histogram (confidence < 0.5 = keypoint không đáng tin → loại bỏ).

**Định tính (semi-manual):**
- Thu thập ~50 ảnh người thật, nhóm gán nhãn body shape thủ công → so sánh với rule classifier → **accuracy 5-class**.
- **Confusion matrix 5×5**: xem classifier nhầm nhiều nhất ở cặp nào (thường: hourglass ↔ rectangle, pear ↔ apple).

**Boundary test (XP — unit test):**
- Các test case biên với `shoulder/hip` ratio ngay cạnh ngưỡng (1.05, 0.95, waist_ratio 0.80) → kiểm tra classifier không dao động.

---

#### Layer 2 — Catalog Encoder

Ba loại đo lường bổ sung nhau:

**1. Retrieval metrics (định lượng chính)**

Trên tập val, mỗi query text → tìm matching image trong catalog. Ground truth = ảnh của cùng `item_ID`.

```
sims[i][j] = <encode_text(text_i), encode_image(image_j)>
Recall@K  = % query tìm đúng item trong top-K kết quả
mAP       = trung bình 1/(rank+1) của đúng item
```

So sánh 4 encoder trên cùng tập val → bảng ablation encoder.

**2. Loss curve (định lượng training)**
- SigLIP training loss vs epoch → xác nhận model đang học (loss giảm).
- Nếu loss tăng hoặc phẳng ngay từ đầu → gradient issue hoặc lr quá cao.
- Log lên W&B → so sánh các lần chạy.

**3. Embedding space visualization (định tính)**
- t-SNE/UMAP 2D plot của 5000 item embeddings, tô màu theo `category1` → tốt = cụm tách biệt theo category (áo/quần/giày rõ ràng).
- Intra-class cosine similarity vs inter-class cosine similarity → tốt = intra >> inter.

---

#### Layer 3 — Qdrant Vector Store

**Filter precision:** sau khi áp `categories_exclude` / `colors_avoid`, lấy mẫu ngẫu nhiên 50 kết quả → kiểm tra bằng tay % item vi phạm constraint. Mục tiêu: 0 vi phạm (filter là hard constraint, không phải ranking).

**Coverage rate sau filter:** nếu filter quá chặt → candidate pool trống → composer không có gì xử lý. Đo `len(candidates) / K_requested` trên 100 query. Nếu < 50% → cần nới lỏng filter hoặc mở rộng catalog.

**ANN search latency:** `Qdrant search` với batch query → log `latency_ms` trung bình và p95. Mục tiêu < 100ms (để tổng E2E < 3s).

---

#### Layer 4 — OutfitTransformer

Đây là tầng có **nhiều metric nhất** và quan trọng nhất với hội đồng DL:

**FITB Accuracy (Fill-in-the-Blank):**
> Che 1 item trong outfit, đưa ra 4 lựa chọn (1 đúng + 3 ngẫu nhiên) → model chọn item phù hợp nhất dựa trên compatibility score. `acc = % model chọn đúng`.
- Baseline ngẫu nhiên = 25% (4 lựa chọn). Target ≥55% — tức model có ý nghĩa thống kê.

**Compatibility AUC:**
> Phân biệt outfit positive (stylist) vs outfit negative (random substitution). `AUC = area under ROC curve`. AUC = 0.5 là random, AUC = 1.0 là hoàn hảo. Target ≥0.85.
- Cần vẽ ROC curve cho mỗi conditioning variant (cond_none / cond_body / cond_body_occ) → hội đồng thấy rõ contribution của từng token.

**Body-conditional Precision@5:**
> Với query có `body_shape`, trong top-5 items → % items có `body_shapes` payload khớp. So sánh `cond_body=True` vs `cond_body=False`. Target +10pp.

**Preference Pairwise Accuracy & Flip Consistency:**
> `pairwise_acc`: % cặp (pos, neg) mà `s_pos > s_neg`.
> `flip_consistency`: % cặp flip instruction mà model cũng flip ranking.
- Hai metric này **chứng minh model học sở thích thực sự**, không phải memorize. Flip consistency < 30% = model bỏ qua `[PREF]` token.

---

#### System E2E — Latency Profiling

Đo **từng bước riêng biệt** để xác định bottleneck:

| Bước | Đo bằng | Mục tiêu |
|---|---|---|
| Preference Structuring (L0) | `time.perf_counter()` wrapping `structure()` | ≈0ms cache hit · ≤800ms miss |
| Body Extraction (L1) | YOLO inference time | ≤400ms |
| Encode query + ANN search (L2+L3) | `encode_text()` + Qdrant search | ≤600ms |
| OutfitTransformer forward (L4) | `composer()` forward time | ≤500ms |
| **Tổng E2E** | `time.perf_counter()` toàn bộ `recommend_outfit()` | **< 3s** |

Trình bày dưới dạng **stacked bar chart** — thấy ngay bước nào chiếm latency nhiều nhất.

---

### 6b.3 Đánh giá định tính (Qualitative Evaluation)

Hai phương pháp bổ sung cho metric định lượng — đặc biệt quan trọng vì "outfit đẹp" không thể đo hoàn toàn bằng số:

#### LLM-as-Judge (Gemini)

Prompt Gemini đánh giá 200 outfit ngẫu nhiên từ hệ thống:
```
"Đây là bộ outfit gợi ý cho người có body shape [X], dịp [Y], sở thích [Z].
Items: [list]. Hãy chấm điểm 1-5 trên 3 tiêu chí:
- Relevance: có phù hợp sở thích không?
- Body-fit: có phù hợp vóc dáng không?
- Occasion-fit: có phù hợp dịp không?"
```

Output: mean score cho mỗi tiêu chí → target ≥3.5/5.

**Lưu ý quan trọng:** LLM-as-judge là **strong baseline cạnh tranh** (GPT-4V / Gemini zero-shot stylist) — nhóm **buộc phải so sánh** với nó. Frame thành: "trong catalog kín, hệ thống specialized của chúng tôi vs. generalist LLM không biết catalog."

#### User Study (Sprint 8)

| Tham số | Giá trị |
|---|---|
| Số người | 10–15, ưu tiên đa dạng body type |
| Số case / người | 5 |
| Thang đo | Likert 1–5 cho 3 tiêu chí: relevance · body-fit · occasion-fit |
| Công cụ | Google Form |
| Phân tích | Mean + std mỗi tiêu chí · paired t-test vs baseline nếu có |
| Bias control | Không cho thấy body shape label để tránh confirmation bias |

Kết quả user study là **highlight quan trọng** trong presentation — con số "người thật đánh giá" thuyết phục hội đồng hơn metric trên tập test.

---

### 6b.4 Bốn Ablation — Thiết kế đo lường

Mỗi ablation kiểm tra đóng góp của **đúng một component**, giữ cố định phần còn lại:

| Ablation | Biến | Metric đo | Kết quả kỳ vọng |
|---|---|---|---|
| **1 — Encoder variants** | CLIP-ZS → FashionCLIP-ZS → FashionSigLIP-ZS → FashionSigLIP-FT | Recall@1/5/10 · mAP | Thang leo lên từng bậc; FT cao nhất |
| **2 — Body conditioning** | `cond_none` vs `cond_body` | Body-cond P@5 · FITB acc | `cond_body` tăng ≥10pp P@5 |
| **3 — Occasion conditioning** | `cond_body` vs `cond_body_occ` | FITB acc trên outfit có occasion label | `cond_body_occ` tốt hơn cho formal/sport |
| **4 — Decoding** | Greedy vs Beam (width B=3) | FITB acc · outfit diversity (intra-list distance) | Beam: FITB cao hơn · diversity cao hơn |

**Cách đọc kết quả ablation khi thuyết trình:**
> "Từ ablation 1, FashionSigLIP-FT > FashionSigLIP-ZS +5pp → fine-tune có hiệu quả. Từ ablation 2, thêm `[BODY]` token tăng P@5 +12pp → conditioning token thực sự học được body preference. Từ ablation 3, `[OCC]` có tác dụng rõ nhất với formal/sport outfit."

---

### 6b.5 Baseline bắt buộc so sánh

Có 3 baseline nhóm **phải có trong slide comparison table** (không né được khi thuyết trình DL):

| Baseline | Mô tả | Điểm mạnh | Điểm yếu so với OutfitMatch |
|---|---|---|---|
| **B1 — CLIP-ZS + Random** | CLIP zero-shot retrieval + ghép outfit ngẫu nhiên | Không cần train | Không học compatibility; không biết body/occasion |
| **B2 — FashionSigLIP-ZS + Bi-LSTM** | SigLIP retrieval + Bi-LSTM compatibility (Han 2017) | SOTA trước transformer | Không có body/occasion conditioning; không có preference |
| **B3 — GPT-4V zero-shot stylist** | Dùng GPT-4V / Gemini mô tả trực tiếp outfit cho user | Generalist mạnh | Không biết catalog cụ thể; không có ANN retrieval; latency cao |

**Framing an toàn khi trình bày:** "B3 là strong baseline, chúng tôi không kỳ vọng thắng mọi tiêu chí. Điểm mạnh của OutfitMatch: (1) tìm được item thực sự có trong catalog, (2) đảm bảo body-fit theo vóc dáng cụ thể, (3) latency < 3s vs. LLM API."

---

### 6b.6 Gợi ý Visualization cho Slide

| Slide | Dạng biểu đồ | Thông điệp |
|---|---|---|
| Encoder ablation | Bar chart: Recall@5 × 4 encoder | "FT vượt ZS" |
| Encoder learning | Line chart: SigLIP loss vs epoch | "Model hội tụ ổn định" |
| Compatibility | ROC curves 3 đường (cond_none/body/body_occ) | "Conditioning cải thiện AUC" |
| Body shape | Confusion matrix 5×5 (heatmap) | "Nhầm nhiều nhất: hourglass ↔ rectangle" |
| Latency breakdown | Stacked horizontal bar: 4 bước | "Bottleneck ở encoder + ANN" |
| User study | Radar chart 3 chiều × 3 hệ thống (B1, B2, OutfitMatch) | "OutfitMatch tốt hơn ở body-fit + occasion-fit" |
| Embedding space | t-SNE 2D, tô màu category | "Cluster rõ → encoder học được fashion domain" |

---

## 7. BẢN ĐỒ SPRINT ↔ KIẾN TRÚC

Đây là slide "kết nối tất cả" — cho hội đồng thấy kiến trúc là sản phẩm của quy trình Scrum:

| Sprint | Tuần | Mục tiêu | Tầng / Component xây |
|---|---|---|---|
| S0 | 1 | Research & baseline | Chọn model & dataset (fashionSigLIP, Polyvore) |
| S1 | 2 | Architecture & pipeline draft | Interface ABC, thiết kế 6 tầng, `config.py` |
| S2 | 3 | Proposal ⚡ | (milestone — trình bày proposal) |
| S3 | 4 | Data + Body pipeline | **Layer 1** + Component 5, Data Stage 1 |
| S4 | 5 | Catalog encoder | **Layer 2** + Component 1, Data Stage 2–3 |
| S5 | 6 | Outfit composer | **Layer 4** + Component 3, Data Stage 4 |
| S6 | 7 | Body-aware + occasion conditioning | Token `[BODY]`/`[OCC]`, Ablation 2 & 3 |
| S7 | 8 | Customization + E2E integration | **Layer 5**, `pipeline.py`, FastAPI |
| S8 | 9 | Demo deploy + user study | Gradio, LLM-as-judge |
| S9 | 10 | Polish + ablation + report ⚡ | **Layer 0** preference, ablation suite, report |

**Thông điệp khi trình bày:** "Chúng tôi không thiết kế xong hết rồi mới code. Mỗi tuần một tầng chạy được, demo ở sprint review, lấy feedback, sang tầng kế. Kiến trúc 6 tầng chính là *cách chia công việc* cho 10 sprint."

---

## 8. TRẠNG THÁI HIỆN TẠI CỦA CODE vs THIẾT KẾ (trung thực)

> Phần này để nhóm **không overclaim** trước hội đồng — XP đề cao "report kết quả trung thực" (ghi rõ trong Risk Register).

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| `config / data / metrics / eval / encoders` | ✅ Hoàn chỉnh + test | Harness chạy được, TDD đầy đủ |
| `OutfitTransformer` (model) | ✅ Hoàn chỉnh | `composer.py` — forward chạy được |
| SigLIP loss + `finetune_encoder` | ✅ Hoàn chỉnh | `contrastive.py` |
| Body pipeline (pose + rule) | ✅ Hoàn chỉnh | `body/` |
| Preference Layer 0 (schema + structuring + post-train) | ✅ Hoàn chỉnh | `preference/`, `preference_trainer.py` |
| Task `fitb` / `compatibility` trong `runner.py` | ⚠️ Chưa hiện thực | `raise NotImplementedError` — kế hoạch Sprint 7 |
| `pipeline.recommend_outfit` → `_retrieve` | ⚠️ Stub | Cần Qdrant index (Sprint 8) |
| Item embeddings trong preference training | ⚠️ Dùng `torch.zeros` placeholder | Chờ Component 2 (catalog index) nối embedding thật |
| `scripts/build_catalog_index.py` | ⚠️ Chưa có | "planned" trong tài liệu |

**Cách phát biểu an toàn khi thuyết trình:** "Kiến trúc và các tầng học cốt lõi (encoder fine-tune, OutfitTransformer, preference post-train) đã hiện thực và test. Phần tích hợp E2E qua Qdrant và task FITB/compatibility là backlog Sprint 7–8 — đúng theo lộ trình sprint."

---

## 9. KỊCH BẢN TRÌNH BÀY 30 PHÚT

| Phút | Nội dung | Slide / Sơ đồ dùng |
|---|---|---|
| 0–3 | Bài toán & motivation: recommend outfit theo body + dịp + sở thích | Sơ đồ 1 (System Overview) |
| 3–6 | Phương pháp luận Scrum/XP — "Sprint = Experiment Cycle" | §0, Sơ đồ 9 (Sprint map) |
| 6–11 | **Data Collection & Pre-processing** — 7 stage, weak supervision, flip invariant | Sơ đồ 2 (Data pipeline) |
| 11–18 | **Model Architecture deep-dive** — Encoder SigLIP + OutfitTransformer tới tầng tensor | Sơ đồ 4, 5 (SigLIP loss, Transformer) |
| 18–23 | **Training Pipeline** — 5 component, 3 invariant, Bradley-Terry | Sơ đồ 3 (Training DAG) |
| 23–26 | **Inference** — luồng 6 bước, ngân sách latency < 3s | Sơ đồ 6 (Inference sequence) |
| 26–29 | Evaluation, ablation, kết quả/metric gate | §6 bảng metric |
| 29–30 | Kết luận + hướng phát triển (try-on, body-aware embedding) | — |

**3 thông điệp đinh phải để lại cho hội đồng:**
1. Kiến trúc 6 tầng = cách chia 10 sprint — *quy trình Scrum sinh ra kiến trúc*.
2. OutfitTransformer là **Set Transformer** với **conditioning token** `[BODY]/[OCC]/[PREF]` — điều kiện hóa nằm ngay trong attention.
3. Chất lượng được bảo đảm bằng **kiểm thử kép**: TDD cho harness, **metric-gate** cho model.

---

*Tài liệu đi kèm: `SO_DO_MERMAID.md` — toàn bộ sơ đồ Mermaid chi tiết.*
