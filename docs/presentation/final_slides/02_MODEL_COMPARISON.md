# 02 — So sánh & Đánh giá Kiến trúc 4 Model Stylist

**Phạm vi:** Phân tích kiến trúc + benchmark 4 ứng viên (T1/T2/T3/T4)
**Mục tiêu slide:** Cho giám khảo DL thấy **tiêu chí chọn model** cho downstream task cụ thể (tool-calling stylist) khác với chọn model theo leaderboard chung.

---

## 1. Bốn ứng viên — Tổng quan kiến trúc

### 1.1 Bảng so sánh kiến trúc

| | **T1** Qwen3-VL-8B Instruct | **T2** Qwen3.5-9B | **T3** Qwen3-VL-8B Thinking ✅ | **T4** Gemma 4 12B IT |
|---|---|---|---|---|
| **Họ model** | Alibaba Qwen3-VL | Alibaba Qwen3.5 | Alibaba Qwen3-VL (Thinking) | Google Gemma 4 |
| **Kiến trúc gốc** | Vision-Language Model | Transformer decoder-only | VLM + reasoning head | Transformer decoder-only |
| **Thành phần** | ViT ~0.5B + LLM ~7.5B | 9B params | ViT ~0.5B + LLM ~7.5B + reasoning | 12B params |
| **Input modal** | Text + Image | Text-only | Text + Image | Text-only |
| **Context window** | 32K tokens | 32K tokens | 32K tokens | 32K tokens |
| **Tool-calling native** | ✅ function calling | ✅ function calling | ✅ function calling | ❌ prompt engineering |
| **VRAM bf16** | ~16GB | ~18GB | ~16GB | ~24GB |
| **VRAM 4-bit** | ~4–5GB | ~5–6GB | ~4–5GB | ~7–8GB |
| **Tiếng Việt** | Khá tốt | **Xuất sắc** | Khá tốt | Yếu |
| **HF checkpoint** | `unsloth/Qwen3-VL-8B-Instruct-bnb-4bit` | `techwithsergiu/Qwen3.5-text-9B-bnb-4bit` | `unsloth/Qwen3-VL-8B-Thinking-bnb-4bit` | `unsloth/gemma-4-12b-it` |

### 1.2 Sơ đồ kiến trúc (VLM vs text-only)

```
TEXT-ONLY (T2, T4)                  VLM (T1, T3)
┌───────────────────┐               ┌───────────────────┐
│  Input: text      │               │  Input: text+img  │
└─────────┬─────────┘               └─────────┬─────────┘
          │                                   │
          ▼                                   ▼
┌───────────────────┐               ┌───────────────────┐
│  Tokenizer        │               │  Tokenizer │ ViT   │
│  (BPE/SentencePc.)│               │  (text)  │ (patch)│
└─────────┬─────────┘               └─────┬───────┘
          │                               │
          ▼                               ▼
┌───────────────────┐               ┌───────────────────┐
│  Embedding        │               │  Embedding │ Proj. │
└─────────┬─────────┘               │  (cross-attn bride)│
          │                         └─────────┬─────────┘
          ▼                                   │
┌───────────────────┐                        ▼
│  Transformer      │            ┌───────────────────┐
│  decoder (N×blk)  │            │  Transformer      │
│  - GQA attn       │            │  decoder (N×blk)  │
│  - RoPE pos enc   │            │  - GQA attn       │
│  - SwiGLU FFN     │            │  - RoPE + img tok │
└─────────┬─────────┘            └─────────┬─────────┘
          ▼                                ▼
┌───────────────────┐            ┌───────────────────┐
│  LM head          │            │  LM head          │
│  → token logits   │            │  → token logits   │
└───────────────────┘            └───────────────────┘
```

**Điểm khác biệt VLM:** thêm **ViT encoder** (patchify ảnh → vision embedding) + **cross-attention projection** để vision token hòa vào text token stream. T3 Thinking có thêm reasoning head / CoT training để suy luận trước khi output.

---

## 2. Phân tích chi tiết từng model (đánh giá sơ bộ trước benchmark)

### 2.1 T1 — Qwen3-VL-8B Instruct

**Điểm mạnh:**
- ✅ Multimodal (nhận ảnh selfie cho Body Analyzer)
- ✅ Tool-calling native (function calling Qwen-style)
- ✅ VRAM thấp (4-bit ~4–5GB)
- ✅ Unsloth support hoàn chỉnh
- ✅ Đã trong plan gốc (`Kien_truc_v3.1.md` §4)

**Điểm yếu:**
- ⚠️ Tiếng Việt yếu hơn Qwen3.5 text-only (VL đánh đổi text quality cho vision)
- ⚠️ Processor phức tạp (`Qwen3VLForConditionalGeneration` + `AutoProcessor`)
- ⚠️ Vision encoder = "dead weight" nếu request text-only

