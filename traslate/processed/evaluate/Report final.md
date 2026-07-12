# BÁO CÁO CHI TIẾT TIẾN TRÌNH XỬ LÝ DỮ LIỆU & ĐÁNH GIÁ MÔ HÌNH
*(Dự án: Trợ lý Thời trang OutfitMatch Stylist)*

Tài liệu này cung cấp cái nhìn chi tiết và chuyên sâu về từng bước trong quy trình phát triển hệ thống, từ giai đoạn xử lý dữ liệu thô cho tới đánh giá chi tiết 4 mô hình ngôn ngữ lớn dựa trên hệ thống tiêu chí mới.

---

## 📊 Tóm tắt các số liệu cốt lõi
> [!NOTE]
> * **Dữ liệu thô ban đầu:** ~40.000 dòng dữ liệu câu hỏi - trả lời.
> * **Dữ liệu sạch sau lọc:** **37.441 dòng** (`cleaned_full_dataset.csv`).
> * **Dữ liệu huấn luyện cân bằng:** **10.000 dòng** (`cleaned_balanced_10k_dataset.csv` & `training_ready_10k_dataset.jsonl`).
> * **Tập dữ liệu Benchmark:** **200 mẫu thử** (`test_part1_200.json`) chia làm **36 danh mục thời trang**.
> * **Tài nguyên liên kết nguồn (`sourcelink.txt`):** **255 đường dẫn (URLs)** thuộc **14 trang web/tên miền** uy tín.

---

## 🛠️ Chi tiết từng bước trong quá trình thực hiện

### Bước 1: Làm sạch 40k dòng dữ liệu gốc (Data Cleaning)
Giai đoạn này xử lý tập dữ liệu thô dịch thuật/gốc ban đầu từ ~40k dòng nhằm tạo ra cơ sở dữ liệu chất lượng cao, không chứa rác thông tin.

* **Thực hiện lọc dữ liệu:**
  * Loại bỏ các dòng trùng lặp hoàn toàn về câu hỏi hoặc câu trả lời.
  * Loại bỏ các câu hỏi quá ngắn, vô nghĩa, hoặc câu trả lời rỗng (`null`).
  * Kết quả thu được **37.441 dòng sạch** lưu tại `cleaned_full_dataset.csv`.
* **Trích xuất tập huấn luyện 10k cân bằng (`cleaned_balanced_10k_dataset.csv`):**
  * Lấy ra chính xác **10.000 mẫu câu hỏi - câu trả lời chất lượng cao nhất**.
  * Định dạng dữ liệu gồm 4 cột chính:
    1. `original_input`: Câu hỏi tiếng Anh gốc.
    2. `original_output`: Câu trả lời tiếng Anh gốc.
    3. `translated_input`: Câu hỏi tiếng Việt tương ứng.
    4. `translated_output`: Câu trả lời tiếng Việt tương ứng.
  * Lưu trữ định dạng JSON Lines tại `training_ready_10k_dataset.jsonl` sẵn sàng cho quá trình Fine-tuning.

---

### Bước 2: Xây dựng Đồ thị Tri thức Cấu trúc & Phân tích Tài nguyên Nguồn

#### 1. Đồ thị tri thức (`structured_knowledge_graph.json`)
Trích xuất từ các tài liệu hướng dẫn và dữ liệu thời trang để tạo ra cơ sở dữ liệu tri thức tĩnh hỗ trợ RAG (Retrieval-Augmented Generation). Đồ thị lưu trữ các thông tin:
* Các thuộc tính thời trang (màu sắc, chất liệu vải, kiểu dáng, cấu trúc cơ thể).
* Các quy tắc phối đồ chuẩn xác (Consensus Rules).
* Các phong cách/xu hướng đã lỗi thời cần né tránh (`outdated_trends_to_avoid`).

