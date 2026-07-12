# Slide Deck Outline — Thuyết trình OutfitMatch Stylist Model

**Môn:** Deep Learning (DPL302m) · **Thời lượng:** ~25 phút + 5–10 phút Q&A
**Focus:** Fine-tune stylist model, xử lý dữ liệu, so sánh kiến trúc, tiềm năng tương lai

> Bản outline này là **bản tóm tắt thực thi** — dùng kèm 5 báo cáo chi tiết (00–05) để dựng slide.

---

## Cấu trúc 20 slide gợi ý

### Mở đầu (3 slide)

#### Slide 1 — Title + Giới thiệu nhóm
- **Tiêu đề:** "Fine-tune AI Stylist tiếng Việt cho thị trường thời trang VN — QLoRA trên Qwen3-VL-8B"
- Nhóm 3 dev · DPL302m · Branch `feat/benchmark`
- 1 câu hook: *"Làm sao biến một LLM 8B thành stylist tư vấn outfit cá nhân hóa, gọi tool đúng schema, không bịa sản phẩm — chạy trên GPU 8GB?"*

#### Slide 2 — Bài toán OutfitMatch (1)
- **Input:** text + (optional) ảnh + quiz 5 câu
- **Output:** Top 3–5 outfit + giải thích tiếng Việt + link mua store VN
- Sơ đồ pipeline 4 tầng (Tầng 1 KB → **Tầng 2 Stylist (focus)** → Tầng 3 Retrieval → Tầng 4 Personalization)
- **Highlight Tầng 2:** đây là phần khó nhất + là focus thuyết trình

#### Slide 3 — Vì sao Stylist khó? (4 yêu cầu kỹ thuật)
- Tool-calling đúng schema (sai 1 enum = 0 kết quả)
- Chống hallucination outfit_id (bịa = lừa user)
- Hỏi lại khi thiếu info (anti-pattern phổ biến LLM)
- Tiếng Việt tự nhiên + VRAM ≤ 8–16GB
- **Thông điệp:** đánh giá stylist = benchmark hành vi, không phải eval loss

---

### Phần 1: Xử lý dữ liệu (4 slide) — từ báo cáo 01

#### Slide 4 — Pipeline dữ liệu tổng thể
- Sơ đồ 3 giai đoạn: **G1 Distill (40K→8.8K) → G2 Grounded (2.8K) → G3 Merge (11.6K)**
- 2 nguồn: `stylist_knowledge` CSV + catalog VN thật (5,618 items)
- **Thông điệp:** data-centric AI — chất lượng > số lượng

#### Slide 5 — G1 Distill: Vấn đề raw + Quality Gate
- 7 vấn đề raw (topic skew 81.8%, mixed_script Cyrillic, overlong, near-dup...)
- Quality Gate 4 rule: drop mixed_script / too_long / question_echo
- **Chart:** `quality_gate_drops.png` (đã có sẵn trong `docs/reports/`)
- Loại 4,308 rows (10.69%), clean pool 35,994

#### Slide 6 — G1 Distill: Topic-balance + Behavioral synth
- sqrt weighting: topic nhỏ oversample, topic lớn undersample
- **Chart:** `topic_distribution_raw_vs_distilled.png` (đã có)
- Behavioral synth 1,600 rows × 7 task type (tool_calling, ask_missing, polite_decline...)
- **Thông điệp:** dạy model **hành vi assistant**, không chỉ kiến thức

#### Slide 7 — G2 Grounded + G3 Merge
- Grounded: sinh data từ catalog/retrieval thật (7 task type, target 900 tool_calling_grounded...)
- **Lý do:** giảm distribution mismatch inference-time
- Merge: 11,600 unique rows (1.3M tokens), train 11,252 / eval 348
- **Thông điệp:** "finetune dùng được" ≠ "finetune có vẻ ổn" — khác biệt nằm ở grounding

---

### Phần 2: So sánh kiến trúc (4 slide) — từ báo cáo 02

