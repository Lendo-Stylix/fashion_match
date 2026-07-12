# Báo cáo tổng hợp — Fine-tune Stylist Model cho OutfitMatch

**Dự án:** OutfitMatch — Body & Occasion-Aware Fashion Recommender (DPL302m)
**Phạm vi:** Tầng 2 — Conversational AI Stylist (Qwen3-VL-8B + Qwen3.5-9B + Gemma 4 12B)
**Mục đích:** Báo cáo tổng quan phục vụ thuyết trình cuối kỳ môn Deep Learning (năm 3, ngành AI)
**Tác giả:** Nhóm OutfitMatch · **Ngày:** 12/07/2026

> Tài liệu này là **báo cáo gốc (master)**. Chi tiết chuyên sâu nằm trong 5 báo cáo thành phần (01–05) cùng thư mục, mỗi báo cáo tương ứng 1 mảng chính của bài thuyết trình.

---

## 0. TL;DR — Tóm tắt cho người đọc nhanh

| Câu hỏi | Câu trả lời |
|---|---|
| **Làm gì?** | Fine-tune một mô hình ngôn ngữ lớn (LLM/VLM) thành *AI Stylist tiếng Việt* cho thị trường thời trang VN — biết hiểu intent, gọi tool `search_outfits`, hỏi lại khi thiếu thông tin, giải thích outfit bằng tiếng Việt tự nhiên, không bịa sản phẩm. |
| **Vì sao khó?** | (1) Thiếu dữ liệu hội thoại tiếng Việt chất lượng cao trong domain thời trang; (2) cần chạy được trên GPU thấp cấp (8–16GB VRAM) để demo; (3) phải đảm bảo **chống hallucination** (không bịa `outfit_id`, `size`, giá); (4) cần **tool-calling đúng schema** thay vì chỉ "nói hay". |
| **Mô hình nào?** | So sánh **4 ứng viên**: Qwen3-VL-8B Instruct (T1), Qwen3.5-9B (T2, text-only), Qwen3-VL-8B Thinking (T3), Gemma 4 12B IT (T4). Kết: **T3 Qwen3-VL-8B Thinking** thắng toàn diện. |
| **Phương pháp?** | **QLoRA SFT** (4-bit NF4, LoRA r=16/α=32) trên Unsloth → Kaggle T4. Sau đó chuẩn bị **GRPO (RL với verifiable reward)** để cải thiện fashion-logic. |
| **Dữ liệu?** | Pipeline 3 giai đoạn: **(G1) Distill 40K→8.8K** (quality gate + topic-balanced), **(G2) Grounded 2.8K** (sinh từ catalog/retrieval thật), **(G3) Merge 11.6K** → train. |
| **Kết quả chính?** | T3 đạt **Tool F1 = 0.898, Format compliance = 1.0, Eval loss = 0.594** (thấp nhất 4 model). Trên fashion-logic benchmark sau scorer-fix: T3 mean = **0.524**, cần RL để vượt T2 (0.543). |
| **Tương lai?** | GRPO verifiable-reward RL, mở rộng benchmark ngoài (BFCL/IFEval/Polyvore), RAG knowledge injection, constrained decoding, fine-tune vòng 2 theo failure-driven data. |

---

## 1. Bối cảnh & Vị trí Stylist trong kiến trúc OutfitMatch

### 1.1 Vị trí trong pipeline 4 tầng (v3.1-lite)

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER: text + (optional) ảnh + quiz onboarding (5 câu)              │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TẦNG 2 — STYLIST (Qwen3-VL-8B + LoRA)  ←──── BÁO CÁO NÀY TẬP TRUNG │
│  1. Parse intent (VN → enum: occasion/style/body_shape/...)         │
│  2. Hỏi lại nếu thiếu occasion/budget (ask_missing_info)            │
│  3. Gọi <tool_call>search_outfits(...)</tool_call> đúng schema      │
│  4. Giải thích outfit kết quả retrieval bằng tiếng Việt              │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TẦNG 3 — RETRIEVAL (Qdrant items + Graph Traversal)                │
│  seed filter (top/dress) → clique traversal → OutfitRecord          │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TẦNG 4 — PERSONALIZATION (Quiz → rule-based rerank + size suggest) │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
                     Top 3–5 outfit + giải thích VI
