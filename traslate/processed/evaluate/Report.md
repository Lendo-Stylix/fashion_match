# BÁO CÁO QUÁ TRÌNH TỪ BƯỚC LÀM SẠCH 40K DÒNG ĐẾN NAY

## Bước 1: Làm sạch 40k dòng dữ liệu gốc (Data Cleaning)

### Mục tiêu

Chắt lọc và chuẩn hóa tập dữ liệu thô gồm khoảng 40.000 câu xuống còn 10.000 câu hỏi và câu trả lời về thời trang.

### Thực hiện

- Loại bỏ các bản ghi trùng lặp.
- Xử lý dữ liệu thiếu, giá trị rỗng và lỗi định dạng.
- Lọc các mẫu câu hỏi tư vấn chất lượng cao, phản ánh phong cách đặt câu hỏi thực tế của người dùng.

---

## Bước 2: Xây dựng Đồ thị Tri thức Cấu trúc (Knowledge Graph)

### Mục tiêu

Xây dựng cơ sở tri thức thời trang làm nguồn ngữ cảnh cho hệ thống Retrieval-Augmented Generation (RAG).

### Thực hiện

- Trích xuất các thuộc tính thời trang như màu sắc, chất liệu, kiểu dáng và dáng người.
- Xây dựng các quy tắc phối đồ (mix-and-match) theo kiến thức thời trang.
- Tổng hợp danh sách các xu hướng lỗi thời cần tránh (`outdated_trends_to_avoid`).
- Lưu toàn bộ dữ liệu tại `structured_knowledge_graph.json`.

---

## Bước 3: Thử nghiệm sinh câu trả lời (Tested Generation)

### Mục tiêu

Đánh giá khả năng sinh câu trả lời của nhiều mô hình trên cùng một bộ benchmark gồm 200 câu hỏi thời trang.

### Thực hiện

Sinh câu trả lời cho bốn mô hình:

- Qwen3-VL 8B Instruct
- Qwen3-VL 8B Thinking
- Qwen3.5 9B Causal
- Gemma4 12B Instruct

Các kết quả đầu ra được lưu trong thư mục `tested/`.

---

## Bước 4: Thiết lập hệ thống đánh giá LLM-as-a-Judge (Evaluation)

### Mục tiêu

Sử dụng một mô hình ngôn ngữ lớn làm giám khảo tự động để đánh giá chất lượng câu trả lời.

### Thực hiện

- Sử dụng Llama 4 Scout 17B làm mô hình giám khảo.
- Đánh giá từng câu trả lời theo năm tiêu chí cốt lõi với thang điểm từ 1–5.
- Chuẩn hóa kết quả sang thang điểm 0.0–1.0.
- Lưu điểm số và phần giải thích chi tiết trong thư mục `evaluated/`.

---

## Bước 5: Báo cáo kết quả và trực quan hóa (Reporting & Visualization)

### Mục tiêu

Tổng hợp kết quả benchmark và trực quan hóa hiệu năng của các mô hình.

### Thực hiện

- Biên soạn báo cáo `FINAL_REPORT.md`.
- Xây dựng các biểu đồ phân tích gồm:
  - Bar chart
  - Box plot
  - Violin plot
- Phân tích kết quả benchmark, trong đó:
  - Dòng Qwen-VL đạt hiệu quả cao nhất về khả năng tư duy phối đồ.
  - Gemma4 đạt kết quả thấp nhất do xu hướng từ chối trả lời quá mức nhằm đảm bảo an toàn.

---

## Bước 6: Đồng bộ hóa và cập nhật hệ tiêu chí đánh giá (Hiện tại)

### Mục tiêu

Chuẩn hóa lại hệ thống đánh giá bằng cách thay đổi tên và định nghĩa các tiêu chí để phản ánh đúng mục tiêu của bài toán.

### Thực hiện

- Thay thế tiêu chí **Retrieval / Citation** bằng:
  - **Context Utilization**
  - **Trend Compliance**
- Đồng bộ toàn bộ mã nguồn, file cấu hình, dữ liệu JSON, báo cáo tổng hợp và biểu đồ phân tích.
- Đảm bảo toàn bộ hệ thống sử dụng thống nhất bộ tiêu chí đánh giá mới.