#### Slide 8 — 4 ứng viên model
- Bảng so sánh: T1 Qwen3-VL Instruct, T2 Qwen3.5-9B, **T3 Qwen3-VL Thinking**, T4 Gemma 4 12B
- Sơ đồ kiến trúc VLM (ViT + LLM) vs text-only
- **Thông điệp:** chọn 4 model để trả lời 3 câu hỏi: (1) vision có giúp? (2) Thinking có hơn Instruct? (3) Google vs Alibaba?

#### Slide 9 — Matrix đánh giá tiêu chí
- Bảng icon 🟢🟡🔴 × tiêu chí (tiếng Việt, tool-calling, vision, VRAM, reasoning)
- Trọng số: Critical / High / Medium
- **Đọc trước benchmark:** T2 + T3 dẫn đầu sơ bộ (8/10), T4 yếu (3/10)

#### Slide 10 — Kết quả benchmark SFT (70 prompts)
- **Bar chart:** Tool F1 / Text sim / Eval loss cho 4 model, T3 highlight
- Bảng rank: **T3 Thinking #1** (Tool F1 0.898, loss 0.594, format 1.0, error 0)
- **Thông điệp:** T3 thắng đồng thời 4/5 metric — ổn định nhất

#### Slide 11 — Subtask insight + "eval loss không quyết định"
- Subtask: `tool_calling` non-grounded — T3 0.857, T4 **0.000** (không trigger tool)
- **Bằng chứng:** T4 loss 0.626 < T2 loss 0.688, nhưng Tool F1 0.653 << 0.877
- **Thông điệp DL:** chọn metric đúng cho downstream task

---

### Phần 3: Fine-tune technique (3 slide) — từ báo cáo 03

#### Slide 12 — QLoRA recipe
- Vì sao QLoRA (4× VRAM reduction)
- Bảng hyperparameter: r=16, α=32, lr=2e-4, nf4, cosine, adamw_8bit, 1 epoch
- Target modules: q/k/v/o + gate/up/down_proj (all-linear)
- **Thông điệp:** recipe cân bằng quality vs VRAM constraint

#### Slide 13 — Kaggle pipeline + tối ưu VRAM
- Sơ đồ: local packaging → Kaggle dataset → kernel T4 → HF Hub
- Multi-account token rotation (2 HF account + 2 Kaggle account để chạy song song)
- VRAM peak T3 local: **6.9GB trên RTX 5060 8GB**
- **Thông điệp:** tinh chỉnh hạ tầng để chạy được trên free tier

#### Slide 14 — Bug đã fix (debug diary)
- Top 3 bug hot: **B9** `device_map={"":0}` fix ValueError bnb 4-bit, **B1** `processor(text=)` fix image source, **B10** trl/vllm stub Windows
- Guardrail 3 lớp: outfit_id + tool_call + size hallucination
- **Thông điệp:** kỹ năng debug thực tế deploy LLM

---

### Phần 4: Đánh giá (3 slide) — từ báo cáo 04

#### Slide 15 — Benchmark đa trục (4 trục)
- Tool correctness / Instruction / VLM reasoning / Fashion downstream
- **Không gộp 1 điểm** — model có thể thắng trục 1, thua trục 4

#### Slide 16 — Fashion-logic benchmark (rule-based, reproducible)
- 2 family × 6 scorer (occasion_formality, body_shape, season, coherence, ask_back, tool_derivation)
- Không cần LLM-judge, deterministic 100%
- Bug scorer fix (alias normalization) — **lesson:** scorer bug che giấu tiến độ thật

#### Slide 17 — Benchmark ngoài đề xuất (BFCL, IFEval, Polyvore)
- Bộ tối thiểu P0: BFCL (tool) + IFEval (instruction) + Polyvore FITB/AUC (fashion)
- Lý do: tránh overfit benchmark nội bộ, so sánh cộng đồng

---

### Phần 5: Tương lai (2 slide) — từ báo cáo 05

#### Slide 18 — GRPO verifiable-reward RL
- Vì sao RL sau SFT (body_shape_advice chỉ 0.04)
- Vì sao GRPO (verifiable reward, không cần RM)
- 6 reward function + target sau RL (mean ≥ 0.55)
- **Thông điệp:** RL = SFT + tối ưu hành vi đúng

