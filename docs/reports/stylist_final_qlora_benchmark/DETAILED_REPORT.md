# Báo cáo fine-tune QLoRA stylist và benchmark 4 mô hình

**Dự án:** OutfitMatch — Body & Occasion-Aware Fashion Recommender  
**Mục tiêu:** fine-tune stylist model tiếng Việt có khả năng parse intent, gọi `search_outfits` đúng schema, hỏi lại khi thiếu thông tin, chống hallucination và giải thích outfit dựa trên retrieval context.  
**Kết luận cuối:** chọn **T3 — Qwen3-VL-8B Thinking QLoRA adapter** làm stylist model chính.

---

## 1. Executive summary

Bốn adapter QLoRA đã được huấn luyện bằng pipeline **Unsloth-only** trên Kaggle, dùng cùng final merged dataset:

- Train: **11,252 examples**
- Eval: **348 examples**
- Tool rows: train **1,360**, eval **40**
- Tất cả hoàn thành **704/704 steps = 1 epoch**
- Tất cả đã được upload public lên Hugging Face

| Rank | Model | Load target | Eval loss | Tool F1 | Text sim | Format | Error |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | T3 Qwen3-VL-8B Thinking | `unsloth/Qwen3-VL-8B-Thinking-bnb-4bit` | **0.5943** | **0.8980** | **0.5519** | **1.0000** | 0 |
| 2 | T2 Qwen3.5-9B BNB4 | `techwithsergiu/Qwen3.5-text-9B-bnb-4bit` | 0.6880 | 0.8776 | 0.4877 | 1.0000 | 0 |
| 3 | T1 Qwen3-VL-8B Instruct | `unsloth/Qwen3-VL-8B-Instruct-bnb-4bit` | 0.6027 | 0.8571 | 0.5437 | 1.0000 | 0 |
| 4 | T4 Gemma 4 12B IT | `unsloth/gemma-4-12b-it` | 0.6255 | 0.6531 | 0.5354 | 0.9714 | 0 |

**Nhận định chính:** T3 không nhất ở mọi subtask, nhưng có tổng thể ổn định nhất: loss thấp nhất, Tool F1 cao nhất, text similarity cao nhất, compliance 100%, không lỗi generate. Đây là tiêu chí phù hợp nhất với OutfitMatch vì stylist model phải làm đúng tool contract trước khi retrieval/rerank hoạt động.

---

## 2. Vai trò của stylist model trong kiến trúc OutfitMatch

Trong kiến trúc v3.1-lite, stylist nằm giữa user và retrieval:

1. User nhập text/ảnh/quiz context.
2. Stylist parse yêu cầu và quyết định hỏi lại hoặc gọi `search_outfits`.
3. Retrieval dùng tool arguments để seed-filter item, graph traversal và post-filter outfit.
4. Stylist giải thích kết quả bằng tiếng Việt, không hallucinate outfit ngoài danh sách.

Do đó model không chỉ cần “nói hay”, mà cần:

- Chuẩn hoá tiếng Việt tự nhiên sang controlled vocabulary.
- Sinh XML/JSON tool-call parse được.
- Không bịa `outfit_id`.
- Biết hỏi lại khi thiếu constraint.
- Biết từ chối hoặc relax constraints khi không có kết quả.

Vì vậy benchmark ưu tiên **Tool F1** và **format compliance** hơn chỉ text similarity.

---

## 3. Dataset fine-tune

Dataset final merged bao gồm các nhóm hành vi chính:

| Nhóm task | Vai trò |
|---|---|
| `tool_calling`, `tool_calling_grounded` | Học gọi `search_outfits` đúng field/enum. |
| `recommend_explain`, `recommend_explain_grounded` | Giải thích outfit dựa trên context retrieval. |
| `body_fit_grounded`, `body_analysis` | Tư vấn theo dáng người. |
| `ask_missing_info`, `ask_missing_info_grounded` | Hỏi lại khi thiếu dịp, ngân sách, style, body info. |
| `polite_decline`, anti-hallucination | Không bịa khi thiếu dữ kiện hoặc ngoài scope. |
| `stylist_knowledge` | Kiến thức phối đồ tiếng Việt. |
| `multi_turn` | Giữ ngữ cảnh hội thoại nhiều lượt. |

