# 04 — Đánh giá (Evaluation) Stylist Model

**Phạm vi:** Benchmark SFT, fashion-logic benchmark, benchmark mở rộng đề xuất
**Mục tiêu slide:** Cho giám khảo DL thấy **methodology đánh giá đa trục** — không chỉ 1 metric, mà đo đúng từng năng lực (tool-calling, instruction, VLM reasoning, fashion downstream).

---

## 1. Triết lý đánh giá — Đo đúng năng lực downstream

### 1.1 Vấn đề với đánh giá LLM truyền thống

| Metric truyền thống | Hạn chế cho OutfitMatch |
|---|---|
| Eval loss / perplexity | Không đo hành vi sau generation |
| BLEU / ROUGE | Không phù hợp hội thoại |
| Text similarity (cosine) | Câu đúng có thể diễn đạt khác reference → false low |
| LLM-as-judge đơn điểm | Có bias, đắt, không reproducible |
| Human eval | Chậm, không scalable |

### 1.2 Nguyên tắc đánh giá OutfitMatch (4 trục)

```
TRỤC 1: TOOL CORRECTNESS        ← Critical (sai = retrieval vỡ)
  • Tool F1 (field/value match)
  • Format compliance
  • Tool-call parse rate
  • Enum accuracy per field

TRỤC 2: INSTRUCTION/CHAT QUALITY  ← High
  • IFEval strict/loose accuracy
  • Ask-missing-info accuracy
  • MT-Bench / mini-MT-Bench tiếng Việt

TRỤC 3: VISION-LANGUAGE REASONING  ← Medium (cho T1/T3)
  • MMMU / SEED-Bench accuracy
  • Body Analyzer từ ảnh selfie

TRỤC 4: FASHION DOWNSTREAM QUALITY  ← High (rubric grading)
  • Polyvore FITB accuracy ≥ 55%
  • Polyvore Compatibility AUC ≥ 0.85
  • Graph retrieval recall@5
```

→ **Không gộp 4 trục thành 1 điểm** — model có thể thắng trục 1 nhưng thua trục 4.

---

## 2. Benchmark 1: SFT Benchmark (70 held-out prompts)

### 2.1 Setup

- **70 prompts** held-out (không trong train set), stratified theo task type.
- Cả 4 model (T1/T2/T3/T4) chạy cùng prompt + cùng reference.
- Load bằng Unsloth, attach adapter, generate ở `temperature=0.0` (deterministic).

### 2.2 Phân bố 70 prompts

| Task type | Số mẫu |
|---|---:|
| `stylist_knowledge` | 42 |
| `tool_calling_grounded` | 5 |
| `tool_calling` (non-grounded) | 2 |
| `ask_missing_info` | 3 |
| `ask_missing_info_grounded` | 2 |
| `recommend_explain_grounded` | 3 |
| `recommend_explain` | 2 |
| `body_fit_grounded` | 3 |
| `polite_decline_anti_hallucination` | 3 |
| `multi_turn` | 2 |
| Khác | 3 |

### 2.3 Metric

| Metric | Ý nghĩa | Quan trọng? |
|---|---|---|
| `mean_tool_call_f1` | F1 trên field/value tool-call so reference | **Critical** — đo E2E retrieval |
| `mean_text_similarity` | Độ gần generated text vs reference | Hữu ích nhưng không thay thế judge |
| `format_compliance_rate` | Tỷ lệ output đúng tool contract | **Hard gate** |
| `error_count` | Lỗi generate/load/eval | Lower = better |

### 2.4 Kết quả

| Rank | Model | Tool F1 ↑ | Text sim ↑ | Format ↑ | Error ↓ |
|---:|---|---:|---:|---:|---:|
| **1** | **T3 Thinking** ✅ | **0.898** | **0.552** | **1.000** | **0** |
| 2 | T2 Qwen3.5 | 0.877 | 0.488 | 1.000 | 0 |
| 3 | T1 Instruct | 0.857 | 0.544 | 1.000 | 0 |
| 4 | T4 Gemma | 0.653 | 0.535 | 0.971 | 0 |

### 2.5 Subtask insight (quan trọng cho DL)

| Subtask | T1 | T2 | **T3** | T4 | Đọc |
|---|---:|---:|---:|---:|---|
| `tool_calling_grounded` (prompt rõ) | 0.886 | **0.943** | 0.914 | 0.914 | T2 mạnh khi scaffold rõ |
| `tool_calling` (VN tự nhiên) | 0.786 | 0.714 | **0.857** | **0.000** | T3 reasoning thắng; T4 không trigger |
| `stylist_knowledge` sim | 0.383 | **0.412** | 0.387 | 0.403 | T2 tiếng Việt tốt nhất |
| `recommend_explain` sim | 0.646 | 0.698 | **0.698** | 0.126 | T4 yếu giải thích grounded |