```

### 1.2 Tại sao Stylist là thành phần "khó nhất"?

| Yêu cầu kỹ thuật | Lý do |
|---|---|
| **Tool-calling đúng schema** | Sai 1 enum `occasion` → retrieval sai hoàn toàn (0 kết quả). Đây là điểm chặn E2E, không phải "nói hay". |
| **Chống hallucination outfit_id** | Model phải chỉ trích dẫn `OF_NNNNN` có thật trong KB; bịa ID = lừa user. |
| **Hỏi lại khi thiếu info** | Không được hallucinate `occasion` khi user chưa nói. Đây là **anti-pattern phổ biến** của LLM. |
| **Tiếng Việt tự nhiên** | Lời giải thích phải nghe như tư vấn viên VN, không phải bản dịch máy. |
| **Multimodal (optional)** | User có thể gửi ảnh selfie → Body Analyzer. |
| **VRAM ≤ 8–16GB** | Demo trên Kaggle T4 / laptop GPU; không đòi A100. |

→ Kết luận: **Stylist phải được đánh giá bằng benchmark hành vi (tool-call correctness, hallucination rate) chứ KHÔNG chỉ eval loss hoặc độ tự nhiên ngôn ngữ.** Đây là nhận định then chốt chi phối toàn bộ design decision.

---

## 2. Bốn ứng viên mô hình — Tổng quan so sánh

| Thuộc tính | **T1** Qwen3-VL-8B Instruct | **T2** Qwen3.5-9B | **T3** Qwen3-VL-8B Thinking ✅ | **T4** Gemma 4 12B IT |
|---|---|---|---|---|
| **Kiến trúc** | VLM (ViT + LLM) | Text-only Transformer | VLM (ViT + LLM) + reasoning | Text Transformer |
| **Params** | 8B | 9B | 8B | 12B |
| **Vision input** | ✅ | ❌ | ✅ | ❌ |
| **Tool-calling native** | ✅ | ✅ | ✅ | ❌ (prompt hack) |
| **VRAM 4-bit** | ~4–5GB | ~5–6GB | ~4–5GB | ~7–8GB |
| **Tiếng Việt** | Khá | Xuất sắc | Khá | Yếu |
| **Unsloth support** | ✅ | ✅ | ✅ | ✅ |
| **Điểm kiến trúc (phân tích sơ bộ)** | 8/10 | 8/10 | 8/10 | 3/10 |
| **Vai trò sau benchmark** | Fallback ổn định | Text-only fallback | **Production primary** | Explanation-only candidate |

> **Lý do chọn 4 model này:** (1) tất cả đều ≤ 12B → vừa T4 free tier; (2) có Qwen text-only (T2) và Qwen VLM (T1/T3) để so sánh "vision có giúp gì không?"; (3) Gemma 4 (Google) để so sánh model family; (4) Thinking variant (T3) có khả năng reasoning khi parse tiếng Việt → enum.

---

## 3. Quy trình fine-tune tổng thể (Sơ đồ end-to-end)

```
┌──────────────────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 1 — XỬ LÝ DỮ LIỆU (Data Pipeline)                          │
│ ┌───────────────────┐    ┌──────────────────┐    ┌─────────────────┐ │
│ │ stylist_knowledge │ ──►│  G1: DISTILL     │ ──►│ 8.8K rows       │ │
│ │ 40,302 rows raw   │    │  quality gate +  │    │ (7.2K knowledge │ │
│ │ (CSV, mixed qual.)│    │  topic-balance   │    │  + 1.6K behav.) │ │
│ └───────────────────┘    └──────────────────┘    └─────────────────┘ │
│                                                       │              │
│ ┌───────────────────┐    ┌──────────────────┐        ▼              │
│ │ Catalog VN thật   │ ──►│  G2: GROUNDED    │ ──► 2.8K rows         │
│ │ 5,618 items +     │    │  scenario bank + │    (tool_calling_    │
│ │ retrieval runtime │    │  GPT-OSS teacher │     grounded + ...)   │
│ └───────────────────┘    └──────────────────┘        │              │
│                                                         ▼            │
│                                    G3: MERGE → 11.6K unique rows     │
│                                    (1.3M tokens Qwen)                │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 2 — FINE-TUNE (QLoRA SFT)                                  │
│  Unsloth + QLoRA (4-bit NF4) · Kaggle T4                             │
│  LoRA r=16, α=32, target=q/k/v/o/gate/up/down_proj                   │
│  lr=2e-4, cosine, warmup 0.03, 1 epoch (704 steps)                   │
│  → 4 adapters (T1/T2/T3/T4) uploaded lên HF                         │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 3 — ĐÁNH GIÁ (Benchmark)                                   │
│  (a) SFT benchmark 70 prompts: Tool F1 + text sim + format + error   │
│  (b) GPU fashion-logic benchmark 28 items × 6 scorers (rule-based)   │
│  → T3 thắng SFT benchmark; T3 cần RL để vượt T2 trên fashion-logic   │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 4 — RL (đang triển khai)                                   │
│  GRPO + QLoRA, reward = 6 deterministic scorers (verifiable reward)  │
│  → T3 cải thiện occasion_formality + body_shape_advice               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Kết quả nổi bật (Highlights)

