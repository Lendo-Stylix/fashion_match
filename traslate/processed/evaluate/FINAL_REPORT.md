# Báo Cáo Đánh Giá Chất Lượng Cuối Cùng (FINAL_REPORT)

Tài liệu này tổng hợp kết quả đánh giá chi tiết chất lượng câu trả lời tư vấn thời trang của 4 mô hình trợ lý (OutfitMatch Stylist) trên bộ dữ liệu 200 mẫu thử nghiệm. Quá trình đánh giá được thực hiện tự động bằng phương pháp **LLM-as-a-judge** (Giám khảo Llama 4 Scout 17B) bám sát theo bộ tiêu chí chuẩn của **JUDGE_RUBRIC.md**.

---

## 1. Tóm Tắt Kết Quả Chung (Executive Summary)

Sau khi tiến hành kiểm thử toàn diện trên 800 lượt chạy (200 mẫu × 4 mô hình), kết quả cho thấy sự phân hóa chất lượng rõ rệt:

*   🥇 **Qwen3-VL 8B Instruct (Quán quân - 0.79/1.0)**: Thể hiện năng lực tư vấn vượt trội, bám sát tốt ngữ cảnh tài liệu RAG, tuân thủ chặt chẽ xu hướng phong cách và đưa ra câu trả lời có tính thẩm mỹ thời trang cao nhất.
*   🥈 **Qwen3-VL 8B Thinking (Á quân - 0.78/1.0)**: Bám sát nút mô hình dẫn đầu. Điểm mạnh lớn nhất là khả năng chống ảo giác đạt mức cao nhất hệ thống nhờ cơ chế suy nghĩ tự kiểm lỗi trước khi trả lời.
*   🥉 **Qwen3.5 9B Causal (Hạng ba - 0.76/1.0)**: Đạt độ chính xác cực cao trong việc tuân thủ phong cách thời trang và đề xuất các item theo đúng xu hướng.
*   🎖️ **Gemma4 12B Instruct (Hạng tư - 0.44/1.0)**: Đạt điểm thấp nhất do xu hướng trả lời quá cẩn trọng (Strict Refusal). Khi ngữ cảnh RAG bị lệch từ khóa hoặc thiếu chi tiết (dù câu hỏi có trong kiến thức nền), mô hình lập tức từ chối trả lời ("Tôi không tìm thấy thông tin"), dẫn đến mất điểm hàng loạt ở các tiêu chí cốt lõi.

---

## 2. Kết Quả Đánh Giá Tổng Hợp (General Benchmark Matrix)

Bảng thống kê điểm số trung bình của 200 mẫu thử quy đổi về thang điểm 0.0 - 1.0 (đi kèm điểm thô thang 1 - 5đ của Giám khảo):

| Mô Hình | Context Util. | Trend Comp. | Fashion QA | Faithfulness | Hallucination | **Điểm TB Cộng** | **Điểm Thô TB** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🥇 **Qwen3-VL 8B Instruct** | **0.67** (3.35đ) | 0.92 (4.60đ) | **0.75** (3.75đ) | **0.69** (3.45đ) | 0.91 (4.55đ) | **0.79** | **3.95đ** |
| 🥈 **Qwen3-VL 8B Thinking** | 0.63 (3.15đ) | 0.92 (4.60đ) | 0.72 (3.60đ) | 0.68 (3.40đ) | **0.94** (4.70đ) | **0.78** | **3.90đ** |
| 🥉 **Qwen3.5 9B Causal** | 0.60 (3.00đ) | **0.93** (4.65đ) | 0.68 (3.40đ) | 0.65 (3.25đ) | 0.93 (4.65đ) | **0.76** | **3.80đ** |
| 🎖️ **Gemma4 12B Instruct** | 0.32 (1.60đ) | 0.47 (2.35đ) | 0.34 (1.70đ) | 0.43 (2.15đ) | 0.64 (3.20đ) | **0.44** | **2.20đ** |

---

## 3. Phân Tích Chi Tiết Theo Tiêu Chí Đánh Giá

### 3.1. Context Utilization (Khai thác và Áp dụng Ngữ cảnh)
*Đo lường khả năng đọc hiểu, chắt lọc và tổng hợp thông tin từ ngữ cảnh để giải quyết trọn vẹn yêu cầu.*
*   **Dòng Qwen (Đạt từ 0.60 - 0.67)**: Khai thác ngữ cảnh linh hoạt, kết nối tốt các quy định thời trang và chi tiết sản phẩm vào câu trả lời cá nhân hóa cho người dùng.
*   **Gemma4 (Đạt 0.32)**: Thường xuyên bị trừ điểm nặng do trả về câu mặc định *"Tôi không tìm thấy thông tin"* khi tài liệu RAG nạp vào không chứa từ khóa trực tiếp (ví dụ: câu hỏi hỏi về "phong cách tiên phong" nhưng tài liệu chỉ ghi quy tắc "lựa chọn đồ bền lâu").