Điểm mạnh của dataset là đã kết hợp cả knowledge, behavior và grounded tool-use. Điểm cần cải thiện là số mẫu tool-calling vẫn còn nhỏ so với open-ended stylist knowledge; benchmark cho thấy một số model học được “giọng stylist” nhưng chưa luôn trigger tool call đúng lúc.

---

## 4. Quá trình fine-tune

### 4.1. Các model huấn luyện

| ID | Base model | Ghi chú |
|---|---|---|
| T1 | `unsloth/Qwen3-VL-8B-Instruct` | Qwen-VL instruct, load 4-bit. |
| T2 | `unsloth/Qwen3.5-9B` | Thực tế dùng `techwithsergiu/Qwen3.5-text-9B-bnb-4bit` để fit GPU. |
| T3 | `unsloth/Qwen3-VL-8B-Thinking` | Qwen-VL thinking, load 4-bit. |
| T4 | `unsloth/gemma-4-12b-it` | Cần Transformers main + HF Hub mới. |

### 4.2. Kết quả training

| Model | Run ID | Resume | Final step | Epoch | Eval loss | Eval runtime |
|---|---|---:|---:|---:|---:|---:|
| T1 | `qwen3vl8b_instruct` | 500 | 704 | 1.0 | 0.602685 | 83.3s |
| T2 | `qwen35_9b_bnb4bit` | 500 | 704 | 1.0 | 0.687953 | 99.9s |
| T3 | `qwen3vl8b_thinking` | 500 | 704 | 1.0 | 0.594302 | 85.6s |
| T4 | `gemma4_12b_it` | 500 | 704 | 1.0 | 0.625529 | 136.5s |

T3 có eval loss thấp nhất, T1 sát T3, Gemma ở giữa, T2 loss cao nhất. Tuy nhiên selection cuối vẫn dựa trên benchmark hành vi vì eval loss không đo trực tiếp chất lượng tool-call.

### 4.3. Các vấn đề kỹ thuật đã xử lý

| Vấn đề | Root cause | Cách xử lý |
|---|---|---|
| Qwen-VL text-only bị `Incorrect image source` | Gọi processor positional khiến prompt bị hiểu là image. | Gọi `processor(text=[prompt], images=None, ...)`. |
| Resume checkpoint sai model | Kaggle dataset có checkpoint cũ/stale. | Chỉ restore checkpoint khi explicit `local_path`; ưu tiên checkpoint dataset đúng model. |
| Torch 2.4 resume bị Transformers chặn | CVE guard và `rng_state_*.pth` weights-only. | Patch trusted resume, xoá `rng_state_*.pth` cho checkpoint tự tạo. |
| Gemma không load với Transformers pinned | `transformers==5.2.0` chưa hỗ trợ Gemma 4. | Dùng Transformers GitHub main, nâng `huggingface_hub>=1.5`. |
| Benchmark P100 fail với Torch mới | Torch 2.10 CUDA không support `sm_60`. | Pin Torch 2.4 stack. |
| Torch downgrade làm `torchaudio` crash | `torchaudio 2.10` còn lại không khớp Torch 2.4. | Uninstall/align `torchaudio`. |
| Unsloth inductor shim lỗi | `SimpleNamespace` không có source cho `inspect.getsource`. | Gán module thật `torch._inductor.config`. |
| Pip resolver conflict | Unsloth-Zoo và Transformers main mâu thuẫn deps. | Tách install và dùng `--no-deps` cho Unsloth/Transformers main. |

---

## 5. Benchmark methodology

Benchmark final dùng **70 held-out prompts** cho cả 4 model. Mỗi model được load bằng Unsloth, attach adapter tương ứng, generate trên cùng prompt/reference và chấm:

| Metric | Ý nghĩa |
|---|---|
| `mean_tool_call_f1` | F1 trên field/value tool-call so với reference. Quan trọng nhất cho E2E retrieval. |
| `mean_text_similarity` | Độ gần giữa generated text và reference. Hữu ích nhưng không thay thế LLM judge. |
| `format_compliance_rate` | Tỷ lệ output đúng format/tool contract. |
| `error_count` | Lỗi generate/load/eval. |

Phân bố benchmark:

| Task type | Số mẫu |
|---|---:|
| `stylist_knowledge` | 42 |
| `tool_calling_grounded` | 5 |
| `tool_calling` | 2 |
| `ask_missing_info` | 3 |
| `ask_missing_info_grounded` | 2 |
| `recommend_explain_grounded` | 3 |
| `recommend_explain` | 2 |
| `body_fit_grounded` | 3 |
| `polite_decline_anti_hallucination` | 3 |
| `multi_turn` | 2 |
| Khác | 5 |

---

## 6. Benchmark results

### 6.1. Overall ranking

| Rank | Model | Tool F1 | Text sim | Format | Error |
|---:|---|---:|---:|---:|---:|
| 1 | T3 Qwen3-VL-8B Thinking | **0.8980** | **0.5519** | **1.0000** | 0 |
| 2 | T2 Qwen3.5-9B BNB4 | 0.8776 | 0.4877 | 1.0000 | 0 |
| 3 | T1 Qwen3-VL-8B Instruct | 0.8571 | 0.5437 | 1.0000 | 0 |
| 4 | T4 Gemma 4 12B IT | 0.6531 | 0.5354 | 0.9714 | 0 |

### 6.2. Một số subtask quan trọng

| Model | `tool_calling_grounded` F1 | `tool_calling` F1 | `stylist_knowledge` sim | `recommend_explain` sim | `body_fit_grounded` sim |
|---|---:|---:|---:|---:|---:|
| T3 Thinking | 0.9143 | **0.8571** | 0.3872 | **0.6983** | 0.8159 |
| T2 Qwen3.5 | **0.9429** | 0.7143 | **0.4119** | 0.6975 | **0.8349** |
| T1 Instruct | 0.8857 | 0.7857 | 0.3831 | 0.6457 | **0.8349** |
| T4 Gemma | 0.9143 | **0.0000** | 0.4028 | 0.1264 | 0.8231 |

---

## 7. Phân tích vì sao kết quả benchmark như vậy

### 7.1. T3 Qwen3-VL-8B Thinking thắng vì ổn định nhất

T3 có profile tốt nhất cho production:

- Tool F1 cao nhất overall.
- Text similarity cao nhất overall.
- Compliance 100%, error 0.
- Eval loss thấp nhất.
- Subtask `tool_calling` non-grounded tốt nhất trong nhóm Qwen/Gemma.

Thinking variant có lợi thế khi phải suy luận từ tiếng Việt tự nhiên sang enum nội bộ. Tool call của OutfitMatch không chỉ là copy keyword; model phải hiểu “đi làm”, “cafe”, “dáng tam giác ngược”, “tránh màu sáng”, “ngân sách dưới 900k” rồi map sang field/schema. T3 giữ được khả năng reasoning này tốt hơn T1, nhưng vẫn không đánh đổi quá nhiều chất lượng câu trả lời.

### 7.2. T2 Qwen3.5-9B BNB4 mạnh về tool khi prompt rõ, nhưng yếu style hơn

T2 đứng nhất ở `tool_calling_grounded` (0.9429), chứng tỏ khi prompt/context rõ thì model map field rất tốt. Tuy nhiên:

- `tool_calling` non-grounded chỉ 0.7143.
- Text similarity overall thấp nhất trong top 3.
- Eval loss cao nhất.

Nguyên nhân hợp lý:

