# Báo cáo đề xuất benchmark mở rộng cho 4 Stylist LoRA

**Ngày:** 2026-07-09  
**Phạm vi:** benchmark ngoài dự án cho 4 adapter đã fine-tune trong `docs/reports/stylist_final_qlora_benchmark/DETAILED_REPORT.md`.  
**Mục tiêu:** chọn bộ benchmark lớn, có nguồn công khai, phù hợp để so sánh năng lực tool-calling, instruction-following, hội thoại, VLM reasoning và downstream fashion/outfit quality.

---

## 1. Bối cảnh 4 model đã fine-tune

| Mã | Model / adapter | Vai trò hiện tại | Ghi chú benchmark nội bộ |
|---|---|---|---|
| **T1** | Qwen3-VL-8B Instruct LoRA | VLM stylist baseline ổn định | Tool F1 và hội thoại tự nhiên tốt nhưng kém T3 |
| **T2** | Qwen3.5-9B BNB4 LoRA | Text-only/tool-focused fallback | Không có vision trực tiếp; phù hợp tool/instruction/chat benchmark |
| **T3** | Qwen3-VL-8B Thinking LoRA | Candidate production hiện tại | Điểm tổng hợp nội bộ cao nhất, tool validity 1.0 |
| **T4** | Gemma 4 12B IT LoRA | Explanation / text generation candidate | Tool trigger yếu hơn; nên tách planner vs explanation |

Kết luận nội bộ trước đó: **T3 Qwen3-VL-8B Thinking** là lựa chọn production tốt nhất hiện tại, nhưng cần benchmark ngoài để tránh overfit vào bộ test nội bộ.

---

## 2. Nguyên tắc chọn benchmark

1. **Khớp năng lực sản phẩm:** OutfitMatch cần parse intent, hỏi lại, gọi `search_outfits`, giải thích bằng tiếng Việt và có thể dùng ảnh.
2. **Có thước đo khách quan khi có thể:** ưu tiên accuracy / pass rate / recall / AUC / MRR thay vì chỉ LLM-judge.
3. **Tách đúng năng lực:** không gộp tool-calling, chat style, vision reasoning và fashion retrieval vào một điểm duy nhất.
4. **So sánh công bằng 4 model:** benchmark có ảnh chỉ chạy trực tiếp cho T1/T3/T4; T2 chạy chế độ text-only hoặc OCR/caption fallback và phải ghi rõ.
5. **Không mâu thuẫn v3.1-lite:** benchmark fashion retrieval/outfit chỉ là eval offline, không thay đổi kiến trúc serving graph-first.

---

## 3. Danh sách benchmark đề xuất

### 3.1. Nhóm A — Tool-calling / agentic tool use

#### A1. BFCL — Berkeley Function Calling Leaderboard

- **Nguồn:** https://proceedings.mlr.press/v267/patil25a.html; leaderboard Gorilla/BFCL.
- **Tác vụ:** function calling, serial/parallel calls, AST-based evaluation, abstain, stateful multi-step agentic settings.
- **Metric chính:** AST match / executable function-call correctness theo từng category của BFCL.
- **Model phù hợp:** T1, T2, T3, T4.
- **Độ ưu tiên:** **P0**.
- **Vì sao cần:** gần nhất với nhiệm vụ production: model phải quyết định khi nào gọi `search_outfits`, truyền đúng enum/schema, không hallucinate tool args.
- **Cách áp dụng cho OutfitMatch:**
  - Chạy benchmark gốc để có điểm tool-calling chung.
  - Tạo thêm subset nội bộ kiểu BFCL với schema `search_outfits` và controlled vocab trong `vocab.py`.

#### A2. StableToolBench

- **Nguồn:** https://aclanthology.org/2024.findings-acl.664
- **Tác vụ:** tool learning quy mô lớn dựa trên ToolBench nhưng ổn định hơn nhờ virtual API server + cache/simulator.
- **Metric chính:** SoPR, SoWR.
- **Model phù hợp:** T1, T2, T3, T4.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** kiểm tra model trong bối cảnh tool/API nhiều bước, đồng thời tránh lỗi benchmark drift do API thay đổi.
- **Lưu ý:** chi phí setup cao hơn BFCL; nên làm sau khi đã có harness tool-call chung.