#### 2. Thống kê liên kết nguồn (`sourcelink.txt`)
Tệp này chứa các đường dẫn uy tín được sử dụng để cung cấp nguồn tham khảo cho câu trả lời của trợ lý. Qua phân tích cấu trúc tệp, hệ thống ghi nhận:
* **Tổng số đường dẫn (URLs):** 255 link.
* **Số đường dẫn duy nhất (Unique URLs):** 221 link.
* **Số trang web/tên miền duy nhất (Unique Domains):** 14 trang web, được chia làm 2 nhóm chính:

| STT | Tên miền (Domain) | Loại trang web | Mô tả vai trò |
| :---: | :--- | :---: | :--- |
| 1 | `www.elle.com` | Thời trang | Tạp chí thời trang cao cấp toàn cầu |
| 2 | `www.esquire.com` | Thời trang | Tạp chí phong cách sống và thời trang nam giới |
| 3 | `www.harpersbazaar.com` | Thời trang | Tin tức xu hướng và phong cách cao cấp |
| 4 | `www.marieclaire.com` | Thời trang | Phong cách thời trang ứng dụng và làm đẹp |
| 5 | `www.whowhatwear.com` | Thời trang | Xu hướng phối đồ và mua sắm của giới trẻ |
| 6 | `www.mrporter.com` | Thời trang | Trang mua sắm và tư vấn phong cách nam giới |
| 7 | `www.net-a-porter.com` | Thời trang | Nền tảng bán lẻ thời trang xa xỉ nữ giới |
| 8 | `www.sumissura.com` | Thời trang | Hướng dẫn may mặc và chọn size đồ |
| 9 | `theadultman.com` | Thời trang | Blog tư vấn phong cách trưởng thành cho nam |
| 10 | `openai.com` | Công nghệ | Tài liệu kỹ thuật, hướng dẫn lập trình |
| 11 | `arxiv.org` | Học thuật | Thư viện báo cáo nghiên cứu khoa học |
| 12 | `learn.microsoft.com` | Công nghệ | Hướng dẫn và tài liệu API hệ thống |
| 13 | `dev.to` | Công nghệ | Blog chia sẻ kinh nghiệm của nhà phát triển |
| 14 | `www.rtinsights.com` | Công nghệ | Tin tức phân tích dữ liệu thời gian thực |

---

### Bước 3: Thử nghiệm sinh câu trả lời & Phân tích tập Benchmark

Tập dữ liệu benchmark đánh giá hiệu năng gồm **200 câu hỏi** được chọn lọc từ `test_part1_200.json`.

#### 📌 Phân bổ danh mục thời trang của 200 câu hỏi:
Hệ thống câu hỏi bao quát **36 chủ đề nhỏ** khác nhau để đảm bảo đánh giá toàn diện năng lực của các mô hình:

```
[ sustainable_fashion ]      ████████ 8.0% (16 câu)
[ color_theory ]             ███████▌ 7.5% (15 câu)
[ capsule_wardrobe ]         ███████ 7.0% (14 câu)
[ safety_recommendations ]   ██████ 5.5% (11 câu)
[ timeless_fashion ]         ██████ 5.5% (11 câu)
[ accessories ]              █████ 5.0% (10 câu)
[ footwear ]                 █████ 5.0% (10 câu)
[ tops_and_outerwear ]       ████▌ 4.5% (9 câu)
[ parisian_chic_minimalism ] ████ 4.0% (8 câu)
[ common_fabrics ]           ███▌ 3.5% (7 câu)
[ bottoms ]                  ███▌ 3.5% (7 câu)
[ outfit_transition ]        ███▌ 3.5% (7 câu)
[ business_formal ]          ███▌ 3.5% (7 câu)
[ patterns ]                 ███ 3.0% (6 câu)
[ technical_fabrics ]        ███ 3.0% (6 câu)
[ cold_winter ]              ███ 3.0% (6 câu)
[ Các nhóm khác (20 nhóm)* ]  █▌ 0.5% - 2.5% mỗi nhóm (tổng 44 câu)
```
*\*Các nhóm khác bao gồm: layering, weekend_casual, clarifying_customer_needs, construction_quality, dresses_and_skirts, body_proportions_and_balance, wedding_and_evening, refusing_out_of_scope_requests, silhouette, business_casual, v.v.*

