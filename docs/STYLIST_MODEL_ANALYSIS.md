# Phân tích Kiến trúc Mô hình Stylist / Conversationalist

**OutfitMatch v3.1-lite · Tầng 2 — Conversational AI Stylist**

**Branch:** `feature/stylist-model-analysis`  
**Ngày:** 14/06/2026

---

## 0. Context — Vai trò của Tầng 2

Tầng 2 Stylist là giao diện hội thoại đối mặt với user. Nó nhận text + (tùy chọn) ảnh,
parse intent, hỏi lại khi thiếu info, gọi `search_outfits` tool, validate output và
giải thích lý do recommend bằng tiếng Việt. 4 vai trò cụ thể:

| # | Vai trò | Input → Output | Yêu cầu năng lực |
|---|---------|----------------|------------------|
| 1 | **Intent Parser** | text tự do → `{occasion, style, body_shape, height, weight, …}` | Hiểu tiếng Việt, suy luận ngữ cảnh |
| 2 | **Body Analyzer** | height/weight + (optional) ảnh selfie → `body_shape` | Vision (nếu có ảnh), reasoning thận trọng |
| 3 | **Conversational Agent** | context đang thiếu info → câu hỏi thăm dò | Multi-turn, giữ context, natural language |
| 4 | **Outfit Explainer** | `OutfitRecord` items + user profile → giải thích cá nhân hóa | Sinh tiếng Việt tự nhiên, trích dẫn logic |

Các yêu cầu kỹ thuật then chốt:
- **Tool-calling:** Gọi `search_outfits(occasion, style, body_shape, price_max, …)` với enum params từ `vocab.py`
- **Validation:** Tầng guardrail kiểm tra `outfit_id` thật/giả, size thật/giả trước khi hiển thị
- **Latency:** ≤ 5–8s trên GPU (streaming UX), hoặc cloud API
- **VRAM:** 8–16GB cho demo (quantize 4-bit)
- **Tiếng Việt:** Sinh văn bản tiếng Việt tự nhiên, không bị lỗi encoding/syntax

---

## 1. Ba Ứng viên Mô hình — Tổng quan

| Thuộc tính | Qwen3.5-9B | Qwen3-VL-8B | Gemma 4-12B |
|---|---|---|---|
| **Kiến trúc gốc** | Transformer decoder-only | Vision-Language (ViT + Qwen3 LLM) | Transformer decoder-only (Gemma 4) |
| **Số tham số** | 9B | 8B (LLM ~7.5B + ViT ~0.5B) | 12B |
| **Modal input** | Text-only | Text + Image | Text-only (Gemma 4 12B PaliGemma có VL) |
| **Context window** | 32K tokens | 32K tokens | 32K tokens (Gemma 4) |
| **Ngôn ngữ train** | en (ưu tiên), multilingual | en/zh (ưu tiên), multilingual | en (ưu tiên), multilingual |
| **Tiếng Việt** | Khá tốt (Qwen multilingual) | Có tiếng Việt trong training data | Yếu — domain chính en |
| **HF checkpoint** | `Qwen/Qwen3.5-9B` | `Qwen/Qwen3-VL-8B-Instruct` | `google/gemma-4-12b-it` |
| **VRAM (bf16)** | ~18GB | ~16GB | ~24GB |
| **VRAM (4-bit)** | ~5–6GB | ~4–5GB | ~7–8GB |
| **Tool-calling native** | Có (function calling) | Có (function calling) | Không native — cần prompt engineering |
| **LoRA support** | PEFT / Unsloth | PEFT / Unsloth | PEFT / Unsloth |

---

## 2. Phân tích Chi tiết từng Mô hình

### 2.1 Qwen3.5-9B — Text-only Powerhouse

#### Kiến trúc
Qwen3.5-9B là text-only Transformer decoder, kế thừa từ dòng Qwen2.5 với cải tiến về
multilingual reasoning. Dùng RoPE position encoding, GQA (Grouped Query Attention).