---

### 3.2. Nhóm B — Instruction-following / hội thoại

#### B1. IFEval

- **Nguồn:** https://arxiv.org/abs/2311.07911
- **Tác vụ:** instruction-following với instruction có thể verify tự động; khoảng 500 prompts, 25 loại instruction.
- **Metric chính:** strict / loose prompt-level và instruction-level accuracy.
- **Model phù hợp:** T1, T2, T3, T4.
- **Độ ưu tiên:** **P0**.
- **Vì sao cần:** OutfitMatch yêu cầu model giữ format, hỏi lại đúng khi thiếu thông tin, không phá JSON/tool schema.
- **Cách áp dụng:** chạy IFEval gốc + thêm mini-suite tiếng Việt: giới hạn số outfit, bắt buộc nêu giá VND, không dùng item ngoài catalog.

#### B2. MT-Bench / Chatbot Arena style eval

- **Nguồn:** https://arxiv.org/abs/2306.05685
- **Tác vụ:** multi-turn open-ended chat; LLM-as-judge; đo helpfulness, reasoning, role adherence.
- **Metric chính:** GPT-4/LLM judge score hoặc pairwise win-rate.
- **Model phù hợp:** T1, T2, T3, T4.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** đánh giá chất lượng stylist conversation ngoài tool-call correctness.
- **Lưu ý:** có bias LLM-judge; cần giữ rubric riêng cho tiếng Việt, fashion helpfulness và groundedness.

#### B3. Arena-Hard-Auto

- **Nguồn:** https://arxiv.org/abs/2406.11939
- **Tác vụ:** 500 prompt khó được curate tự động từ crowd-sourced data; LLM-as-judge.
- **Metric chính:** win-rate / judge preference; paper báo cáo tương quan cao với human preference ranking.
- **Model phù hợp:** T1, T2, T3, T4.
- **Độ ưu tiên:** **P2**.
- **Vì sao cần:** nếu cần một benchmark chat khó hơn MT-Bench để tách biệt các model gần điểm nhau.

---

### 3.3. Nhóm C — Multimodal / VLM reasoning

#### C1. MMMU

- **Nguồn:** CVPR 2024, https://openaccess.thecvf.com/content/CVPR2024/html/Yue_MMMU_A_Massive_Multi-discipline_Multimodal_Understanding_and_Reasoning_Benchmark_for_CVPR_2024_paper.html
- **Tác vụ:** multimodal understanding + reasoning cấp college; 11.5K questions, 6 disciplines, 30 subjects, 183 subfields.
- **Metric chính:** accuracy.
- **Model phù hợp:** T1, T3, T4 trực tiếp; T2 chỉ chạy text/OCR-caption fallback.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** kiểm tra khả năng hiểu ảnh + reasoning của VLM, bổ sung cho benchmark tool nội bộ.

#### C2. SEED-Bench

- **Nguồn:** CVPR 2024, https://openaccess.thecvf.com/content/CVPR2024/papers/Li_SEED-Bench_Benchmarking_Multimodal_Large_Language_Models_CVPR_2024_paper.pdf
- **Tác vụ:** 24K multiple-choice questions, 27 dimensions; single image, multi-image, video, interleaved image-text, một phần image generation.
- **Metric chính:** accuracy theo dimension.
- **Model phù hợp:** T1, T3, T4; T2 fallback text-only không tính ngang hàng.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** phủ rộng VLM capability hơn MMMU, có evaluation khách quan không cần GPT judge.
- **Lưu ý:** chỉ chạy phần input image/text → output text nếu adapter không hỗ trợ image generation.

#### C3. MathVista

- **Nguồn:** ICLR 2024, https://mathvista.github.io/
- **Tác vụ:** visual mathematical reasoning; 6,141 examples từ 31 datasets; testmini 1,000 examples.
- **Metric chính:** accuracy.
- **Model phù hợp:** T1, T3, T4; T2 fallback caption/OCR.
- **Độ ưu tiên:** **P2**.
- **Vì sao cần:** stress-test reasoning trên ảnh/biểu đồ; không sát fashion nhưng tốt để phân tích VLM weakness.

---

### 3.4. Nhóm D — Fashion / outfit downstream benchmark