### 3.2. Trend Awareness & Style Compliance (Nắm bắt Xu hướng & Tuân thủ Phong cách)
*Đo lường mức độ đề xuất key_items phù hợp và né tránh các phong cách/xu hướng lỗi thời (outdated_trends_to_avoid).*
*   **Qwen3.5 9B dẫn đầu (0.93)**: Tư vấn trang phục nhạy bén, đề xuất các món đồ chủ đạo chính xác và tuân thủ cực tốt các quy tắc thẩm mỹ thời trang.
*   **Gemma4 (0.47)**: Mất điểm nhiều do các câu từ chối trả lời nên không đưa ra được các đề xuất xu hướng/phong cách phù hợp.

### 3.3. Fashion Knowledge QA (Hỏi đáp Kiến thức Thời trang)
*Đánh giá tư duy thời trang, khiếu thẩm mỹ và logic tư vấn thực tế.*
*   **Qwen3-VL Instruct dẫn đầu (0.75)**: Các câu trả lời phối màu sắc, lựa chọn dáng váy che khuyết điểm cơ thể mang tính ứng dụng cao, có chiều sâu chuyên môn.
*   **Gemma4 (0.34)**: Chỉ trả lời tốt được một số câu cơ bản về màu sắc trung tính, còn lại đa số từ chối tư vấn.

### 3.4. Faithfulness (Tính trung thực với ngữ cảnh)
*Đánh giá mức độ bám sát ngữ cảnh tài liệu cung cấp, tránh tự ý suy diễn vô căn cứ.*
*   Cả 3 mô hình Qwen giữ vững phong độ ổn định ở mức **0.65 - 0.69**, bám sát tài liệu RAG tốt và không bị lan man ngoài lề.

### 3.5. Hallucination (Chống ảo giác)
*Đo lường độ tin cậy của thông tin (không bịa đặt sản phẩm, giá tiền hoặc link giả).*
*   **Qwen3-VL Thinking dẫn đầu (0.94 - 4.70/5đ)**: Đạt điểm chống ảo giác cao nhất nhờ khối suy nghĩ tự sinh (`<think>`). Mô hình tự rà soát, đối chiếu các thông số sản phẩm và loại bỏ các lỗi sai trước khi in ra câu trả lời cuối cùng.
*   Gemma4 (0.64) bị trừ điểm ở các trường hợp từ chối trả lời nhưng vẫn bị giám khảo coi là chưa đáp ứng yêu cầu thực tế.

---

## 4. Phân Tích Hiệu Năng Từng Mô Hình

### 4.1. Qwen3-VL 8B Instruct (Điểm TB: 0.79)
*   **Ưu điểm**: Xử lý ngữ cảnh đa phương tiện tốt, câu trả lời thời trang chuyên nghiệp, có khiếu thẩm mỹ thực tế.
*   **Nhược điểm**: Đôi lúc câu trả lời hơi ngắn nếu tài liệu RAG đầu vào ngắn.

### 4.2. Qwen3-VL 8B Thinking (Điểm TB: 0.78)
*   **Ưu điểm**: Khả năng suy luận chiều sâu xuất sắc, loại bỏ ảo giác gần như tuyệt đối (0.94), cấu trúc câu trả lời mạch lạc.
*   **Nhược điểm**: Thời gian sinh câu trả lời lâu hơn do phải tốn thêm token suy nghĩ trong khối `<think>`.

### 4.3. Qwen3.5 9B Causal (Điểm TB: 0.76)
*   **Ưu điểm**: Định dạng đầu ra rất ổn định, tuân thủ phong cách và nắm bắt xu hướng tốt nhất hệ thống (0.93).
*   **Nhược điểm**: Không hỗ trợ đầu vào hình ảnh trực tiếp (chỉ thuần văn bản).

### 4.4. Gemma4 12B Instruct (Điểm TB: 0.44)
*   **Ưu điểm**: Khả năng chống ảo giác tốt trên lý thuyết.
*   **Nhược điểm**: Bị "Over-Alignment" (cân chỉnh quá mức an toàn). System Prompt quá chặt chẽ khiến mô hình từ chối trả lời hầu hết các câu hỏi RAG thực tế, phá hỏng khả năng ứng dụng.

---

## 5. Kết Luận & Khuyến Nghị

1.  **Lựa chọn mô hình cho Production**: 
    *   Nên ưu tiên sử dụng **Qwen3-VL 8B Instruct** vì có sự cân bằng tốt nhất giữa chất lượng tư vấn thời trang và độ tuân thủ RAG.
    *   Nếu ứng dụng đòi hỏi độ chính xác tuyệt đối, tránh ảo giác tối đa, hãy lựa chọn **Qwen3-VL 8B Thinking**.
2.  **Khuyến nghị tối ưu Gemma4**: Để phát huy sức mạnh 12B tham số của Gemma4, cần viết lại Prompt hệ thống nới lỏng bớt điều kiện RAG (ví dụ: cho phép mô hình sử dụng kiến thức nền chuyên môn để tư vấn nếu tài liệu ngữ cảnh chỉ ghi quy tắc chung).
3.  **Duy trì bảo trì mã nguồn**: Việc áp dụng stop token `<|im_end|>` và parser cắt chuỗi `</think>` đã khắc phục triệt để lỗi trôi chữ và rò rỉ định dạng đầu ra của dòng Qwen. Cần tiếp tục áp dụng cấu hình stop token này trong các phiên bản cập nhật tiếp theo.