#### Điểm mạnh cho project
| Ưu điểm | Chi tiết | Impact |
|----------|----------|--------|
| **Tiếng Việt tốt** | Qwen có dữ liệu multilingual mạnh, hỗ trợ ~100 ngôn ngữ | Giải thích outfit tiếng Việt tự nhiên |
| **Tool-calling native** | Có sẵn function calling format Qwen-style | Gọi `search_outfits` tool qua API chuẩn |
| **VRAM thấp** | 9B params, 4-bit ~5–6GB → chạy được T4 16GB | Demo local dễ, không cần A100 |
| **Unsloth hỗ trợ** | Qwen3.5 có trong Unsloth supported models | QLoRA nhanh, ít bug |
| **Context 32K** | Đủ cho multi-turn hội thoại (3–5 turns × 200–500 tokens) + tool response | Không bị context overflow |
| **Sinh structured output** | Tốt với JSON mode / constrained output | Parse intent → `{occasion, style, …}` dễ validate |

#### Điểm yếu
| Nhược điểm | Chi tiết | Mitigation |
|------------|----------|------------|
| **Không vision** | Không xử lý ảnh đầu vào → bỏ qua use case "user gửi ảnh outfit" | Chấp nhận MVP — ảnh là optional; có thể fallback qua Gemini Flash gọi riêng để phân tích ảnh |
| **Ngữ cảnh thời trang Á** | Domain kiến thức chủ yếu Tây/Trung | Fine-tune LoRA trên data VN để bù |

#### Phù hợp với project: ⭐⭐⭐⭐⭐ (5/5)
Model lý tưởng cho MVP nếu chấp nhận bỏ vision đầu vào. Tool-calling sẵn, tiếng Việt tốt,
VRAM thấp, framework trưởng thành.

---

### 2.2 Qwen3-VL-8B — Vision-Language Model

#### Kiến trúc
Qwen3-VL dùng ViT (Vision Transformer) encoder gắn vào Qwen3 LLM backbone qua cross-attention
projection. Cho phép nhận cả text + image trong cùng prompt, sinh text output.

#### Điểm mạnh cho project
| Ưu điểm | Chi tiết | Impact |
|----------|----------|--------|
| **Multimodal** | Nhận ảnh + text cùng lúc → user gửi ảnh outfit, model tự phân tích | Hỗ trợ Body Analyzer + Outfit Explainer từ ảnh |
| **Tool-calling native** | Qwen3-VL kế thừa function calling từ Qwen3 | Gọi `search_outfits` tool qua format Qwen |
| **VRAM tốt** | 8B params, 4-bit ~4–5GB → T4 16GB ok | Demo local được |
| **Context 32K** | Đủ cho multi-turn + image tokens | Không overflow |
| **Tiếng Việt** | Có trong training data VL, nhưng yếu hơn text-only | Bù bằng LoRA |
| **Đã là plan gốc** | `Kien_truc_v3.1.md` §4 chọn Qwen3-VL là primary | Đồng bộ với architecture docs |

#### Điểm yếu
| Nhược điểm | Chi tiết | Mitigation |
|------------|----------|------------|
| **Tiếng Việt yếu hơn Qwen3.5 text-only** | VL model đánh đổi text quality cho vision → giải thích tiếng Việt có thể kém tự nhiên hơn | Tăng data tiếng Việt trong LoRA dataset |
| **Processor phức tạp** | `Qwen3VLForConditionalGeneration` + `AutoProcessor` — image preprocessing cần chính xác format | Code đã có sẵn trong `run_qwen3vl8b_stylist_experiment.py` |
| **Vision encoder = dead weight nếu không dùng ảnh** | 0.5B params ViT vẫn load dù text-only request | Quantize 4-bit giảm overhead |

#### Phù hợp với project: ⭐⭐⭐⭐ (4/5)
Model được chọn trong plan gốc. Ưu điểm multimodal rất quan trọng cho use case "user gửi
ảnh". Tuy nhiên tiếng Việt yếu hơn và setup phức tạp hơn text-only model.

---

### 2.3 Gemma 4-12B — Google's Multilingual LLM

