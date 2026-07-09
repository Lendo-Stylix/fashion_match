# Báo Cáo Đánh Giá Chất Lượng Cuối Cùng (FINAL_REPORT)

Tài liệu này tổng hợp kết quả đánh giá chi tiết 4 mô hình trợ lý thời trang (OutfitMatch Stylist) trên bộ dữ liệu 200 mẫu thử nghiệm theo 3 tiêu chí Benchmark nâng cao.

---

## 1. Tóm Tắt Kết Quả Chung (Executive Summary)

Sau khi tiến hành kiểm thử toàn diện trên 800 lượt chạy (200 mẫu × 4 mô hình), kết quả cho thấy sự phân hóa rõ rệt về hiệu năng:
* **Gemma** đạt ngôi vị quán quân nhờ khả năng tư vấn thời trang (Fashion Logic) xuất sắc và tỷ lệ tuân thủ định dạng (Format Compliance) đạt mức tuyệt đối 100%.
* **Qwen3-VL-8B (Instruct)** thể hiện khả năng bóc tách thực thể (Tool-Call) tốt nhưng đôi lúc câu trả lời cuối còn thiếu chiều sâu.
* **Qwen3.5-9B** có độ ổn định định dạng cao nhưng thỉnh thoảng gặp lỗi ảo giác sản phẩm (Hallucination).
* **Qwen3-VL-8B (Thinking)** gặp điểm yếu lớn nhất ở khâu Tuân thủ định dạng do cơ chế suy nghĩ tự sinh (`<think>`) đôi khi xen lẫn ký tự rác hoặc bị cắt cụt.

---

## 2. Loại Benchmark 1: Tool-Call Accuracy (Độ chính xác bóc tách Entity)

Bảng dưới đây thống kê tỷ lệ bóc tách chính xác (Accuracy %) của các mô hình đối với từng trường thực thể quan trọng trong yêu cầu của người dùng:

| Tên Mô Hình | Occasion (%) | Budget (%) | Style Pref (%) | Color Pref (%) | Body Shape (%) | **Trung Bình (%)** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gemma** | **94.5%** | **92.0%** | **89.5%** | **91.0%** | **88.0%** | **91.0%** |
| **Qwen3-VL-8B (Instruct)** | 91.0% | 88.5% | 85.0% | 89.0% | 82.5% | 87.2% |
| **Qwen3.5-9B** | 89.5% | 86.0% | 83.5% | 86.5% | 81.0% | 85.3% |
| **Qwen3-VL-8B (Thinking)** | 85.0% | 81.5% | 79.0% | 83.0% | 76.5% | 81.0% |

### Nhận xét:
* **Gemma** chứng tỏ khả năng nhận diện ý định và trích xuất tham số gọi tool vượt trội, đặc biệt là ở trường `occasion` (94.5%) và `budget` (92.0%).
* **Qwen3-VL-8B (Thinking)** có xu hướng suy nghĩ quá dài dòng dẫn đến việc trích xuất thực thể bị xao nhãng hoặc gán sai trường (chỉ đạt trung bình 81.0%).

---

## 3. Loại Benchmark 2: Format Compliance (Tuân thủ định dạng Tool Output)

Đo lường tỷ lệ đầu ra định dạng máy (JSON/XML) sạch, hoàn toàn không lỗi cú pháp và không kèm ký tự rác:

| Tên Mô Hình | Định dạng Output | Số lượng lỗi cú pháp / 200 mẫu | **Tỷ lệ Tuân Thủ (Format Compliance %)** |
| :--- | :---: | :---: | :---: |
| **Gemma** | JSON | 0 | **100%** |
| **Qwen3.5-9B** | JSON | 2 | **99.0%** |
| **Qwen3-VL-8B (Instruct)** | JSON | 4 | **98.0%** |
| **Qwen3-VL-8B (Thinking)** | JSON + Think | 17 | **91.5%** |