**Đánh giá:** ⭐⭐⭐⭐ (4/5) — baseline VLM ổn định.

### 2.2 T2 — Qwen3.5-9B (Text-only)

**Điểm mạnh:**
- ✅ **Tiếng Việt xuất sắc nhất** (Qwen multilingual ~100 ngôn ngữ)
- ✅ Tool-calling native
- ✅ **VRAM thấp nhất** (4-bit ~5–6GB)
- ✅ Unsloth support tốt
- ✅ Structured output (JSON mode) mạnh
- ✅ Context 32K đủ multi-turn

**Điểm yếu:**
- ❌ **Không vision** → bỏ use case "user gửi ảnh"
- ⚠️ Domain thời trang Á yếu hơn Tây/Trung → cần LoRA bù
- ⚠️ Load target thực dụng là repo ngoài (`techwithsergiu/...`) → có thể khác chat template

**Đánh giá:** ⭐⭐⭐⭐⭐ (5/5) cho text-only use case. Lý tưởng nếu bỏ vision.

### 2.3 T3 — Qwen3-VL-8B Thinking ✅ (PRODUCTION PRIMARY)

**Điểm mạnh:**
- ✅ Multimodal + **reasoning** (Thinking variant)
- ✅ Tool-calling native
- ✅ VRAM tốt (4-bit ~4–5GB)
- ✅ Context 32K
- ✅ **Lợi thế reasoning khi parse VN → enum** ("đi làm" → `office`, "dáng tam giác ngược" → `inverted_triangle`)
- ✅ Unsloth support

**Điểm yếu:**
- ⚠️ Tiếng Việt yếu hơn T2 text-only
- ⚠️ Processor phức tạp
- ⚠️ Reasoning head tăng latency (nhưng acceptable cho streaming UX)

**Đánh giá:** ⭐⭐⭐⭐ (4/5) — **được chọn làm production primary** sau benchmark.

### 2.4 T4 — Gemma 4 12B IT

**Điểm mạnh:**
- ✅ Google ecosystem (tương thích Gemini Flash API)
- ✅ Multilingual (nhưng chủ yếu en)
- ✅ LoRA/QLoRA support
- ✅ Long context

**Điểm yếu:**
- ❌ **Tiếng Việt yếu nhất** (en-primary)
- ❌ **Không tool-calling native** → phải prompt hack "Trả JSON {tool:...}"
- ❌ **VRAM cao nhất** (4-bit ~7–8GB)
- ❌ Không vision (text-only)
- ❌ Ít community VN

**Đánh giá:** ⭐⭐ (2/5) — **không phù hợp MVP**. Chỉ dùng cho ablation "Google vs Alibaba".

---

## 3. So sánh trực tiếp trên tiêu chí cốt lõi (matrix đánh giá)

| Tiêu chí | T1 | T2 | T3 ✅ | T4 | Trọng số |
|---|:---:|:---:|:---:|:---:|:---:|
| Tiếng Việt tự nhiên | 🟡 Khá | 🟢 Xuất sắc | 🟡 Khá | 🔴 Yếu | **High** |
| Tool-calling native | 🟢 | 🟢 | 🟢 | 🔴 Không | **Critical** |
| Vision input | 🟢 | 🔴 | 🟢 | 🔴 | Medium |
| VRAM 4-bit thấp | 🟢 4–5GB | 🟢 5–6GB | 🟢 4–5GB | 🟡 7–8GB | Medium |
| LoRA ecosystem | 🟢 | 🟢 | 🟢 | 🟢 | High |
| Structured output | 🟢 JSON | 🟢 JSON | 🟢 JSON | 🟡 Prompt | High |
| Multi-turn 32K | 🟢 | 🟢 | 🟢 | 🟢 | Medium |
| Reasoning (VN→enum) | 🟡 | 🟡 | 🟢 **Thinking** | 🟡 | Medium |
| Unsloth support | 🟢 | 🟢 | 🟢 | 🟢 | High |

---

## 4. Kết quả benchmark thực nghiệm

### 4.1 SFT Benchmark (70 held-out prompts, cùng dataset)

| Rank | Model | Tool F1 ↑ | Text sim ↑ | Format ↑ | Error ↓ | Eval loss ↓ |
|---:|---|---:|---:|---:|---:|---:|
| **1** | **T3 Thinking** ✅ | **0.898** | **0.552** | **1.000** | **0** | **0.594** |
| 2 | T2 Qwen3.5 BNB4 | 0.877 | 0.488 | 1.000 | 0 | 0.688 |
| 3 | T1 Instruct | 0.857 | 0.544 | 1.000 | 0 | 0.603 |
| 4 | T4 Gemma | 0.653 | 0.535 | 0.971 | 0 | 0.626 |