#### Kiến trúc
Gemma 4-12B là text-only Transformer decoder từ Google DeepMind, dùng kiến trúc Gemma 4
với cải tiến so với Gemma 3 (longer context, better multilingual, faster inference).

#### Điểm mạnh cho project
| Ưu điểm | Chi tiết | Impact |
|----------|----------|--------|
| **Google ecosystem** | Tương thích Gemini Flash API → dùng chung hạ tầng tagging | Unified cloud inference |
| **Multilingual** | Gemma 4 hỗ trợ multilingual, nhưng chủ yếu en | — |
| **LoRA/QLoRA** | PEFT/Unsloth hỗ trợ Gemma | Fine-tune được |
| **Long context** | 32K context window | Multi-turn ok |

#### Điểm yếu
| Nhược điểm | Chi tiết | Impact |
|------------|----------|------------|
| **Tiếng Việt yếu nhất** | Gemma train chủ yếu en; tiếng Việt là secondary language | Giải thích tiếng Việt có thể lỗi syntax, sai ngữ pháp, thiếu tự nhiên |
| **Không tool-calling native** | Gemma không có function calling → phải parse text thủ công | Rủi ro hallucinate tool params, khó validate |
| **VRAM cao nhất** | 12B params, 4-bit ~7–8GB | Vẫn chạy được T4 nhưng sát giới hạn |
| **Không vision** | Text-only → bỏ qua use case ảnh | Phải fallback Gemini Flash cho ảnh |
| **Ít community VN** | Ít tài liệu, ít model tiếng Việt fine-tune sẵn | Mất thời gian debug |

#### Phù hợp với project: ⭐⭐ (2/5)
Không phù hợp cho MVP. Tiếng Việt yếu, không tool-calling native, không vision, VRAM cao.
Chỉ dùng nếu muốn so sánh ablation "Google vs Alibaba" hoặc nếu Gemini Flash làm fallback
stylist và Gemma chỉ làm reasoning engine.

---

## 3. So sánh Trực tiếp trên Tiêu chí Cốt lõi

| Tiêu chí | Qwen3.5-9B | Qwen3-VL-8B | Gemma 4-12B | Trọng số |
|----------|:---:|:---:|:---:|:---:|
| **Tiếng Việt tự nhiên** | 🟢 Xuất sắc | 🟡 Khá | 🔴 Yếu | High |
| **Tool-calling native** | 🟢 Có | 🟢 Có | 🔴 Không | Critical |
| **Vision (ảnh đầu vào)** | 🔴 Không | 🟢 Có | 🔴 Không | Medium |
| **VRAM (4-bit)** | 🟢 ~5–6GB | 🟢 ~4–5GB | 🟡 ~7–8GB | Medium |
| **LoRA ecosystem** | 🟢 PEFT+Unsloth | 🟢 PEFT+Unsloth | 🟢 PEFT+Unsloth | High |
| **Structured output** | 🟢 JSON mode | 🟢 JSON mode | 🟡 Prompt-only | High |
| **Multi-turn context** | 🟢 32K | 🟢 32K | 🟢 32K | Medium |
| **Community/resource** | 🟢 Nhiều | 🟢 Nhiều | 🟡 Ít hơn | Low |
| **Đã trong plan gốc** | 🔴 Chưa | 🟢 Có | 🔴 Chưa | Low |
| **Điểm tổng** | **8/10** | **8/10** | **3/10** | |

> **Ghi chú trọng số:** "Critical" = model không đạt thì phải dùng approach thay thế.
> "Medium" = ảnh hưởng đáng kể đến UX hoặc chi phí triển khai.

---

## 4. Dataset cho Fine-tuning

### 4.1 Loại Dataset