#### D1. Polyvore Outfits / FITB + Compatibility AUC

- **Nguồn:** ECCV 2018 Type-Aware Embeddings; https://openaccess.thecvf.com/content_ECCV_2018/papers/Mariya_Vasileva_Learning_Type-Aware_Embeddings_ECCV_2018_paper.pdf
- **Tác vụ:**
  - Fill-in-the-blank outfit completion.
  - Outfit compatibility prediction.
- **Quy mô:** Polyvore Outfits 68,306 outfits / 365,054 items; Polyvore Outfits-D 32,140 outfits / 175,485 items.
- **Metric chính:** FITB accuracy, compatibility AUC.
- **Model phù hợp:** downstream pipeline, không chỉ stylist LoRA.
- **Độ ưu tiên:** **P0**.
- **Vì sao cần:** sát nhất với luận điểm OutfitMatch: outfit phải compatible, không chỉ nói hay.
- **Cách áp dụng:** dùng để đo graph retrieval / OutfitTransformer-labse / rerank, sau đó cho stylist giải thích outfit đã retrieve.

#### D2. DeepFashion

- **Nguồn:** CVPR 2016, https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html
- **Tác vụ:** Attribute Prediction, Consumer-to-shop Retrieval, In-shop Clothes Retrieval, Landmark Detection.
- **Quy mô:** hơn 800K images, 50 categories, 1,000 attributes, hơn 300K cross-pose/cross-domain pairs.
- **Metric chính:** retrieval recall/top-k, attribute/category accuracy tùy subset.
- **Model phù hợp:** encoder/retrieval pipeline; VLM caption/explanation có thể eval phụ.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** benchmark retrieval thời trang lớn và kinh điển, hữu ích để chứng minh grounding bằng ảnh sản phẩm.

#### D3. FashionIQ

- **Nguồn:** CVPR 2021, https://openaccess.thecvf.com/content/CVPR2021/html/Wu_Fashion_IQ_A_New_Dataset_Towards_Retrieving_Images_by_Natural_CVPR_2021_paper.html
- **Tác vụ:** natural language feedback để retrieve ảnh garment tương tự/đúng yêu cầu.
- **Metric chính:** Recall@K cho interactive / composed image retrieval.
- **Model phù hợp:** stylist + retrieval, đặc biệt nếu thêm vòng sửa yêu cầu “giống cái này nhưng ...”.
- **Độ ưu tiên:** **P2**.
- **Vì sao cần:** rất gần trải nghiệm conversational shopping assistant, nhưng cần adapter eval riêng.

#### D4. Marqo FashionCLIP/FashionSigLIP benchmark suite

- **Nguồn:** https://github.com/Marqo-AI/marqo-FashionCLIP và `LEADERBOARD.md`.
- **Datasets:** Atlas, DeepFashion-InShop, DeepFashion-Multimodal, Fashion200K, iMaterialist, KAGL, Polyvore.
- **Tác vụ:** text-to-image, category-to-product, sub-category-to-product, một số attribute-to-product.
- **Metric chính:** Recall@1/10, AvgRecall, P@1/10, MRR.
- **Model phù hợp:** encoder/retrieval benchmark; stylist dùng kết quả retrieve để explain.
- **Độ ưu tiên:** **P1**.
- **Vì sao cần:** có suite 7 dataset công khai, so sánh được với FashionCLIP2.0, OpenFashionCLIP, Marqo-FashionCLIP, Marqo-FashionSigLIP.

---

## 4. Bộ benchmark tối thiểu đề xuất cho báo cáo Sprint/Final

### 4.1. Must-have P0

| Benchmark | Lý do must-have | Output báo cáo |
|---|---|---|
| BFCL | Tool-calling là năng lực lõi của stylist | Tool-call accuracy theo model |
| IFEval | Đo tuân thủ instruction/schema khách quan | Strict/loose accuracy |
| Polyvore FITB/AUC | Đo chất lượng outfit downstream | FITB accuracy + compatibility AUC |

### 4.2. Should-have P1

