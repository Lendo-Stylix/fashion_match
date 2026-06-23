# Detailed report — stylist knowledge distillation for Qwen3.5-9B

**Date:** 2026-06-23  
**Branch:** `feature/stylist-knowledge-distill-report`

> Ghi chú /sp: repo hiện không có skill file `/sp execute` riêng. Phần dưới đây được thực hiện theo execute-mode thủ công: phân tích vấn đề → sửa distill pipeline → verify lại artifact → ghi rõ scorecard và residual risks.

---

## 1) Scope và artifact được đánh giá

### Input raw
- Nguồn: `data/stylist/fine_tune/stylist_knowledge/finetuning_data_fashion_knowledge.csv`
- Quy mô raw: **40,302 rows**

### Output distilled dùng cho QLoRA Qwen3.5-9B
- Bundle: `data/stylist/fine_tune/runs/stylist_distilled_qwen35_under10k/`
- Knowledge rows: **7,200**
- Behavioral rows: **1,600**
- Combined rows: **8,800**
- Approx training budget: **1,297,484 Qwen tokens**

### Report/charts liên quan
- `README.md`
- `summary.json`
- `topic_distribution_raw_vs_distilled.png`
- `prompt_style_raw_vs_distilled.png`
- `answer_length_hist_raw_vs_distilled.png`
- `quality_gate_drops.png`
- `family_size_buckets_raw_vs_distilled.png`

---

## 2) Các vấn đề chính trong raw dataset

### 2.1 Topic skew rất nặng
Raw data bị dồn vào 2 nhóm lớn:
- `color_analysis`: **20,100 / 40,302 = 49.87%**
- `wardrobe_capsule`: **12,869 / 40,302 = 31.93%**

Tác động:
- Model sau fine-tune dễ **mode collapse** về “màu gì hợp”, “xây tủ đồ capsule”, nhưng yếu hơn ở:
  - occasion-specific reasoning
  - body-fit reasoning
  - care / maintenance
  - season / layering
- Khi gặp prompt hiếm, model có xu hướng trả lời bằng mẫu phổ biến thay vì trả đúng intent.

### 2.2 Prompt-style bias: first-person quá áp đảo
Raw prompt style:
- `first_person`: **66.62%**

Tác động:
- Model học mạnh kiểu trả lời tư vấn dài cho “tôi muốn…”, nhưng yếu hơn ở:
  - câu hỏi định nghĩa
  - câu hỏi how-to ngắn
  - câu request dạng tool / task-oriented
- Tool-calling / follow-up behavior dễ thiếu ổn định nếu tập huấn luyện thiên quá nhiều về một kiểu prompt.

### 2.3 Overlong answer / essay drift
Raw long-answer ratio:
- `long`: **10.53%**
- Max assistant length: **705 words**

Tác động:
- Fine-tuned model dễ trả lời **quá dài**, vòng vo, tăng latency, tăng token cost.
- Với QLoRA SFT, quá nhiều long-form rows có thể làm model ưu tiên “viết essay” thay vì “trả lời đúng format và dừng đúng lúc”.
- Trong downstream tool / JSON / retrieval UX, đây là failure mode rất xấu.

### 2.4 Mixed-script / translation artifact
Quality gate phát hiện:
- `mixed_script`: **1,788 rows = 4.44%**

Ví dụ lỗi thực tế:
- chèn Cyrillic: `серьги`, `поверх`, `шарф`
- chèn CJK: `thời髦`

Tác động:
- Model học ra **câu trả lời tiếng Việt bị lẫn ký tự ngoại lai**.
- Tokenization bị nhiễu, lãng phí capacity vào pattern không mong muốn.
- UX giảm mạnh vì user thấy model “bị lỗi ngôn ngữ”.

### 2.5 Prompt echo / question restatement
Quality gate phát hiện:
- `question_echo`: **167 rows = 0.41%**

Tác động:
- Model sau fine-tune dễ mở đầu bằng việc **lặp lại câu hỏi** thay vì trả lời trực tiếp.
- Ở strict output setting, đây là dấu hiệu instruction-following không sắc.

### 2.6 Near-duplicate density cao
Raw family buckets:
- family size `21+`: **246 families**
- family size `11-20`: **297 families**
- family size `6-10`: **567 families**

Tác động:
- Nếu distill ngây thơ theo random sample, model sẽ thấy nhiều paraphrase gần như cùng một ý.
- Gradient update bị lãng phí cho cụm template lặp thay vì phủ thêm các topic hiếm.
- Model dễ “memorize style” hơn là học boundary tổng quát.

### 2.7 Behavioral supervision của bundle cũ còn hơi mỏng
Bundle cũ:
- **5,700 rows** = 5,000 knowledge + 700 behavioral
- behavioral share: **12.28%**

Tác động:
- Model có thể biết kiến thức fashion, nhưng chưa đủ mạnh ở các hành vi cần cho assistant thật:
  - ask missing info
  - tool calling
  - polite decline
  - concise recommend + explain
  - multi-turn carry-over

---

## 3) Nếu các vấn đề trên không được xử lý, model sau fine-tune có thể hỏng theo những cách nào?