#### Slide 19 — 6 hướng phát triển
- Bảng: GRPO RL / RAG Tầng 1.5 / Constrained decoding / Benchmark ngoài / Failure-driven data / Vision integration
- Timeline + impact + risk
- **Định lượng tiềm năng:** SFT 0.524 → RL 0.55 → RAG 0.65 → full roadmap 0.75

#### Slide 20 — Tổng kết + Q&A
- 3 takeaways: (1) Data-centric > model-centric; (2) Metric đúng cho downstream; (3) SFT + RL + RAG complementary
- HF repo public (4 adapter)
- Cảm ơn + Q&A

---

## Chart/Visual đã có sẵn (dùng ngay)

| Chart | File | Dùng cho slide |
|---|---|---|
| Topic distribution raw vs distilled | `docs/reports/stylist_knowledge_qwen35_under10k/topic_distribution_raw_vs_distilled.png` | 6 |
| Quality gate drops | `docs/reports/stylist_knowledge_qwen35_under10k/quality_gate_drops.png` | 5 |
| Answer length histogram | `docs/reports/stylist_knowledge_qwen35_under10k/answer_length_hist_raw_vs_distilled.png` | 6 |
| Prompt style distribution | `docs/reports/stylist_knowledge_qwen35_under10k/prompt_style_raw_vs_distilled.png` | 6 |
| Family size buckets | `docs/reports/stylist_knowledge_qwen35_under10k/family_size_buckets_raw_vs_distilled.png` | 6 |
| LlamaFactory screenshot | `docs/reports/stylist_knowledge_qwen35_under10k/llamafactory_screenshot.png` | 13 |
| Mermaid architecture diagram | `docs/presentation/SO_DO_MERMAID.md` | 2 |

## Chart cần tự tạo (gợi ý)

| Chart | Data source | Tool |
|---|---|---|
| Bar chart 4 model SFT benchmark | `04_EVALUATION.md` §2.4 | matplotlib / Excel |
| Radar chart 4 model × 6 scorer fashion-logic | `gpu_T{1,2,3}_rescored.json` | matplotlib |
| Pipeline diagram 3 giai đoạn data | `01_DATA_PIPELINE.md` §1 | draw.io / mermaid |
| VLM vs text-only architecture | `02_MODEL_COMPARISON.md` §1.2 | draw.io |
| RL target projection | `05_FUTURE_DIRECTIONS.md` §9 | matplotlib |

---

## Demo gợi ý (nếu có thời gian)

```bash
# 1. Load T3 adapter + generate 1 prompt
uv run python scripts/stylist/run_gpu_benchmark.py --model-id T3 --adapter post-RL

# 2. Show validation layer block hallucinated outfit_id
uv run python -c "from outfitmatch.stylist.validation import validate_response; print(validate_response('OF_00001 và OF_99999', {'OF_00001'}))"

# 3. Show tool-call parser
uv run python -c "from outfitmatch.stylist.tools import parse_tool_call_text; print(parse_tool_call_text('<tool_call>{\"name\":\"search_outfits\",\"arguments\":{\"occasion\":\"office\"}}</tool_call>'))"
```

---

## Tips thuyết trình DL

1. **Mở đầu bằng vấn đề, không phải giải pháp** — giám khảo muốn biết "vì sao cần LLM stylist?" trước khi nghe "chọn model nào".
2. **Highlight Deep Learning concept** mỗi slide: QLoRA (§12), distillation (§5), reward shaping (§18), distribution mismatch (§7).
3. **Dùng chart thật, không stock photo** — chart từ repo tăng credibility.
4. **Nói rõ trade-off** — không có model nào hoàn hảo. T3 thắng nhưng T2 mean fashion-logic cao hơn → cho thấy tư duy critically.
5. **Q&A preparation** — 8 câu hỏi dự kiến trong `05_FUTURE_DIRECTIONS.md` §12.
6. **Demo code ngắn** (nếu được) — chạy 1 tool-call parse live tăng ấn tượng.

---

*Hết outline. Tất cả báo cáo chi tiết trong cùng thư mục `docs/presentation/final_slides/`.*
