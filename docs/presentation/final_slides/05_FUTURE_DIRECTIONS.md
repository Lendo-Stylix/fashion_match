# 05 — Tiềm năng & Hướng phát triển tương lai cho Stylist Model

**Phạm vi:** RL (GRPO), RAG knowledge injection, constrained decoding, benchmark ngoài, vision integration
**Mục tiêu slide:** Cho giám khảo DL thấy **tầm nhìn nghiên cứu tiếp theo** — đây là phần thường được hỏi nhiều trong Q&A.

---

## 1. Tóm tắt — 6 hướng phát triển chính

| # | Hướng | Timeline | Impact | Risk |
|---|---|---|---|---|
| **1** | **GRPO verifiable-reward RL** cho T3 | 1–2 tuần | 🔴 Cao | 🟡 Trung bình |
| **2** | **RAG knowledge injection** (Tầng 1.5) | 2–3 tuần | 🔴 Cao | 🟡 Trung bình |
| **3** | **Constrained decoding + parser repair** | 1 tuần | 🟡 Trung bình | 🟢 Thấp |
| **4** | **Benchmark ngoài** (BFCL/IFEval/Polyvore) | 2–4 tuần | 🟡 Trung bình | 🟢 Thấp |
| **5** | **Failure-driven data vòng 2** | 1–2 tuần | 🔴 Cao | 🟢 Thấp |
| **6** | **Vision integration thực sự** (image-text pair) | 3–4 tuần | 🟡 Trung bình | 🟡 Trung bình |

---

## 2. Hướng 1 — GRPO Verifiable-Reward RL (Priority cao nhất)

### 2.1 Vì sao cần RL sau SFT?

**Vấn đề SFT:** Model học "giọng stylist" + tool-call format, nhưng chưa tối ưu **hành vi đúng** trên fashion-logic:
- `body_shape_advice` chỉ 0.04 (quá generic)
- `occasion_formality` 0.74 (tốt nhưng còn dư địa)
- `coherence` 0.50 (T2 đạt 1.0 → T3 có thể học)

**RL giải quyết:** Fine-tune tiếp trên SFT model, nhưng thay vì học "next-token đúng", học **tối ưu reward** = hành vi đúng fashion.

### 2.2 Vì sao chọn GRPO (không phải PPO/DPO/KTO)?

| Thuật toán | Ưu | Nhược | Chọn? |
|---|---|---|---|
| **PPO** | On-policy classic | Cần reward model + value model → tốn VRAM | ❌ |
| **DPO** | Đơn giản, offline pairwise | Distribution mismatch vs SFT | ❌ |
| **KTO** | Unpaired preference | Cần nhãn предпочтения | ⚠️ Fallback |
| **SimPO** | Reference-free | Cần pairwise | ❌ |
| **GRPO** ✅ | **Verifiable reward, không cần RM**, on-policy, 1 model + KL | Cần compute gõ hơn SFT | ✅ |

**Lý do GRPO thắng cho OutfitMatch:**
- **Reward deterministic** từ 6 scorer `fashion_eval.py` → KHÔNG cần reward model tốn kém
- **On-policy** → khắc phục distribution mismatch của DPO offline
- **1 quantized model + KL** → vừa T4 Kaggle 16GB vừa RTX 5060 8GB local
- DeepSeek-R1 dùng GRPO → proven cho reasoning task

### 2.3 Reward design — 6 verifiable reward functions

Từ `scripts/stylist/grpo_rewards.py`, mỗi reward bridge 1 scorer trong `fashion_eval.py` sang `reward_fn(completions, **kwargs) -> list[float]`:

| # | Reward | Baseline T3 | Priority | Revision |
|---|---|---:|---|---|
| R1 | `occasion_formality_reward` | 0.740 | 🟡 P1 | Thêm substring normalization |
| R2 | `body_shape_advice_reward` | 0.040 | 🔴 **P0** | Tăng positive recall weight |
| R3 | `season_advice_reward` | 0.383 | 🟡 P1 | Như gốc |
| R4 | `coherence_reward` | 0.500 | 🟡 P2 | Thêm binary key verdict |
| R5 | `ask_back_reward` | 0.667 | 🟢 P3 | Anti-regression |
| R6 | `tool_call_derivation_reward` | 0.763 | 🟢 P3 | Anti-regression |