| Loại | Mô tả | Dùng cho model nào | Kích thước |
|------|-------|-------------------|------------|
| **Synthetic conversations (text)** | Gemini sinh hội thoại theo 7 mẫu: hỏi lại, phân tích cơ thể, recommend+giải thích, từ chối, multi-turn, edge case, tool-calling | Cả 3 model | 3–5K hội thoại |
| **Real product captions (text)** | Mô tả sản phẩm VN từ catalog (title_vi, store_name, price_vnd) | Qwen3.5-9B, Gemma | ~5K samples |
| **Image + text pairs** | Ảnh item + text mô tả tiếng Việt | Qwen3-VL-8B | ~2K pairs (có sẵn từ catalog) |
| **Tool-calling examples** | `search_outfits(occasion="office", style="minimalist", …)` với response thật từ retrieval | Cả 3 (ưu tiên Qwen) | ~500–1K samples |
| **Validation guardrail examples** | Negative samples: response chứa `OF_99999` giả, `size XXL` không có → model học tự validate | Cả 3 | ~200 samples |

### 4.2 Dữ liệu Đặc thù cho từng Model

#### Qwen3.5-9B
- **Ưu tiên:** Synthetic conversations tiếng Việt, tool-calling examples, product captions
- **Tỷ lệ:** 60% hội thoại full, 20% tool-calling, 10% product knowledge, 10% guardrail
- **Format:** ChatML (đã có trong `distill_stylist_dataset.py`)
- **Nguồn:** Gemini Flash sinh synthetic + catalog metadata đã có

#### Qwen3-VL-8B
- **Ưu tiên:** Image-text pairs, synthetic conversations, tool-calling
- **Tỷ lệ:** 30% image captioning (ảnh item → mô tả), 40% hội thoại, 20% tool-calling, 10% guardrail
- **Format:** ChatML với `{"type": "image", "image": "..."}` block format Qwen3-VL
- **Nguồn:** Catalog images + Gemini Flash mô tả item, synthetic conversations

#### Gemma 4-12B
- **Ưu tiên:** Nếu bắt buộc dùng → cần lượng lớn hơn (8–10K) để bù domain gap tiếng Việt
- **Tỷ lệ:** 70% hội thoại tiếng Việt, 20% product knowledge, 10% guardrail
- **Format:** ChatML — không có tool-calling native nên cần prompt: "Trả JSON {tool: search_outfits, params: {...}}"
- **Rủi ro:** Dễ hallucinate params → cần data lượng lớn + validation strict

---

## 5. Phương pháp & Framework Fine-tune

### 5.1 So sánh Framework

| Framework | Qwen3.5-9B | Qwen3-VL-8B | Gemma 4-12B | Ghi chú |
|-----------|:---:|:---:|:---:|---|
| **PEFT + LoRA** | ✅ | ✅ | ✅ | Chuẩn HF — ổn định, dễ dùng, nhiều doc |
| **Unsloth + QLoRA** | ✅ | ✅ | ✅ | Nhanh hơn 2x, tiết kiệm VRAM, hỗ trợ Kaggle T4 |
| **Axolotl** | ✅ | ⚠️ VL chưa ổn định | ✅ | Dataset YAML config, multi-GPU |
| **LLaMA-Factory** | ✅ | ✅ | ⚠️ | UI training, hỗ trợ VL |
| **TRL (SFTTrainer)** | ✅ | ⚠️ | ✅ | HF native, ít bug nhất |

### 5.2 Đề xuất cho MVP

```
Framework:  Unsloth + QLoRA (như đã setup trong prepare_stylist_qlora_kaggle.py)
Platform:   Kaggle T4×2 GPU (free tier)
Strategy:   LoRA r=16, alpha=32, target_modules=all-linear
Quantize:   4-bit NF4 double-quant (giảm VRAM 4x)
Optimizer:  AdamW 8-bit (paged)
Epochs:     3–5 (dataset nhỏ 3–5K, tránh overfit)
Schedule:   Linear warmup 10% + cosine decay
Batch:      2–4 per GPU (effective 4–8 với gradient accumulation)
```

### 5.3 Quy trình Fine-tune (Chuẩn cho cả 3 model)