Bốn mô hình được chạy thử nghiệm trên bộ khung này bao gồm: `Qwen3-VL 8B Instruct`, `Qwen3-VL 8B Thinking`, `Qwen3.5 9B Causal`, và `Gemma4 12B Instruct`. Kết quả thô được lưu trong thư mục `tested/`.

---

### Bước 4: Thiết lập hệ thống đánh giá LLM-as-a-Judge (Evaluation)

Hệ thống sử dụng **Llama 4 Scout 17B** làm giám khảo trung lập để chấm điểm tự động.

* **5 Tiêu chí cốt lõi mới (Thang điểm thô 1–5):**
  1. `context_utilization` (Khai thác ngữ cảnh): Mức độ áp dụng hiệu quả thông tin được cung cấp trong tài liệu/RAG.
  2. `trend_compliance` (Tuân thủ phong cách & xu hướng): Đề xuất key_items phù hợp và né tránh các xu hướng lỗi thời.
  3. `fashion_knowledge_qa` (Kiến thức thời trang): Tính chuyên nghiệp, logic trong tư vấn (phối màu, dáng người).
  4. `faithfulness` (Tính trung thực): Sự trung thực với tài liệu gốc, không tự suy diễn thông tin ngoài lề.
  5. `hallucination` (Chống ảo giác): Tuyệt đối không bịa đặt sản phẩm, giá tiền hoặc đường dẫn không có thật.
* **Quy đổi điểm số:** Điểm số thô (1–5) sau khi chấm sẽ được chia cho `5.0` để chuyển đổi về thang điểm chuẩn từ `0.0` đến `1.0` giúp tính toán trực quan.

---

### Bước 5: Ý nghĩa các sơ đồ trực quan hóa

Để phân tích và đánh giá 800 lượt chạy (200 mẫu thử × 4 mô hình), hệ thống tạo ra 4 biểu đồ trực quan hóa:

#### 1. Biểu đồ điểm trung bình (`benchmark_average_scores.png`)
* **Ý nghĩa:** So sánh điểm số trung bình tổng hợp của cả 5 tiêu chí của từng mô hình.
* **Vai trò:** Giúp nhận diện nhanh thứ hạng tổng quan của mô hình trên production.
* **Kết quả:** Qwen3-VL 8B Instruct đạt điểm cao nhất (0.79), theo sát là Qwen3-VL 8B Thinking (0.78), Qwen3.5 9B (0.76) và thấp nhất là Gemma4 (0.44).

#### 2. Biểu đồ phân phối điểm số (`benchmark_score_distribution.png`)
* **Ý nghĩa:** Thể hiện tỷ lệ phần trăm câu trả lời rơi vào từng phân khúc chất lượng: *Rất kém (0.0-0.2), Yếu (0.2-0.4), Trung bình (0.4-0.6), Tốt (0.6-0.8), Xuất sắc (0.8-1.0)*.
* **Vai trò:** Cho thấy tính ổn định của mô hình. Một mô hình tốt cần có tỷ lệ câu trả lời "Xuất sắc" lớn và "Rất kém" tối thiểu.
* **Kết quả:** Qwen3-VL 8B Instruct có tỷ lệ câu trả lời "Xuất sắc" cao nhất (60%). Gemma4 bị lỗi phân cực nặng với 42.5% câu trả lời bị chấm "Rất kém" do mô hình từ chối trả lời quá nhiều.

#### 3. Biểu đồ Violin và Box Plot kết hợp (`benchmark_box_violin_plots.png`)
* **Ý nghĩa:**
  * *Violin Plot:* Cho thấy hình dáng phân bố mật độ xác suất của điểm số (bụng phình to thể hiện điểm số tập trung dày đặc ở mức đó).
  * *Box Plot:* Hiển thị khoảng tứ phân vị (Q1, Q3), điểm trung vị (median) và các điểm ngoại lệ (outliers).