### 2.4 Prompt pool cho GRPO

- `build_fashion_prompt_pool()`: 397 items từ Cartesian expansion trong `grpo_rewards.py`
- Mở rộng: thêm 50 occasion-prompt biến thể đơn class (ep model chọn chính xác, không range)
- 30 body-shape prompt yêu cầu mention ≥2 positive keywords (thúc R2)
- Ground truth tính từ `vocab.py` → reproducible 100%

### 2.5 Training recipe GRPO

```bash
# Hyperparameter
beta = 0.04            # KL drift coefficient
lr = 1e-5              # thấp hơn SFT (2e-4)
num_generations = 8    # G=8 (T4), G=4 nếu local 8GB OOM
batch_size = 8
max_completion_length = 256
lora_r = 32            # cao hơn SFT để có capacity mới
loss_type = dr_grpo    # remove length bias (Liu et al. 2025)
optim = paged_adamw_8bit
```

**Anti-collapse:**
- Monitor `frac_reward_zero_std ≥ 0.3` → giảm LR
- Length penalty −0.05
- Drift KL giữ tiếng Việt không forget

### 2.6 Compute budget

| Hardware | Mode | ETA | Output |
|---|---|---|---|
| Local RTX 5060 8GB | 50 GRPO steps, 28-item pool | ~30–90 min | Sanity + first signal |
| Local RTX 5060 | 200–500 steps, 397-item pool | 4–12h (overnight) | Usable adapter |
| Kaggle T4×1 (15GB) | 500 steps, ~500-prompt pool | ~13h | Production-ready |
| Kaggle T4×2 | 500 steps | ~7h | Production-ready |

### 2.7 Target sau RL

| Metric | Baseline T3 SFT | Target sau RL | Δ |
|---|---:|---:|---:|
| `body_shape_advice` | 0.040 | **≥ 0.45** | +0.41 |
| `season_advice` | 0.383 | ≥ 0.60 | +0.22 |
| `coherence` | 0.500 | ≥ 0.85 | +0.35 |
| `occasion_formality` | 0.740 | ≥ 0.65 (anti-regress) | — |
| Tool F1 (SFT) | 0.898 | ≥ 0.85 (anti-regress) | — |
| **Overall mean** | 0.524 | **≥ 0.55** | +0.03 |

→ Mục tiêu đạt T2 mean (0.543) + vượt qua, đồng thời giữ Tool F1 SFT.

---

## 3. Hướng 2 — RAG Knowledge Injection (Tầng 1.5)

### 3.1 Vấn đề "học vẹt" của SFT

**Phân tích (từ decision memory):** Dataset distill có 7,200 knowledge + 1,600 behavioral = **82% knowledge, 18% behavior**. Model 8B + LoRA **không thể memorize** 7,200 diverse fabric/color QA → SFT MLE collapse thành "câu cực đơn giản" vẫn pass `validation.py` (chỉ check tool schema + outfit_id + size).

→ **Verdict:** Thêm RAG layer, refit LoRA thuần behavior (~3–5K, context-conditional SFT).

### 3.2 Kiến trúc Tầng 1.5 `fashion_kb`