### 4.1 SFT Benchmark — 4 model trên 70 held-out prompts

| Rank | Model | Tool F1 | Text sim | Format | Error | Eval loss |
|---:|---|---:|---:|---:|---:|---:|
| **1** | **T3 Qwen3-VL-8B Thinking** ✅ | **0.898** | **0.552** | **1.000** | **0** | **0.594** |
| 2 | T2 Qwen3.5-9B BNB4 | 0.878 | 0.488 | 1.000 | 0 | 0.688 |
| 3 | T1 Qwen3-VL-8B Instruct | 0.857 | 0.544 | 1.000 | 0 | 0.603 |
| 4 | T4 Gemma 4 12B IT | 0.653 | 0.535 | 0.971 | 0 | 0.626 |

**Đọc kết quả:** T3 thắng **đồng thời 4/5 metric** (Tool F1, text sim, format, eval loss). T3 không nhất mọi subtask nhưng ổn định nhất → phù hợp production. Gemma yếu ở `tool_calling` non-grounded (0.000) vì model trả lời prose thay vì `<tool_call>`.

### 4.2 Fashion-Logic Benchmark (GPU, 28 items × 6 scorers, sau scorer-fix)

| Task | T1 | T2 | **T3** | Priority RL |
|---|---:|---:|---:|---|
| `occasion_formality` | 0.607 | 0.585 | **0.740** | 🟡 P1 |
| `body_shape_advice` | 0.000 | 0.050 | **0.040** | 🔴 **P0** (quá generic) |
| `season_advice` | 0.258 | 0.333 | **0.383** | 🟡 P1 |
| `coherence` | 0.500 | 1.000 | 0.500 | 🟡 P2 |
| `ask_back` | 0.667 | 0.667 | 0.667 | 🟢 P3 |
| `tool_call_derivation` | 0.812 | 0.788 | 0.763 | 🟢 P3 |
| **Overall mean** | 0.462 | **0.543** | **0.524** | — |

**Insight:** T3 mạnh về occasion (0.74) và tool-call (0.76) nhờ SFT, nhưng `body_shape_advice` gần 0 → RL cần tập trung dạy model dùng keyword canonical (`chân váy A`, `high waist`, ...).

### 4.3 Hugging Face artifacts (public)

| Adapter | HF Repo |
|---|---|
| **T3 Thinking (primary)** | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora` |
| T2 Qwen3.5 BNB4 | `Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora` |
| T1 Instruct | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-instruct-lora` |
| T4 Gemma | `Nhat-Quang/outfitmatch-stylist-final-gemma4-12b-it-lora` |

Mỗi repo có: `adapter_model.safetensors`, `adapter_config.json`, tokenizer/chat template, `training_summary.json`, `trainer_state.json`, README benchmark summary.

---

## 5. Bài học kỹ thuật then chốt (Lessons Learned)