### 4.2 Subtask breakdown — quan trọng để hiểu điểm mạnh/yếu

| Subtask | T1 | T2 | **T3** | T4 | Insight |
|---|---:|---:|---:|---:|---|
| `tool_calling_grounded` | 0.886 | **0.943** | 0.914 | 0.914 | T2 mạnh khi prompt rõ |
| `tool_calling` (non-grounded) | 0.786 | 0.714 | **0.857** | **0.000** | T3 reasoning giúp nhất; Gemma không trigger tool |
| `stylist_knowledge` sim | 0.383 | **0.412** | 0.387 | 0.403 | T2 tiếng Việt tốt nhất |
| `recommend_explain` sim | 0.646 | 0.698 | **0.698** | 0.126 | Gemma yếu giải thích grounded |
| `body_fit_grounded` sim | **0.835** | **0.835** | 0.816 | 0.823 | Tất cả khá |

### 4.3 Fashion-Logic Benchmark (GPU, 28 items × 6 scorers, sau scorer-fix)

| Task | T1 | T2 | **T3** | Đọc |
|---|---:|---:|---:|---|
| `occasion_formality` | 0.607 | 0.585 | **0.740** | T3 thắng nhờ SFT tool + reasoning |
| `body_shape_advice` | 0.000 | 0.050 | **0.040** | **Tất cả yếu** — answer quá generic, cần RL |
| `season_advice` | 0.258 | 0.333 | **0.383** | T3 tốt nhất nhưng còn thấp |
| `coherence` | 0.500 | **1.000** | 0.500 | T2 perfect; T3 học được qua RL |
| `ask_back` | 0.667 | 0.667 | 0.667 | Cả 3 đều 1 prompt fail |
| `tool_call_derivation` | **0.812** | 0.788 | 0.763 | Đã cao, anti-regression |
| **Overall mean** | 0.462 | **0.543** | **0.524** | T2 dẫn đầu ngắn; T3 cần RL +0.03 |

---

## 5. Phân tích vì sao T3 thắng SFT benchmark

### 5.1 T3 — ổn định nhất, không nhất mọi subtask

T3 có **profile tốt nhất cho production** vì thắng đồng thời:
- Tool F1 cao nhất overall (0.898)
- Text similarity cao nhất overall (0.552)
- Format compliance 100%, error 0
- Eval loss thấp nhất (0.594)
- `tool_calling` non-grounded tốt nhất Qwen/Gemma (0.857)

**Lý do:** Thinking variant có lợi thế khi phải suy luận từ tiếng Việt tự nhiên sang enum nội bộ. Tool call OutfitMatch không chỉ là copy keyword — model phải hiểu "đi làm", "cafe", "dáng tam giác ngược", "tránh màu sáng", "ngân sách dưới 900k" rồi map sang field/schema.

### 5.2 T2 — mạnh tool khi prompt rõ, yếu style hơn

T2 thắng `tool_calling_grounded` (0.943) → khi prompt/context rõ thì map field rất tốt. Nhưng:
- `tool_calling` non-grounded chỉ 0.714 (kém T3 0.143)
- Text similarity overall thấp nhất top 3
- Eval loss cao nhất (0.688)

**Nguyên nhân:**
- Load target thực dụng là repo ngoài (`techwithsergiu/...`) → khác chat template behavior
- Text-only có xu hướng trả lời thẳng, ít bám style hội thoại
- Hợp làm fallback planner khi prompt scaffold rõ

### 5.3 T1 — tự nhiên nhưng tool F1 thấp hơn T3

T1 có text similarity gần T3 và compliance 100%, nhưng:
- `tool_calling_grounded` 0.886 < T2/T3
- `tool_calling` 0.786 < T3 0.857

→ Instruct variant học format tốt nhưng kém Thinking variant ở bước **chọn đúng argument/enum**. Phù hợp nếu muốn output ngắn trực tiếp, nhưng production cần tool chính xác hơn.

### 5.4 T4 Gemma — chưa nội hoá "khi nào gọi tool"

Gemma có eval loss 0.626 (khá) và text sim 0.535 (không tệ). Cũng đạt `tool_calling_grounded` 0.914. Nhưng Tool F1 overall chỉ 0.653 vì:
- `tool_calling` non-grounded = **0.000** (model sinh prose "Mình sẽ tìm outfit..." thay vì `<tool_call>`)
- Format compliance 0.971 (thấp nhất 4 model)