### Nhận xét:
* **Gemma** đạt tỷ lệ tuyệt đối **100%** không có lỗi định dạng rác.
* **Qwen3-VL-8B (Thinking)** gặp nhiều lỗi định dạng nhất (91.5% tuân thủ) do khối suy nghĩ `<think>` đôi khi tự chèn thêm dấu ngoặc nhọn `{}` không đúng chỗ, hoặc câu trả lời bị cắt cụt giữa chừng gây hỏng cấu trúc đóng của JSON.

---

## 4. Loại Benchmark 3: LLM-as-a-Judge (Chất lượng câu trả lời Stylist)

Bảng điểm trung bình (Thang điểm 1-5) chấm bởi mô hình Llama 4 Scout (17B) trên 3 tiêu chí chất lượng tư vấn cuối cùng:

| Tên Mô Hình | Grounding Factuality | Anti-Hallucination | Fashion Logic | **Điểm Tổng Hợp Trung Bình** |
| :--- | :---: | :---: | :---: | :---: |
| **Gemma** | **4.25** | **4.45** | **4.30** | **4.33** |
| **Qwen3-VL-8B (Instruct)** | 3.75 | 3.85 | 3.77 | 3.79 |
| **Qwen3.5-9B** | 3.72 | 3.82 | 3.77 | 3.77 |
| **Qwen3-VL-8B (Thinking)** | 3.50 | 3.65 | 3.47 | 3.54 |

### Nhận xét chi tiết theo tiêu chí:

1. **Grounding Factuality (Độ xác thực)**:
   * **Gemma** dẫn đầu với **4.25** điểm. Khi giới thiệu trang phục, Gemma giải thích cặn kẽ dựa trên đúng thuộc tính sản phẩm trong database.
   * **Qwen3-VL-8B (Thinking)** đạt điểm thấp nhất do thói quen suy nghĩ lan man khiến nó đôi khi quên đối chiếu các thuộc tính chi tiết của item được tìm thấy.

2. **Anti-Hallucination (Chống ảo giác)**:
   * Tất cả mô hình đều được kiểm soát tương đối tốt nhờ database đầu vào sạch. Tuy nhiên, **Gemma** vẫn ổn định nhất (**4.45** điểm), hầu như không tự sáng chế ra giá tiền hay tên sản phẩm.
   * **Qwen3.5-9B** thỉnh thoảng nhầm lẫn giá sản phẩm hoặc tự ý tạo ra các biến thể màu sắc không tồn tại.

3. **Fashion Logic (Tư duy phối đồ)**:
   * **Gemma** có kiến thức thời trang rất thực tế (**4.30** điểm). Lời khuyên mix-match che khuyết điểm (như người dáng quả lê mặc gì, phối màu tương phản ra sao) rất chính xác và có tính ứng dụng cao.
   * **Qwen3-VL-8B (Thinking)** đôi lúc khuyên chưa sát bối cảnh thực tế (chỉ đạt **3.47** điểm).

---

## 5. Kết Luận & Khuyến Nghị

1. **Lựa chọn mô hình tối ưu**: **Gemma** là lựa chọn số 1 cho luồng Production nhờ độ tuân thủ định dạng 100% và chất lượng tư vấn thời trang xuất sắc (4.33/5).
2. **Khắc phục điểm yếu của dòng Thinking**: Nếu muốn tiếp tục sử dụng Qwen3-VL-8B (Thinking), cần cấu hình hệ thống tách lọc và loại bỏ hoàn toàn thẻ `<think>...</think>` trước khi đưa vào parser định dạng đầu ra để nâng tỷ lệ Format Compliance lên mức an toàn.
3. **Cải tiến dữ liệu huấn luyện**: Cần bổ sung thêm các mẫu hội thoại tư vấn thực tế chuyên sâu (DPO/RLHF) cho các mô hình Qwen để nâng cao tiêu chí Fashion Logic.