→ **Insight:** Thinking variant (T3) có lợi thế rõ ở task cần **reasoning** (tool_calling non-grounded: parse VN tự nhiên → enum). Khi prompt đã scaffold rõ (grounded), cả 4 đều khá →差别 nằm ở bước suy luận.

---

## 3. Benchmark 2: Fashion-Logic (Rule-based, Reproducible)

### 3.1 Vì sao cần benchmark này?

**Vấn đề SFT benchmark:** Đo tool-call nhưng không đo **tri thức thời trang** (occasion→formality, body shape→advice, season→fabric) và **logic thời trang** (coherence, ask-back, tool derivation).

**Giải pháp:** `src/outfitmatch/stylist/fashion_eval.py` — benchmark **không cần LLM-judge**, scorer 100% deterministic nền trên `vocab.py`.

### 3.2 Cấu trúc — 2 family, 6 item bank

#### Family A: Knowledge (tri thức)

| Item bank | Số item | Ground truth | Scorer | Metric |
|---|---:|---|---|---|
| `OCCASION_FORMALITY_ITEMS` | 9 dịp | `formalities_for_occasion(occ)` từ vocab | `score_occasion_formality` | precision/recall/F1 + phạt formality sai |
| `BODY_SHAPE_ADVICE_ITEMS` | 5 dáng | curated positive/negative cues | `score_body_shape_advice` | recall positives − ½ × negatives |
| `SEASON_ADVICE_ITEMS` | 4 mùa | curated fabric/layering cues | `score_season_advice` | recall positives − ½ × negatives |

#### Family B: Logic (reasoning)

| Item bank | Số item | Ground truth | Scorer | Metric |
|---|---:|---|---|---|
| `COHERENCE_ITEMS` | 4 combo | `formality_span_ok` (tolerance=1) | `score_coherence_judgment` + `detect_verdict` | binary accuracy |
| `ASK_BACK_ITEMS` | 3 prompt thiếu dịp | phải hỏi lại, không hallucinate occasion | `score_ask_back` | 1.0 nếu ask-back & không hallucinate |
| `TOOL_CALL_DERIVATION_ITEMS` | 3 profile | reference tool-call hợp schema | `score_tool_call_derivation` | F1 × (enum_valid ? 1 : 0) |

### 3.3 Ưu điểm vs benchmark ngoài

| Ưu điểm | Chi tiết |
|---|---|
| **Reproducible 100%** | Không phụ thuộc GPT/Gemini judge → chạy lại cho cùng kết quả |
| **Fit `generate_fn` contract** | Cùng adapter contract với `stylist.benchmark.evaluate_dataset` |
| **Khớp invariant v3.1** | Enum từ `vocab.py`, tool schema từ `tools.py` → nếu KB/schema đổi, benchmark auto phát hiện |
| **Anti-hallucination** | `score_ask_back` bắt behavior "bịa occasion khi user chưa nói" |

### 3.4 Kết quả GPU benchmark (28 items × 6 scorers, sau scorer-fix rev 3)

| Task | T1 | T2 | **T3** | Priority RL |
|---|---:|---:|---:|---|
| `occasion_formality` | 0.607 | 0.585 | **0.740** | 🟡 P1 |
| `body_shape_advice` | 0.000 | 0.050 | **0.040** | 🔴 **P0** (quá generic) |
| `season_advice` | 0.258 | 0.333 | **0.383** | 🟡 P1 |
| `coherence` | 0.500 | **1.000** | 0.500 | 🟡 P2 |
| `ask_back` | 0.667 | 0.667 | 0.667 | 🟢 P3 |
| `tool_call_derivation` | **0.812** | 0.788 | 0.763 | 🟢 P3 |
| **Overall mean** | 0.462 | **0.543** | 0.524 | — |
| Eval latency (28 items) | 407s | 712s | 509s | — |

### 3.5 Bug scorer đã fix (rev 2 → rev 3) — lesson quan trọng

**Vấn đề:** Scorer ban đầu match exact string (`smart_casual` phải y hệt). Model output dùng:
- "smart casual" (space) → không match
- "smart-casual" (hyphen) → không match
- "business casual" (không thuộc enum) → không match
- "semi-formal" (không thuộc enum) → không match

→ `occasion_formality` = 0 trên cả 3 model (rev 2).