- Load target thực dụng là repo 4-bit ngoài (`techwithsergiu/...`) thay vì base Unsloth trực tiếp, có thể khác chat/template behavior.
- Text-only model có xu hướng trả lời thẳng, ít bám style hội thoại reference.
- Nó hợp làm fallback planner/tool caller khi prompt được scaffold rõ, nhưng tổng thể chưa vượt T3.

### 7.3. T1 Qwen3-VL-8B Instruct tự nhiên nhưng tool F1 thấp hơn T3

T1 có text similarity gần T3 và compliance 100%, nhưng Tool F1 thấp hơn:

- `tool_calling_grounded`: 0.8857, thấp hơn T2/T3/Gemma.
- `tool_calling`: 0.7857, thấp hơn T3.

Điều này cho thấy Instruct variant học format tốt nhưng kém Thinking variant ở bước chọn đúng argument/enum. T1 phù hợp nếu muốn output ngắn, trực tiếp và ít thinking marker, nhưng production retrieval cần tool chính xác hơn nên T3 vẫn tốt hơn.

### 7.4. Gemma 4 12B IT không yếu về language, nhưng chưa học trigger tool-call

Gemma có eval loss 0.6255 và text similarity 0.5354, không tệ. Nó cũng đạt `tool_calling_grounded` 0.9143. Nhưng Tool F1 overall chỉ 0.6531 vì:

- Ở nhóm `tool_calling` non-grounded, Gemma đạt **0.0000**.
- Model sinh câu tự nhiên kiểu “Mình sẽ tìm outfit...” thay vì phát `<tool_call>`.
- Format compliance chỉ 0.9714, thấp hơn 3 model còn lại.

Kết luận: Gemma đã học khá tốt phần ngôn ngữ/giải thích, nhưng chưa nội hoá contract “khi nào phải gọi tool”. Khi scaffold đủ rõ, nó có thể gọi tool; khi prompt tự nhiên hơn, nó quay về assistant prose. Đây là lý do Gemma chưa phù hợp làm stylist planner chính.

### 7.5. Vì sao eval loss không quyết định ranking cuối

Eval loss đo next-token likelihood trung bình trên toàn eval set, còn benchmark đo hành vi sau generation. Một model có thể loss tốt nhưng vẫn:

- Sai một enum quan trọng.
- Bỏ `<tool_call>`.
- Trả lời prose thay vì JSON/XML.
- Đúng ý nhưng khác reference nên text similarity thấp.

Với OutfitMatch, một lỗi nhỏ trong tool-call có thể làm retrieval sai hoàn toàn. Vì vậy chọn model phải dựa trên benchmark hành vi, đặc biệt là Tool F1 và compliance.

---

## 8. Hugging Face artifacts

Đã upload public 4 final adapters:

| Model | HF repo |
|---|---|
| T3 Thinking | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora` |
| T2 Qwen3.5 BNB4 | `Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora` |
| T1 Instruct | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-instruct-lora` |
| T4 Gemma | `Nhat-Quang/outfitmatch-stylist-final-gemma4-12b-it-lora` |

Mỗi repo có adapter root files (`adapter_model.safetensors`, `adapter_config.json`), tokenizer/chat template/processor files khi có, `training_summary.json`, `trainer_state.json` và README benchmark summary.

Benchmark artifact local:

`data/stylist/fine_tune/runs/kaggle_qlora_final_outputs/benchmark4_v9/adapter_benchmark_70_four_models.json`

---

## 9. Khuyến nghị production

### Model chính

Dùng **T3 Qwen3-VL-8B Thinking LoRA**:

- Tool F1: 0.8980
- Text similarity: 0.5519
- Compliance: 1.0
- Error: 0
- Eval loss: 0.5943

### Fallback

- **T2 Qwen3.5-9B BNB4:** fallback text-only/tool-focused nếu prompt được scaffold rõ.
- **T1 Qwen3-VL-8B Instruct:** fallback ổn định, tự nhiên, nhưng kém T3 về tool F1.
- **Gemma 4 12B IT:** chưa dùng làm planner/tool caller; có thể thử cho explanation-only sau retrieval.