| Benchmark | Lý do | Output báo cáo |
|---|---|---|
| StableToolBench | Tool-use ổn định hơn ToolBench | SoPR/SoWR |
| MT-Bench hoặc mini-MT-Bench tiếng Việt | Đo chất lượng hội thoại stylist | Judge score + ví dụ win/loss |
| MMMU hoặc SEED-Bench | Đo VLM reasoning ngoài domain | Accuracy theo category |
| Marqo 7-dataset suite | Đo retrieval/fashion grounding | Recall/P/MRR |

### 4.3. Nice-to-have P2

| Benchmark | Khi nào làm |
|---|---|
| Arena-Hard-Auto | Khi 4 model quá gần điểm MT-Bench |
| MathVista | Khi cần phân tích VLM reasoning sâu |
| FashionIQ | Khi thêm feature conversational refinement |

---

## 5. Thiết kế harness chung

### 5.1. Chuẩn hóa model interface

Cần một wrapper chung cho 4 adapter:

```text
BenchmarkSample -> PromptBuilder -> ModelAdapter.generate() -> Parser -> Metric
```

Interface tối thiểu:

```python
class StylistModelAdapter:
    name: str
    supports_images: bool
    supports_tools: bool

    def generate_text(self, messages, *, max_tokens, temperature) -> str: ...
    def generate_with_images(self, messages, image_paths, *, max_tokens, temperature) -> str: ...
    def generate_tool_call(self, messages, tools, *, max_tokens, temperature) -> dict | str: ...
```

### 5.2. Chế độ chạy công bằng

| Nhóm benchmark | Temperature | Decoding | Judge |
|---|---:|---|---|
| Tool/IFEval | 0.0 | deterministic | parser/objective metric |
| Chat judge | 0.2 hoặc 0.0 | fixed max tokens | Gemini/GPT judge + rubric cố định |
| VLM MCQ | 0.0 | answer letter only | exact match |
| Retrieval/fashion | N/A | deterministic retrieval config | objective Recall/AUC/MRR |

### 5.3. Báo cáo kết quả cuối

Mỗi benchmark nên xuất:

```text
reports/benchmarks/<benchmark>/<run_id>/
  predictions.jsonl
  metrics.json
  error_analysis.md
  samples_pass.md
  samples_fail.md
```

Metrics tổng hợp:

```text
model, benchmark, split, metric_name, metric_value, n_samples, date, commit_sha
```

---

## 6. Rủi ro và cách giảm thiểu

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| T2 không hỗ trợ ảnh | So sánh VLM không công bằng | Chạy T2 ở `text_fallback`; không rank chung với VLM direct |
| LLM-judge bias | Chat benchmark thiếu khách quan | Luôn kèm objective benchmark BFCL/IFEval/Polyvore |
| Dataset license/access | Chậm setup | Ưu tiên benchmark có HF/GitHub public; ghi rõ nếu chỉ dùng testmini |
| Benchmark quá nặng | Không kịp final | Chạy P0 trước, P1 sample/testmini sau |
| Prompt tiếng Anh không phản ánh sản phẩm VN | Kết luận lệch | Thêm mini-suite tiếng Việt nội bộ cho stylist behavior |
| Tool schema khác `search_outfits` | Điểm BFCL không phản ánh domain | Chạy cả benchmark gốc và subset schema OutfitMatch |

---

## 7. Kế hoạch chạy theo giai đoạn

### Giai đoạn 1 — Benchmark P0 khách quan

1. Chuẩn hóa adapter inference cho 4 LoRA.
2. Chạy IFEval full.
3. Chạy BFCL subset khả thi.
4. Chạy Polyvore FITB/AUC cho retrieval pipeline.
5. Viết error analysis: tool args sai, enum sai, format sai, hallucinated IDs.

### Giai đoạn 2 — Hội thoại và VLM

1. Chạy MT-Bench hoặc mini-MT-Bench tiếng Việt.
2. Chạy MMMU hoặc SEED-Bench testmini cho T1/T3/T4.
3. Chạy T2 text/OCR fallback nhưng tách bảng.
4. So sánh T3 với T1/T2/T4 theo từng năng lực.

### Giai đoạn 3 — Fashion retrieval mở rộng

1. Chạy Marqo 7-dataset suite nếu compute cho phép.
2. Chạy DeepFashion In-shop retrieval subset.
3. Chạy FashionIQ nếu có feature text-feedback retrieval.