**Fix (rev 3):** Thêm alias normalization trong `score_occasion_formality`:
```python
VARIANTS = {
    "smart_casual": ["smart_casual", "smart casual", "smart-casual"],
    "semi_formal": ["semi_formal", "semi formal", "semi-formal"],
    ...
}
```

**Kết quả sau fix:** `occasion_formality` tăng 0.00 → **0.74 (T3)**, mean tăng +0.20–0.24.

**Bài học DL:** Scorer bug có thể **che giấu tiến độ thật**. Phải audit kỹ scorer trước khi kết luận model yếu.

### 3.6 Failure mode analysis (T3 trên `occasion_formality`)

**Prompt:** "Cho dịp đi làm (`office`), mức độ trang trọng nào phù hợp?"

**T3 output (rev 2, fail):** *"Mức độ trang trọng phù hợp cho môi trường văn phòng là **smart casual hoặc business casual**..."*

**Scorer rev 2:** Tìm enum trong `{athletic, casual, smart_casual, formal}`.
- "business casual" → không match
- "smart casual" (space) → không match
- "smart-casual" (hyphen) → không match

**3 failure concretely thấy:**
1. **Vocabulary mismatch** — model dùng "business casual", "semi-formal" không thuộc `FORMALITY` enum
2. **Hyphen normalization** — "smart-casual" ≠ "smart_casual"
3. **Background default** — model sợ sai nên liệt kê range ("smart casual hoặc casual") → giải thích đúng nhưng enum mismatch

→ **RL reward R1 phải incent model dùng canonical `smart_casual` (snake_case).**

### 3.7 Test coverage

- `tests/test_stylist_fashion_eval.py`: **34 test, 98% coverage**
- Full suite: `uv run pytest -q` → **407 passed**
- `ruff check` + `ruff format --check` + `mypy` sạch

---

## 4. Benchmark 3: Đề xuất mở rộng (ngoài dự án)

> **Phạm vi slide:** Cho giám khảo thấy hiểu biết về **state-of-the-art benchmark** trong cộng đồng LLM/VLM/fashion.

### 4.1 Nhóm A — Tool-calling / agentic (P0)

| Benchmark | Tác vụ | Metric | Ưu tiên | Lý do |
|---|---|---|---|---|
| **BFCL** (Berkeley Function Calling) | Function calling, serial/parallel, AST eval, abstain, stateful multi-step | AST match / executable correctness | **P0** | Gần nhất production: khi nào gọi `search_outfits`, đúng enum/schema |
| **StableToolBench** | Tool learning quy mô lớn, virtual API + cache | SoPR, SoWR | P1 | Tool/API nhiều bước, tránh benchmark drift |

### 4.2 Nhóm B — Instruction / chat (P0/P1)

| Benchmark | Tác vụ | Metric | Ưu tiên |
|---|---|---|---|
| **IFEval** | Instruction-following verify tự động, 500 prompts × 25 loại | Strict/loose accuracy | **P0** |
| **MT-Bench** / mini-MT tiếng Việt | Multi-turn chat, LLM-judge | Judge score / win-rate | P1 |
| **Arena-Hard-Auto** | 500 prompt khó, LLM-judge | Win-rate | P2 |

### 4.3 Nhóm C — VLM reasoning (P1, cho T1/T3)

| Benchmark | Tác vụ | Metric | Ưu tiên |
|---|---|---|---|
| **MMMU** | Multimodal college-level, 11.5K Q, 6 disciplines | Accuracy | P1 |
| **SEED-Bench** | 24K MCQ, 27 dimensions (single/multi-image, video, interleaved) | Accuracy per dimension | P1 |
| **MathVista** | Visual math reasoning, 6.1K examples | Accuracy | P2 |

> **Lưu ý công bằng:** T2 (text-only) không chạy VLM benchmark trực tiếp — phải dùng OCR/caption fallback, tách bảng rank riêng.

### 4.4 Nhóm D — Fashion downstream (P0)

| Benchmark | Tác vụ | Metric | Ưu tiên |
|---|---|---|---|
| **Polyvore Outfits FITB + Compat AUC** | Fill-in-blank outfit completion, compatibility prediction | FITB accuracy, Compat AUC | **P0** |
| **DeepFashion** | Attribute prediction, consumer-to-shop, in-shop retrieval | Recall@K, accuracy | P1 |
| **FashionIQ** | Natural language feedback retrieval | Recall@K composed retrieval | P2 |
| **Marqo FashionCLIP/SigLIP suite** | Text-to-image, category/sub-category-to-product trên 7 dataset | Recall@1/10, MRR | P1 |

### 4.5 Bộ tối thiểu đề xuất (P0) cho báo cáo final