→ Gemma học khá tốt phần ngôn ngữ/giải thích, nhưng **chưa nội hoá contract "khi nào phải gọi tool"**. Khi scaffold đủ rõ, gọi được; khi prompt tự nhiên hơn, quay về prose. Chưa phù hợp làm planner chính.

---

## 6. Vì sao eval loss KHÔNG quyết định ranking cuối

| Đo lường | Cái gì | Hạn chế |
|---|---|---|
| **Eval loss** | Next-token likelihood trung bình trên eval set | Không đo hành vi sau generation |
| **Text similarity** | Độ gần generated vs reference | Câu đúng có thể diễn đạt khác → false low |
| **Tool F1** | Field/value match trong tool-call | **Đo đúng contract production** |
| **Format compliance** | Output đúng tool schema | **Hard gate** — sai = retrieval vỡ |

**Quy tắc chọn model cho OutfitMatch:**
> Một lỗi nhỏ trong tool-call có thể làm retrieval sai hoàn toàn. Vì vậy chọn model phải dựa trên **benchmark hành vi** (Tool F1 + compliance), KHÔNG chỉ eval loss.

**Ví dụ thực tế:** T4 Gemma eval loss 0.626 < T2 0.688, nhưng Tool F1 0.653 << T2 0.877. Nếu chỉ nhìn loss sẽ chọn nhầm Gemma.

---

## 7. Quyết định cuối + vai trò từng model

```
┌─────────────────────────────────────────────────────────────────┐
│  PRODUCTION PRIMARY: T3 Qwen3-VL-8B Thinking + LoRA            │
│  • Tool F1: 0.898  • Text sim: 0.552  • Compliance: 1.0        │
│  • Eval loss: 0.594 (thấp nhất)  • Error: 0                    │
│  • Lý do: ổn định nhất + multimodal + reasoning cho VN→enum     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FALLBACK / ABLATION:                                           │
│  • T2 Qwen3.5-9B — text-only/tool-focused khi prompt rõ        │
│  • T1 Qwen3-VL-8B Instruct — ổn định, tự nhiên, kém T3 tool     │
│  • T4 Gemma 4 12B — chỉ dùng cho explanation-only sau retrieval │
│                  (không dùng làm planner/tool caller)           │
└─────────────────────────────────────────────────────────────────┘
```

**Trade-off quan trọng (cần nói rõ trong slide):**
- T2 (text-only) mean fashion-logic 0.543 > T3 0.524, nhưng T2 **không có vision**.
- T3 được chọn vì stylist nhận ảnh user là **feature cốt lõi** của sản phẩm.
- Nếu sau RL T3 vẫn tụt dưới T2 ≥ 0.10 mean → cân nhắc ship T2 cho feature không cần ảnh.

---

## 8. Bảng tổng kết — Điểm tổng + vai trò

| | T1 Instruct | T2 Qwen3.5 | **T3 Thinking** ✅ | T4 Gemma |
|---|:---:|:---:|:---:|:---:|
| Tiếng Việt | 🟡 | 🟢 | 🟡 | 🔴 |
| Tool-calling | 🟢 | 🟢 | 🟢 | 🔴 |
| Vision | 🟢 | 🔴 | 🟢 | 🔴 |
| VRAM 4-bit | 🟢 | 🟢 | 🟢 | 🟡 |
| SFT Tool F1 | 0.857 | 0.877 | **0.898** | 0.653 |
| SFT Eval loss | 0.603 | 0.688 | **0.594** | 0.626 |
| Fashion-logic mean | 0.462 | 0.543 | 0.524 | n/a* |
| **Điểm tổng** | 8/10 | 8/10 | **8/10 + production** | 3/10 |
| **Vai trò** | Fallback | Text fallback | **Primary** | Explanation-only |

\* T4 chưa benchmark GPU vì cần >8GB VRAM (defer Kaggle).

---

## 9. Slide gợi ý (cho giám khảo DL)

1. **Slide ma trận kiến trúc** (§1.1) — so sánh 4 model trên 1 bảng.
2. **Slide sơ đồ VLM vs text-only** (§1.2) — trực quan kiến trúc.
3. **Slide matrix đánh giá** (§3) — icon 🟢🟡🔴 dễ hiểu.
4. **Slide benchmark chart** — cột nhóm Tool F1 / Eval loss / Text sim cho 4 model (T3 highlight).
5. **Slide "vì sao T3 thắng"** (§5) — giải thích Thinking variant reasoning.
6. **Slide "eval loss không quyết định"** (§6) — điểm nhấn DL: chọn metric đúng cho downstream task.
7. **Slide vai trò cuối** (§7) — primary/fallback/ablation.

---

*Hết báo cáo model comparison. Đọc tiếp `03_FINETUNE_DETAILS.md`.*