---

## 8. Kết luận đề xuất

Bộ benchmark nên trình bày theo 4 trục thay vì một leaderboard duy nhất:

1. **Tool correctness:** BFCL, StableToolBench, domain `search_outfits` suite.
2. **Instruction/chat quality:** IFEval, MT-Bench/Arena-Hard, mini-suite tiếng Việt.
3. **Vision-language reasoning:** MMMU, SEED-Bench, MathVista.
4. **Fashion/outfit downstream quality:** Polyvore FITB/AUC, DeepFashion, FashionIQ, Marqo suite.

Nếu thời gian hạn chế, chạy **BFCL + IFEval + Polyvore** trước. Đây là bộ tối thiểu đủ chứng minh model không chỉ “nói hay” mà còn gọi tool đúng, tuân thủ schema và tạo/retrieve outfit có compatibility đo được.

---

## 9. Benchmark trong-repo đã triển khai (rule-based, reproducible)

Bên cạnh các benchmark ngoài dự án ở §3, nhánh `feat/benchmark` đã triển khai một
benchmark **không cần LLM-judge**, đo trực tiếp **tri thức + logic thời trang**
của stylist bằng scorer quy tắc (deterministic) nền trên `vocab.py`.

**Module:** `src/outfitmatch/stylist/fashion_eval.py` · **Test:** `tests/test_stylist_fashion_eval.py` (34 test, 98% coverage)

### 9.1. Tri thức thời trang (knowledge)

| Item bank | Số item | Ground truth | Scorer | Metric |
|---|---|---|---|---|
| `OCCASION_FORMALITY_ITEMS` | 9 dịp | `formalities_for_occasion(occ)` (vocab) | `score_occasion_formality` | precision/recall/F1 trên enum + phạt formality sai |
| `BODY_SHAPE_ADVICE_ITEMS` | 5 dáng | curated positive/negative cues | `score_body_shape_advice` | recall positives − ½ × negatives |
| `SEASON_ADVICE_ITEMS` | 4 mùa | curated positive/negative cues | `score_season_advice` | recall positives − ½ × negatives |

### 9.2. Logic thời trang (reasoning)

| Item bank | Số item | Ground truth | Scorer | Metric |
|---|---|---|---|---|
| `COHERENCE_ITEMS` | 4 combo | `formality_span_ok` / tolerance=1 | `score_coherence_judgment` (+`detect_verdict`) | binary accuracy |
| `ASK_BACK_ITEMS` | 3 prompt thiếu dịp | phải hỏi lại, không hallucinate `occasion` | `score_ask_back` | 1.0 nếu ask-back & không hallucinate |
| `TOOL_CALL_DERIVATION_ITEMS` | 3 profile | reference tool-call hợp schema | `score_tool_call_derivation` | tool-call F1 × (enum_valid ? 1 : 0) |

### 9.3. Ưu điểm so với benchmark ngoài

- **Reproducible 100%**: không phụ thuộc GPT/Gemini làm judge → chạy lại cho cùng kết quả.
- **Fits cùng `generate_fn` adapter** với `stylist.benchmark.evaluate_dataset` → gắn vào 4 adapter QLoRA hiện có.
- **Khớp invariant v3.1-lite**: enum từ `vocab.py`, tool schema từ `tools.py` — nếu KB/schema đổi, benchmark thường xuyên dựa trước kỹ.
- **Vincoli honesty**: `score_ask_back` bắt hành vi “bịa occasion khi user chưa nói dịp”, đúng nỗi đau production của stylist.

### 9.4. Cách chạy

```bash
uv run pytest tests/test_stylist_fashion_eval.py -q
# aggregate demo trên 4 adapter:
#   report = evaluate_fashion_dataset(dataset, your_model.generate_fn)
```

---

## 10. Liên kết tài liệu

- Báo cáo đầy đủ: `docs/reports/stylist_benchmark_expansion/DETAILED_REPORT.md` (file này)
- Progress tracker: `docs/reports/stylist_benchmark_expansion/PROGRESS.md`
- Module: `src/outfitmatch/stylist/fashion_eval.py`
- Test: `tests/test_stylist_fashion_eval.py`
- Feature log: `docs/feature.md` → `stylist-fashion-eval`