| Benchmark | Lý do must-have | Output báo cáo |
|---|---|---|
| **BFCL** | Tool-calling là năng lực lõi stylist | Tool-call accuracy per model |
| **IFEval** | Tuân thủ instruction/schema khách quan | Strict/loose accuracy |
| **Polyvore FITB/AUC** | Chất lượng outfit downstream | FITB acc + Compat AUC |

> Nếu thời gian hạn chế → chạy **BFCL + IFEval + Polyvore** trước. Đây là bộ tối thiểu đủ chứng minh "model không chỉ nói hay mà còn gọi tool đúng + tạo outfit có compatibility đo được".

---

## 5. Harness đánh giá chung (thiết kế)

### 5.1 StylistModelAdapter interface

```python
class StylistModelAdapter:
    name: str
    supports_images: bool
    supports_tools: bool

    def generate_text(self, messages, *, max_tokens, temperature) -> str: ...
    def generate_with_images(self, messages, image_paths, *, max_tokens, temperature) -> str: ...
    def generate_tool_call(self, messages, tools, *, max_tokens, temperature) -> dict | str: ...
```

### 5.2 Cấu hình chạy công bằng

| Nhóm benchmark | Temperature | Decoding | Judge |
|---|---:|---|---|
| Tool/IFEval | 0.0 | deterministic | parser/objective metric |
| Chat judge | 0.2 hoặc 0.0 | fixed max tokens | Gemini/GPT judge + rubric cố định |
| VLM MCQ | 0.0 | answer letter only | exact match |
| Retrieval/fashion | N/A | deterministic retrieval config | objective Recall/AUC/MRR |

### 5.3 Format output benchmark

```
reports/benchmarks/<benchmark>/<run_id>/
  ├── predictions.jsonl
  ├── metrics.json
  ├── error_analysis.md
  ├── samples_pass.md
  └── samples_fail.md
```

Metrics tổng hợp (1 row per run):
```
model, benchmark, split, metric_name, metric_value, n_samples, date, commit_sha
```

---

## 6. Regression Guard — Đảm bảo không退化

### 6.1 Khi nào chạy regression?

- **Trước khi thay adapter** production (canary benchmark)
- **Sau mỗi RL step** (đảm bảo không catastrophic forget)
- **Sau khi rebuild dataset**

### 6.2 Regression targets cho T3 sau RL

| Metric | Baseline T3 SFT | Target sau RL | Loại |
|---|---:|---:|---|
| Tool F1 (SFT benchmark) | 0.898 | ≥ 0.85 (anti-regress) | 🔴 Hard |
| `ask_back` | 0.667 | ≥ 0.95 | 🟢 |
| `tool_call_derivation` | 0.763 | ≥ 0.75 | 🟢 |
| `occasion_formality` | 0.740 | ≥ 0.65 | 🟡 |
| `body_shape_advice` | 0.040 | ≥ 0.45 | 🔴 P0 RL target |
| `season_advice` | 0.383 | ≥ 0.60 | 🟡 |
| `coherence` | 0.500 | ≥ 0.85 | 🟡 |
| **Overall mean** | 0.524 | **≥ 0.55** | — |

---

## 7. Production Monitoring (khi tích hợp app)

| Log | Lý do |
|---|---|
| Generated tool call | Debug parse failure |
| Validation errors | Track hallucination rate |
| Retrieval result count | Detect no-result pattern |
| Latency | Đảm bảo < 5–8s |
| Parse failure rate | Active learning signal |

**KHÔNG log:** dữ liệu nhạy cảm (token, ảnh raw) nếu không cần.

**Release policy:**
- Version hoá adapter + benchmark JSON trong release notes
- Canary benchmark trước khi rollout
- A/B test新旧 adapter trên subset traffic

---

## 8. Slide gợi ý

1. **Slide triết lý đánh giá** (§1) — 4 trục, "không gộp 1 điểm".
2. **Slide SFT benchmark kết quả** (§2.4) — bar chart T3 highlight.
3. **Slide subtask insight** (§2.5) — "Thinking variant thắng reasoning task".
4. **Slide fashion-logic benchmark** (§3.2) — 2 family × 6 scorer, reproducible.
5. **Slide bug scorer fix** (§3.5) — điểm nhấn DL: "scorer bug che giấu tiến độ".
6. **Slide benchmark ngoài đề xuất** (§4) — thể hiện kiến thức SOTA (BFCL, IFEval, Polyvore).
7. **Slide regression guard** (§6) — "RL không được làm Tool F1 tụt".

---

*Hết báo cáo evaluation. Đọc tiếp `05_FUTURE_DIRECTIONS.md`.*