```
┌─────────────────────────────────────────────────────────────┐
│  TẦNG 1.5 — FASHION KB (Qdrant collection `fashion_kb`)     │
│  • 35,994 clean knowledge rows (từ G1 distill clean pool)   │
│  • Embed via LaBSE adapter (đã có trong kb/embedding.py)    │
│  • Chunk theo heading, metadata: topic, source              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (retrieval top-K theo user query)
┌─────────────────────────────────────────────────────────────┐
│  TẦNG 2 — STYLIST (refit LoRA thuần behavior)               │
│  System prompt: "<fashion_kb>{retrieved_context}</fashion_kb>"│
│  + user query                                                │
│  → Model học ĐIỀU KIỆN theo context, không memorize         │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Vì sao KHÔNG mâu thuẫn v3.1 "reject RAG"?

**Quyết định v3.1 §3** reject RAG vector search cho **Tầng 3 outfit retrieval** (query → outfit-embedding space chưa định nghĩa). Nhưng **Tầng 1.5 `fashion_kb`** là **free-text knowledge injection** cho stylist — **không phải** contradiction.

### 3.4 3 must-have để fix hoạt động

1. **Expand behavioral data + teach verbose-grounded pattern** — model phải học "khi có context, trả lời rich grounding vào context"
2. **Context-conditional SFT** — `<fashion_kb>` slot ở **cả train và infer**, không chỉ infer
3. **LLM-judge "grounding richness" dimension** — beyond yes/no, chấm mức độ dùng context

### 3.5 Implementation gợi ý

- `build_fashion_kb.py` (~120 LOC mới) — index 35K rows vào Qdrant
- `stylist/knowledge_rag.py` (~80 LOC mới) — retrieval adapter
- Rewrite `stylist/data.py` + `stylist/model.py` stubs
- Edit `distill_stylist_dataset.py` để **drop knowledge rows**, chỉ giữ behavioral

**Reuse:** qdrant-client, `kb/embedding.py` encode_items adapter, `stylist/tools.py` + `validation.py` untouched, `vocab.py` invariant intact.

---

## 4. Hướng 3 — Constrained Decoding + Parser Repair

### 4.1 Vì sao cần?

Tool-call là **contract cứng** — 1 JSON syntax error = retrieval vỡ. SFT giảm error nhưng không triệt tiêu. Cần:

| Kỹ thuật | Mô tả |
|---|---|
| **JSON grammar / constrained decoding** | Dùng `outlines` / `lm-format-enforcer` ép output đúng JSON schema trong `<tool_call>` |
| **Enum alias normalizer** | Map "smart casual" → `smart_casual` runtime |
| **Retry nếu thiếu `<tool_call>`** | Trong tình huống bắt buộc gọi tool, retry với system prompt mạnh hơn |
| **Validation layer chặn field ngoài vocab** | Block enum ngoài `vocab.py` |
| **Logging parse failures** | Active learning signal → gom vào data vòng 2 |

### 4.2 Trade-off

- ✅ Hard guarantee tool-call parse được
- ⚠️ Tăng latency (~10–20ms cho grammar check)
- ⚠️ Có thể giảm creativity (acceptable cho tool-call, không cho explanation)

→ Áp dụng **chỉ cho tool-call turn**, không cho explanation turn.

---

## 5. Hướng 4 — Benchmark Ngoài (BFCL, IFEval, Polyvore)

### 5.1 Lý do

Benchmark nội bộ (SFT 70 prompts + fashion-logic 28 items) đủ chọn model nhưng **chưa đủ sâu cho production regression**. Cần benchmark ngoài để:
- So sánh với cộng đồng (leaderboard)
- Tránh overfit vào bộ test nội bộ
- Đo năng lực tổng quát (instruction-following, VLM reasoning)

### 5.2 Kế hoạch chạy (3 giai đoạn)

**Giai đoạn 1 — P0 khách quan:**
1. Chuẩn hóa adapter inference (StylistModelAdapter)
2. Chạy IFEval full
3. Chạy BFCL subset khả thi
4. Chạy Polyvore FITB/AUC cho retrieval pipeline
5. Error analysis: tool args sai, enum sai, format sai, hallucinated IDs

**Giai đoạn 2 — Hội thoại + VLM:**
1. MT-Bench hoặc mini-MT tiếng Việt
2. MMMU hoặc SEED-Bench testmini cho T1/T3/T4
3. T2 chạy text/OCR fallback nhưng tách bảng
4. So sánh T3 với T1/T2/T4 theo từng năng lực

**Giai đoạn 3 — Fashion retrieval mở rộng:**
1. Marqo 7-dataset suite
2. DeepFashion In-shop retrieval subset
3. FashionIQ nếu có feature text-feedback retrieval

### 5.3 Đích reporting

Mỗi benchmark xuất:
```
reports/benchmarks/<bench>/<run_id>/
  ├── predictions.jsonl
  ├── metrics.json
  ├── error_analysis.md
  ├── samples_pass.md
  └── samples_fail.md