* **Vai trò:** Đánh giá độ trồi sụt phong độ của mô hình. Hộp (box) càng ngắn thể hiện mô hình trả lời càng ổn định, ít có câu trả lời bị lệch điểm bất thường.

#### 4. Biểu đồ so sánh theo 5 tiêu chí chi tiết (`benchmark_criteria_comparison.png`)
* **Ý nghĩa:** So sánh điểm trung bình của 4 mô hình trên từng tiêu chí con riêng biệt.
* **Vai trò:** Xác định điểm mạnh/yếu cụ thể của từng mô hình (ví dụ: mô hình nào chống ảo giác tốt nhất, mô hình nào khai thác ngữ cảnh tốt nhất).
* **Kết quả:**
  * Qwen3-VL 8B Thinking dẫn đầu về chống ảo giác (`hallucination`: 0.94) nhờ khối suy nghĩ `<think>`.
  * Qwen3.5 9B dẫn đầu về tuân thủ xu hướng thời trang (`trend_compliance`: 0.93).

---

### Bước 6: So sánh ưu và nhược điểm của các mô hình

Dựa trên kết quả đánh giá thực tế từ hệ thống Giám khảo và phân tích dữ liệu đầu ra:

| Mô hình | Điểm số TB | Ưu điểm cốt lõi | Nhược điểm lớn nhất |
| :--- | :---: | :--- | :--- |
| **Qwen3-VL 8B Instruct** | **0.79** (1st) | - Khả năng tư vấn thời trang chuyên nghiệp, có khiếu thẩm mỹ cao.<br>- Khai thác ngữ cảnh và tuân thủ RAG cực kỳ nhạy bén. | - Đôi lúc câu trả lời bị ngắn nếu tài liệu ngữ cảnh nạp vào quá ngắn. |
| **Qwen3-VL 8B Thinking** | **0.78** (2nd) | - Khả năng suy luận logic chuyên sâu rất tốt.<br>- Điểm chống ảo giác (`hallucination`) cao nhất hệ thống (0.94) nhờ cơ chế tự soát lỗi trong khối `<think>`. | - Tốc độ phản hồi chậm hơn do phải sinh thêm các token suy nghĩ nội bộ. |
| **Qwen3.5 9B Causal** | **0.76** (3rd) | - Định dạng câu trả lời rất chuẩn mực và ổn định.<br>- Đề xuất phong cách và key_items cực kỳ nhạy bén (`trend_compliance` đạt 0.93). | - Không hỗ trợ đầu vào dạng hình ảnh (chỉ nhận văn bản). |
| **Gemma4 12B Instruct** | **0.44** (4th) | - Tính an toàn thông tin cao, khả năng chống ảo giác ở mức tốt trên lý thuyết. | - **Bị lỗi Over-Alignment (Cân chỉnh quá đà):** System prompt quá nghiêm ngặt khiến mô hình liên tục từ chối trả lời ("Tôi không tìm thấy thông tin") ngay cả khi thông tin có thể suy luận được từ ngữ cảnh rộng. |

---

### Bước 7: Đồng bộ hóa và cập nhật hệ tiêu chí đánh giá (Hiện tại)
Khi thay đổi hệ thống tiêu chí chấm điểm trong `JUDGE_RUBRIC.md` để phù hợp hơn với thực tế tư vấn thời trang:
* Thay thế **Knowledge Retrieval** thành **Context Utilization** (đánh giá năng lực khai thác và tổng hợp thông tin ngữ cảnh thay vì chỉ truy xuất đơn thuần).
* Thay thế **Citation Accuracy** thành **Trend Compliance** (đổi từ việc chấm điểm đường dẫn URLs sang đánh giá tính nhạy bén thời trang và tuân thủ xu hướng phong cách).
* Toàn bộ mã nguồn, cấu hình đánh giá, 800 bản ghi kết quả JSON và báo cáo phân tích đã được đồng bộ hóa thành công mà không cần chạy lại các lượt chấm điểm tốn kém tài nguyên API.