```bash
# Bước 1: Chuẩn bị dataset
uv run python scripts/stylist/distill_stylist_dataset.py \
    --mode full \
    --out data/stylist/fine_tune/stylist_distilled_full/

# Bước 2: Package cho Kaggle
uv run python scripts/stylist/prepare_stylist_qlora_kaggle.py \
    --stylist-knowledge data/stylist/fine_tune/stylist_distilled_full/ \
    --model qwen35-9b \
    --target-kaggle-dataset Nhat-Quang/outfitmatch-stylist-dataset

# Bước 3: Train trên Kaggle T4×2 (Unsloth QLoRA)
# → Kernel tự động push LoRA adapter lên HF
# → Repo: Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora

# Bước 4: Merge + quantize GGUF (Llama Turbo Quant)
uv run python scripts/stylist/upload_stylist_artifacts_to_hf.py \
    --hf-repo Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora \
    --push-gguf
```

---

## 6. Khuyến nghị Final

### 6.1 MVP Primary: Qwen3.5-9B (5/5)

```
Lý do chọn:
  1. Tiếng Việt xuất sắc nhất trong 3 model → giải thích tự nhiên
  2. Tool-calling native → bảo vệ chống hallucination outfit_id
  3. VRAM thấp nhất (5–6GB 4-bit) → demo dễ, T4 free tier Kaggle ok
  4. Unsloth support hoàn chỉnh → QLoRA nhanh, ít lỗi
  5. JSON mode → parse intent structured dễ validate

Trade-off chấp nhận:
  - Bỏ vision đầu vào → user không gửi ảnh selfie
  - Fallback: Gemini Flash xử lý ảnh riêng, rồi đưa text description vào Qwen
```

### 6.2 MVP Secondary / Comparison: Qwen3-VL-8B (4/5)

```
Vai trò: Ablation so sánh "có vision vs không vision"
Dùng khi: Cần báo cáo multimodal capability cho rubric
Setup: Đã có experiment script (run_qwen3vl8b_stylist_experiment.py)
```

### 6.3 Không khuyến nghị: Gemma 4-12B (2/5)

```
Chỉ dùng cho:
  - Ablation comparison "Google vs Alibaba model family"
  - Nếu bắt buộc đa dạng model trong báo cáo

Không dùng cho:
  - Production / demo chính (tiếng Việt yếu, không tool-calling)
```

### 6.4 Roadmap Tầng 2 (Sprint 6–7)

| Sprint | Model | Action |
|--------|-------|--------|
| Sprint 6a | Qwen3.5-9B | Generate 3–5K synthetic convs + QLoRA train |
| Sprint 6b | Qwen3-VL-8B | QLoRA train với image-text pairs (ablation) |
| Sprint 7a | Qwen3.5-9B | Tích hợp tool-calling + validation → pipeline E2E |
| Sprint 7b | Qwen3.5-9B | Merge LoRA → GGUF quantize → upload HF |
| Sprint 9 | Cả 2 Qwen | LLM-judge evaluation + ablation "text-only vs multimodal" |

---

## 7. Tổng kết

| | Qwen3.5-9B | Qwen3-VL-8B | Gemma 4-12B |
|---|:---:|:---:|:---:|
| **Tiếng Việt** | 🟢 Xuất sắc | 🟡 Khá | 🔴 Yếu |
| **Tool-calling** | 🟢 Native | 🟢 Native | 🔴 Prompt hack |
| **Vision** | 🔴 Không | 🟢 Có | 🔴 Không |
| **VRAM 4-bit** | 🟢 5–6GB | 🟢 4–5GB | 🟡 7–8GB |
| **Điểm tổng** | **8/10** ✅ | **8/10** ✅ | **3/10** ❌ |
| **Vai trò** | **Primary** | Ablation comparison | Không dùng |

**Quyết định:** Qwen3.5-9B làm primary stylist model, Qwen3-VL-8B làm ablation comparison.
Gemma 4-12B không phù hợp cho MVP do tiếng Việt quá yếu và thiếu tool-calling native.
Dataset dùng synthetic conversations từ Gemini + catalog metadata, fine-tune qua
Unsloth QLoRA trên Kaggle T4×2.

---

*Hết — Phân tích Kiến trúc Stylist Model v3.1-lite.*