```

---

## 6. Hướng 5 — Failure-Driven Data Vòng 2

### 6.1 Nguyên tắc

> "Data mới đi đúng vào chỗ model đang yếu, thay vì tăng data mù." (`Improving_distilled_dataset_plan.md`)

### 6.2 Quy trình

```
1. Fine-tune model hiện tại (đã done — T3 SFT)
2. Chạy benchmark probe (SFT 70 + fashion-logic 28)
3. Gom failure thật:
   • hỏi thiếu info nhưng không hỏi lại
   • gọi tool sai params
   • answer quá dài
   • generic explanation
   • fail topic hiếm (body_shape, season)
4. Tạo thêm data đúng vào failure đó (targeted augmentation)
5. Distill lại + fine-tune vòng 2
```

### 6.3 Hard negatives / counterfactuals cần thêm

| Loại | Ví dụ |
|---|---|
| Prompt thiếu occasion | "Mình muốn outfit đi..." (thiếu dịp) → model phải hỏi lại |
| Prompt mâu thuẫn | "Đi đám cưới nhưng siêu casual" → decline hoặc hỏi lại |
| Budget quá thấp cho yêu cầu sang trọng | "Đi gala nhưng 200k" → relax constraints |
| Body-shape/occasion/style conflict | → tradeoff explain |
| User yêu cầu bịa sản phẩm/outfit_id/size | → decline |
| Prompt quá mơ hồ | → ask missing info |
| Tool params gần đúng nhưng sai 1 field | → contrastive pair học field sensitivity |

### 6.4 Pairwise preference data (cho DPO/KTO sau này)

Cùng prompt:
- **A** = answer verbose, generic (chosen)
- **B** = answer ngắn hơn, đúng hơn, grounded hơn (rejected)

→ Dạy model **phong cách** mong muốn, không chỉ nội dung đúng/sai.

---

## 7. Hướng 6 — Vision Integration thực sự

### 7.1 Vấn đề hiện tại

T3 (Qwen3-VL) có ViT nhưng **chưa train trên image-text pair đủ lớn** → vision capability chưa được exploit. Body Analyzer từ ảnh selfie còn yếu.

### 7.2 Kế hoạch

- **Image-text pair dataset:** ~2K pairs từ catalog (ảnh item + title_vi + description)
- **Body shape từ ảnh:** Cần dataset selfie + label body_shape (ethical concern — có thể dùng silhouette thay face)
- **Outfit Transformer cross-check:** Dùng OT-labse chấm compatibility outfit user up → suggest cải thiện

### 7.3 Domain shift risk

Qwen3-VL train chủ yếu trên ảnh Tây → item VN (áo dài, áo bà ba, ...) có thể OOD. Cần:
- Fine-tune ViT projector (không full ViT)
- Hoặc dùng Gemini Flash caption ảnh → text description vào Qwen (fallback)

---

## 8. Hướng dài hạn (beyond MVP)

| Hướng | Mô tả | Timeline |
|---|---|---|
| **Multi-agent stylist** | Tách planner (T2 text) + explainer (T3 VLM) + critic (LLM-judge) | 1–2 tháng |
| **Personalization Continual Learning** | Incremental LoRA update theo feedback user | 2–3 tháng |
| **Streaming UX** | Streaming generate + early tool-call parse → giảm perceived latency | 1 tháng |
| **Federated fine-tune** | Privacy-preserving: train trên device user | Research |
| **Multi-modal RAG** | Retrieval cả text + image (OutfitTransformer embedding) | 1–2 tháng |
| **Multilingual expand** | Add English/Chinese cho user expat VN | 2–3 tháng |

---

## 9. Định lượng tiềm năng (impact projection)

| Metric | Hiện tại (T3 SFT) | Sau RL (target) | Sau RAG (estimate) | Sau full roadmap |
|---|---:|---:|---:|---:|
| Tool F1 | 0.898 | ≥0.90 | ≥0.90 | ≥0.95 |
| `body_shape_advice` | 0.040 | ≥0.45 | ≥0.60 | ≥0.80 |
| `occasion_formality` | 0.740 | ≥0.80 | ≥0.85 | ≥0.90 |
| Fashion-logic mean | 0.524 | ≥0.55 | ≥0.65 | ≥0.75 |
| Knowledge QA richness | generic | generic | **rich (RAG)** | rich + cited |
| E2E latency | ~5s | ~5s | ~6s (RAG add) | <5s (streaming) |
| Vision capability | weak | weak | weak | **functional** |

→ **Tiềm năng dài hạn:** chuyển từ "stylist demo" thành "stylist production-grade" với grounding rich + vision + personalization.

---

## 10. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| GRPO collapse (reward hack) | `β=0.04` KL drift; monitor `frac_reward_zero_std` |
| RAG context bloat | Chunk size cap; top-K=3; relevance threshold |
| Constrained decoding giảm creativity | Áp dụng chỉ cho tool-call turn |
| Benchmark drift | Pin benchmark version; reproduce baseline quarterly |
| Vision domain shift | Fine-tune ViT projector; fallback Gemini caption |
| Catastrophic forget (RL) | Drift KL; eval ask_back mỗi 50 step; canary benchmark |
| Kaggle 9h limit | `max_steps=500` ≤ 9h; resume từ checkpoint |

---

## 11. Slide gợi ý

1. **Slide 6 hướng phát triển** (§1) — bảng tổng quan + timeline.
2. **Slide GRPO là gì** (§2.2) — so sánh PPO/DPO/GRPO, "vì sao GRPO thắng cho verifiable reward".
3. **Slide reward design** (§2.3) — 6 reward bridge từ scorer.
4. **Slide target sau RL** (§2.7) — bảng delta rõ ràng.
5. **Slide RAG Tầng 1.5** (§3) — sơ đồ kiến trúc, "không mâu thuẫn v3.1".
6. **Slide failure-driven data** (§6) — "data đi đúng điểm yếu".
7. **Slide tiềm năng dài hạn** (§9) — bảng projection từ SFT → RL → RAG → full roadmap.

---

## 12. Câu hỏi Q&A dự kiến (chuẩn bị trước)

| Q | A gợi ý |
|---|---|
| **Vì sao không dùng GPT-4 / Claude làm stylist?** | (1) Cost per request cao; (2) data privacy (user up ảnh); (3) latency; (4) không kiểm soát được tool-call contract; (5) cần localize cho VN. QLoRA 8B local rẻ + private + deterministic. |
| **Vì sao QLoRA thay vì full fine-tune?** | VRAM constraint (T4 16GB free tier). QLoRA 4-bit giảm 4× → chạy được. Quality gần full FT cho task narrow (tool-call + style). |
| **Vì sao Thinking variant thắng Instruct?** | Reasoning head + CoT training → tốt hơn khi parse VN tự nhiên → enum. Tool-call không chỉ copy keyword, cần suy luận "đi làm" → `office`. |
| **RL có làm model forget tiếng Việt không?** | Có risk → drift KL `β=0.04` giữ reference. Eval `ask_back` + sample hội thoại mỗi 50 step. Canary benchmark trước rollout. |
| **Benchmark nội bộ có overfit không?** | Có risk → đó là lý do đề xuất benchmark ngoài (BFCL/IFEval/Polyvore). Benchmark nội đủ chọn model, benchmark ngoài đủ validate production. |
| **Tại sao không train từ scratch model VN?** | (1) Compute không đủ; (2) data hội thoại VN thời trang ít; (3) pretrained Qwen đã có tiếng Việt tốt. Transfer learning + LoRA efficient hơn. |
| **Model có bias không (gender, body shape)?** | Có risk → catalog VN thiên women's. Mitigation: audit catalog coverage, balance data, thêm style neutral. Đã có `BODY_SHAPE` enum 5 dáng cân bằng. |
| **Deploy production thế nào?** | (1) GGUF quantize + llama.cpp server (OpenAI-compatible API); (2) FastAPI wrapper + validation layer; (3) Monitoring parse rate, hallucination rate, latency. |

---

*Hết báo cáo future directions. Trở lại `00_MASTER_REPORT.md` cho tổng kết.*