### Case A — trả lời rất “đúng fashion”, nhưng không giống assistant production
Dấu hiệu:
- nói dài
- mở đầu bằng việc paraphrase lại câu hỏi
- ít hỏi ngược khi thiếu thông tin
- ít tool-call đúng lúc

Nguyên nhân dataset:
- overlong rows
- prompt echo
- behavioral share thấp

### Case B — tiếng Việt bị lẫn script lạ
Dấu hiệu:
- xuất hiện từ lạ như `поверх`, `серьги`, `thời髦`
- câu trả lời nhìn như bản dịch lỗi

Nguyên nhân dataset:
- mixed-script artifact lọt vào train set

### Case C — model mạnh ở color/capsule nhưng yếu ở body/occasion/season
Dấu hiệu:
- hỏi về body shape nhưng trả lời chung chung về màu/trang phục cơ bản
- hỏi occasion cụ thể nhưng model quay về lời khuyên generic

Nguyên nhân dataset:
- topic skew quá mạnh

### Case D — tool-calling yếu hoặc không ổn định
Dấu hiệu:
- không hỏi thiếu info
- không sinh tool call khi đáng ra phải gọi
- hoặc gọi tool xong vẫn sinh explanation dài, không gọn

Nguyên nhân dataset:
- behavioral supervision thiếu số lượng / thiếu tỷ trọng

### Case E — model bị “template lock”
Dấu hiệu:
- nhiều câu trả lời khác prompt nhưng giống cấu trúc gần như hoàn toàn
- diversity thấp, wording lặp

Nguyên nhân dataset:
- near-duplicate families quá dày

---

## 4) Đã distill bằng những phương pháp gì?

### 4.1 Quality gate trước khi sample
Các rule dùng trong `scripts/stylist/distill_stylist_dataset.py`:
- drop `mixed_script`
- drop `too_long` nếu assistant > **280 words**
- drop `question_echo` nếu overlap với first sentence của answer >= **0.65**

Kết quả:
- rows bị loại: **4,308 = 10.69% raw set**
- clean pool còn: **35,994 rows**

### 4.2 Cap near-duplicate family
- Family key dùng 3 content tokens đầu sau stopword filtering
- `max_per_family = 3`

Mục tiêu:
- giữ coverage
- giảm template repetition
- tránh train set bị chi phối bởi paraphrase clusters

### 4.3 Topic-balanced selection bằng quota theo `sqrt(count)`
- Không dùng proportional sampling thuần vì sẽ tiếp tục nuôi topic lớn
- Dùng sqrt-weight để **nâng các topic nhỏ lên** nhưng không ép hard-balance thiếu tự nhiên

Mục tiêu:
- giảm dominance của topic lớn
- vẫn giữ sample mass đủ lớn cho topic phổ biến

### 4.4 Tăng behavioral supervision
Task mix mới:
- `ask_missing_info`: 250
- `body_analysis`: 200
- `recommend_explain`: 300
- `polite_decline`: 150
- `multi_turn`: 200
- `edge_case`: 150
- `tool_calling`: 350

Tổng behavioral: **1,600 rows**

### 4.5 Exact dedupe sau synthetic generation
Trong verify, mình phát hiện bundle đầu tiên còn **1 duplicate row** trong behavioral section.  
Đã sửa generator để tự thêm suffix tự nhiên cho synthetic rows nếu signature bị trùng.

Kết quả verify cuối:
- exact duplicate rows trong final train set: **0**

---

## 5) Validation methods đã dùng

### 5.1 Structural validation
Mục tiêu: đảm bảo artifact có thể đóng gói cho pipeline train

Đã kiểm tra:
- mọi JSONL parse được
- mọi row có `messages`
- mọi row có tối thiểu 3 messages
- `manifest` khớp line counts thực tế

Kết quả:
- `knowledge_distilled.jsonl` = **7,200** rows
- `behavioral_synthetic.jsonl` = **1,600** rows
- `train.jsonl` = **8,800** rows
- khớp `manifest.json`

### 5.2 Packaging validation
Mục tiêu: đảm bảo config Kaggle thật sự đọc đúng bundle

Đã kiểm tra:
- `collect_examples(configs/stylist_finetune_kaggle_qwen35_under10k.yaml)`
- số examples trả về phải bằng `manifest['combined_examples']`

Kết quả:
- **8,800 / 8,800** → pass

Ý nghĩa:
- bundle không chỉ “đúng file”, mà còn “đúng khi đi qua loader train thật”.

### 5.3 Quality-leak validation
Mục tiêu: đảm bảo raw issues không lọt qua distill output

Đã kiểm tra lại trên final dataset:
- `mixed_script`
- `too_long`
- `question_echo`

Kết quả:
- final knowledge set flagged rows: **0 / 7,200**
- final combined set flagged rows: **0 / 8,800**

### 5.4 Exact duplicate validation
Mục tiêu: đảm bảo packaging không collapse duplicate rows

Đã kiểm tra:
- hash trên full `messages`

Kết quả:
- duplicate rows final: **0**

### 5.5 Coverage validation
Mục tiêu: distill phải nhỏ hơn nhiều nhưng không làm mất domain coverage

Kết quả:
- topic coverage raw: **9/9**
- topic coverage fina