---

## 10. Định hướng cải thiện tương lai

### 10.1. Tăng dữ liệu tool-calling hard cases

Ưu tiên sinh thêm 1–2K examples cho:

- Request tiếng Việt tự nhiên, ít keyword enum.
- Body shape/skin tone/style dễ nhầm.
- Budget/price tier phức tạp.
- Prompt cần hỏi lại thay vì gọi tool.
- Prompt bắt buộc gọi tool nhưng model hay trả prose.
- Contrastive pairs chỉ khác một constraint để model học field sensitivity.

Mục tiêu ngắn hạn: đưa T3 Tool F1 lên **> 0.93**.

### 10.2. Mở rộng benchmark

Benchmark 70 mẫu đủ để chọn model, nhưng chưa đủ sâu cho production regression. Nên mở rộng lên 200–500 mẫu và tách leaderboard:

- Tool-call parse rate.
- Enum accuracy theo field: `occasion`, `style`, `body_shape`, `skin_tone`, `price_max`, `exclude_colors`.
- Ask-missing-info accuracy.
- Grounded explanation factuality.
- Hallucinated outfit ID rate.
- Vietnamese helpfulness bằng LLM-as-judge.

### 10.3. Thêm constrained decoding/parser repair

Tool-call là contract cứng, nên nên bổ sung:

- JSON grammar/constrained decoding.
- Enum alias normalizer.
- Retry nếu output không có `<tool_call>` trong tình huống bắt buộc gọi tool.
- Validation layer chặn field ngoài vocabulary.
- Logging parse failures để active learning.

### 10.4. Dùng LLM-as-judge cho phần text

Text similarity không đủ vì câu đúng có thể diễn đạt khác reference. Nên dùng Gemini/LLM judge theo rubric:

- Có grounded vào outfit/context không?
- Có bịa item/outfit/store/giá không?
- Có giải thích body/occasion/style hợp lý không?
- Tiếng Việt tự nhiên không?
- Có actionable recommendation không?

### 10.5. Fine-tune vòng 2 cho T3

Nên train thêm một vòng ngắn cho model thắng:

- Lấy tất cả sample T3 sai/sát ngưỡng.
- Thêm sample T2/Gemma đúng nhưng T3 sai.
- Oversample `tool_calling` non-grounded.
- Train LR thấp trong 0.3–0.5 epoch để tránh quên style.

### 10.6. Nếu tiếp tục Gemma

Gemma cần sửa trigger tool-call:

- Oversample non-grounded tool-call.
- System prompt mạnh hơn: nếu cần tìm outfit, phải trả `<tool_call>` trước, không nói prose trước.
- Dùng constrained decoding.
- Đánh giá riêng planner vs explanation; nếu planner vẫn thấp, chỉ dùng Gemma cho explanation/rerank text.

### 10.7. Production monitoring

Khi tích hợp app:

- Log generated tool call, validation errors, retrieval result count, no-result rate.
- Không log dữ liệu nhạy cảm/token/ảnh raw nếu không cần.
- Theo dõi parse rate, hallucinated outfit ID rate, latency.
- Canary benchmark trước khi thay adapter.
- Version hoá adapter + benchmark JSON trong release notes.

---

## 11. Kết luận

Quá trình fine-tune đã tạo và so sánh thành công 4 adapter QLoRA trên cùng dataset, cùng benchmark, và đã publish final adapters lên Hugging Face. **Qwen3-VL-8B Thinking** là lựa chọn production tốt nhất hiện tại vì thắng đồng thời ở Tool F1, text similarity, compliance và eval loss.

Bài học quan trọng là với OutfitMatch, chất lượng stylist phải được đo bằng hành vi tool-calling/grounding chứ không chỉ eval loss hoặc độ tự nhiên ngôn ngữ. Giai đoạn tiếp theo nên tập trung vào hard-case tool data, benchmark lớn hơn, constrained decoding, parser repair và LLM-as-judge cho explanation quality.