| # | Bài học | Chi tiết |
|---|---|---|
| **L1** | **Đánh giá bằng hành vi, không phải loss** | Eval loss không đo tool-call correctness. T4 Gemma có loss 0.626 (khá) nhưng Tool F1 chỉ 0.653 vì không trigger tool-call. |
| **L2** | **Data quality > data quantity** | Distill từ 40K → 8.8K nhưng "sắc" hơn (drop mixed-script, near-duplicate, overlong). Lượng tăng mù không giúp — phải đúng distribution inference. |
| **L3** | **Ground vào runtime thật** | Sinh data từ catalog/retrieval thật (G2 grounded) giúp model học đúng distribution inference-time, khác biệt lớn giữa "finetune có vẻ ổn" và "finetune dùng được". |
| **L4** | **Tool-call là contract cứng** | Phải freeze wire format `<tool_call>{...}</tool_call>` ở code + parser + training data. Nếu drift → model sinh sai schema. |
| **L5** | **Chống hallucination = guardrail code + training data** | Cần cả hai: validation.py block ID giả + training data có negative samples `polite_decline_anti_hallucination`. |
| **L6** | **Thinking variant > Instruct cho reasoning** | T3 Thinking thắng T1 Instruct ở `tool_calling` non-grounded (0.857 vs 0.786) nhờ khả năng suy luận VN→enum. |
| **L7** | **Multimodal là feature cốt lõi, không phải bonus** | T3 (VLM) được chọn dù T2 (text-only) mean cao hơn fashion-logic, vì stylist nhận ảnh user là USP của sản phẩm. |
| **L8** | **VRAM 8GB đủ QLoRA 8B nếu dùng đúng pattern** | `device_map={"":0}` (không `"auto"`) + bnb 4-bit + gradient checkpointing → T3 chạy được trên RTX 5060 laptop. |
| **L9** | **RL verifiable-reward > reward model cho task có ground truth** | 6 scorer trong `fashion_eval.py` đủ làm reward → không cần RM tốn kém, reproducible 100%. |
| **L10** | **Scorer bug có thể che giấu tiến độ thật** | Bug alias normalization (`smart casual` ≠ `smart_casual`) khiến occasion_formality = 0 trên cả 3 model. Fix → +0.2 mean ngay lập tức. |

---

## 6. Hướng phát triển tương lai (chi tiết ở báo cáo 05)

1. **GRPO verifiable-reward RL** cho T3 — mục tiêu mean ≥ 0.55, `body_shape_advice` ≥ 0.45.
2. **Mở rộng benchmark ngoài:** BFCL (tool-calling), IFEval (instruction), Polyvore FITB/AUC (fashion downstream).
3. **RAG knowledge injection** — thêm tầng 1.5 `fashion_kb` (Qdrant) cho 35K clean knowledge rows, refit LoRA thuần behavior.
4. **Constrained decoding + parser repair** cho tool-call contract.
5. **Failure-driven data vòng 2** — gom failure từ benchmark probe → tạo data đúng vào điểm yếu.
6. **Tích hợp vision** thực sự (T3 đã có ViT, cần image-text pair data đủ lớn).

---

## 7. Cấu trúc bộ báo cáo thuyết trình

| File | Nội dung | Slide gợi ý |
|---|---|---|
| `00_MASTER_REPORT.md` | Báo cáo tổng hợp này (đọc đầu) | 1–2 slide tổng quan |
| `01_DATA_PIPELINE.md` | Chi tiết xử lý dữ liệu fine-tune (G1 distill, G2 grounded, G3 merge) | 3–4 slide |
| `02_MODEL_COMPARISON.md` | So sánh kiến trúc & đánh giá 4 model | 4–5 slide |
| `03_FINETUNE_DETAILS.md` | Chi tiết kỹ thuật fine-tune (QLoRA recipe, Kaggle pipeline, bugs đã fix) | 3–4 slide |
| `04_EVALUATION.md` | Chi tiết benchmark SFT + fashion-logic + mở rộng đề xuất | 3–4 slide |
| `05_FUTURE_DIRECTIONS.md` | Tiềm năng & hướng phát triển (RL, RAG, benchmark ngoài) | 2–3 slide |

**Tổng thời lượng gợi ý:** 20–25 phút thuyết trình + 5–10 phút Q&A.

---

## 8. Nguồn tài liệu tham chiếu (trong repo)

- Kiến trúc canonical: `Kien_truc_v3.1.md`, `docs/ARCHITECTURE.md`
- Phân tích model: `docs/STYLIST_MODEL_ANALYSIS.md`
- Báo cáo SFT benchmark: `docs/reports/stylist_final_qlora_benchmark/DETAILED_REPORT.md`
- Báo cáo benchmark mở rộng: `docs/reports/stylist_benchmark_expansion/DETAILED_REPORT.md`
- Báo cáo distill: `docs/reports/stylist_knowledge_qwen35_under10k/DETAILED_REPORT.md`
- Chiến lược RL: `docs/reports/stylist_benchmark_expansion/RL_STRATEGY.md`
- Feature log: `docs/feature.md`
- Code nguồn: `src/outfitmatch/stylist/`, `scripts/stylist/`

---

*Hết báo cáo tổng hợp. Đọc tiếp `01_DATA_PIPELINE.md` để đi sâu vào xử lý dữ liệu.*
