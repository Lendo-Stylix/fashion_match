# Hướng Dẫn Chấm Điểm & Tiêu Chí Đánh Giá (JUDGE_RUBRIC)

Tài liệu này định nghĩa chi tiết các tiêu chí chấm điểm và phương pháp đánh giá dựa trên phương pháp **LLM-as-a-judge** nhằm đánh giá chất lượng câu trả lời tư vấn thời trang của mô hình trợ lý (OutfitMatch Stylist).

Đầu ra của mô hình được đánh giá toàn diện trên thang điểm từ 1 đến 5 (số nguyên), sau đó được **quy đổi về thang điểm 0.0 - 1.0 (bằng cách lấy điểm số thô chia cho 5.0)** để tính toán điểm trung bình hệ thống.

---

## 📊 Bảng Quy Đổi Điểm Số

| Điểm số thô (Giám khảo chấm) | Điểm quy đổi (Lưu trong JSON & Báo cáo) | Đánh giá chất lượng |
| :---: | :---: | :--- |
| **5 điểm** | **1.0** | Xuất sắc (Hoàn hảo) |
| **4 điểm** | **0.8** | Tốt |
| **3 điểm** | **0.6** | Trung bình |
| **2 điểm** | **0.4** | Yếu |
| **1 điểm** | **0.2** | Rất kém / Không đạt |

---

## 1. Các Tiêu Chí Đánh Giá Chi Tiết

### Tiêu chí 1.1. Context Utilization (Khai thác và Áp dụng Ngữ cảnh)
*Đánh giá khả năng đọc hiểu, chắt lọc và tổng hợp thông tin từ ngữ cảnh (retrieved_contexts) được cung cấp sẵn để giải quyết trọn vẹn yêu cầu của người dùng.*
* **5 điểm (Quy đổi: 1.0)**: Mô hình khai thác triệt để và chính xác các thông tin có giá trị nhất từ ngữ cảnh. Câu trả lời tổng hợp đầy đủ các quy tắc phối đồ và chi tiết sản phẩm được cung cấp để giải quyết trực tiếp và trọn vẹn câu hỏi.
* **3 điểm (Quy đổi: 0.6)**: Mô hình có sử dụng thông tin từ ngữ cảnh nhưng chỉ trích xuất được một phần. Bỏ sót các chi tiết, giải pháp hoặc quy tắc quan trọng có trong tài liệu, dẫn đến câu trả lời đúng nhưng chưa đủ sâu sắc.
* **1 điểm (Quy đổi: 0.2)**: Mô hình phớt lờ hoàn toàn các thông tin hữu ích trong ngữ cảnh, hoặc trả lời chung chung không dựa trên tài liệu được cung cấp

### Tiêu chí 1.2. Trend Awareness & Style Compliance (Nắm bắt Xu hướng & Tuân thủ Phong cách)
*Đánh giá mức độ nhạy bén về thời trang của mô hình thông qua việc đề xuất chính xác các món đồ chủ đạo (key_items) và khả năng né tránh tuyệt đối các phong cách/xu hướng đã lỗi thời (outdated_trends_to_avoid) được quy định trong đồ thị tri thức.*
* **5 điểm (Quy đổi: 1.0)**: Mô hình khéo léo lồng ghép các key_items phù hợp vào câu trả lời để tư vấn cho người dùng. Tuyệt đối tuân thủ các quy tắc thẩm mỹ, không gợi ý bất kỳ món đồ hay cách phối nào nằm trong danh sách outdated_trends_to_avoid.
* **3 điểm (Quy đổi: 0.6)**: Câu trả lời an toàn, có tư vấn trang phục nhưng các gợi ý khá mờ nhạt, không làm nổi bật được các key_items đặc trưng của phong cách đó. Hoặc, mô hình có nhắc đến một chi tiết nhỏ mang hơi hướng lỗi thời nhưng chưa làm hỏng tổng thể bộ trang phục.
* **1 điểm (Quy đổi: 0.2)**: Mô hình đưa ra những lời khuyên thời trang đi ngược lại tiêu chuẩn của danh mục, trực tiếp khuyên người dùng sử dụng các món đồ, màu sắc hoặc cách phối nằm trong danh sách

### Tiêu chí 1.3. Fashion Knowledge QA (Hỏi đáp Kiến thức Thời trang)
*Đánh giá khả năng tư vấn thời trang chuyên sâu và giải đáp thắc mắc của người dùng (phối màu, dáng người, chọn trang phục, xu hướng thời trang cần tránh) theo đúng logic thời trang chuyên nghiệp.*
* **5 điểm (Quy đổi: 1.0)**: Câu trả lời thể hiện tư duy thời trang sâu sắc, đưa ra giải pháp mix-match tối ưu cho từng dáng người/màu da, tuân thủ nghiêm ngặt các quy tắc thẩm mỹ thực tế.
* **3 điểm (Quy đổi: 0.6)**: Câu trả lời ở mức cơ bản, chỉ nêu lý thuyết chung chung (giống như đọc sách), chưa mang tính cá nhân hóa cao cho người hỏi.
* **1 điểm (Quy đổi: 0.2)**: Lời khuyên sai lệch kiến thức thời trang cơ bản hoặc khuyên phản thẩm mỹ (ví dụ: người béo bụng khuyên mặc áo thun bó sát màu sáng).

### Tiêu chí 1.4. Faithfulness (Tính trung thực với ngữ cảnh)
*Đánh giá xem câu trả lời của trợ lý có trung thực và hoàn toàn dựa trên ngữ cảnh được cung cấp (sản phẩm thực tế, tài liệu tri thức) hay không, tránh việc suy diễn vô căn cứ hoặc tự ý thêm thắt thông tin ngoài ngữ cảnh.*
* **5 điểm (Quy đổi: 1.0)**: Tất cả các thông tin đưa ra (chất liệu, công dụng, kiểu dáng) đều có căn cứ trực tiếp từ ngữ cảnh. Không suy diễn quá mức.
* **3 điểm (Quy đổi: 0.6)**: Phần lớn thông tin trung thực, nhưng có một vài suy diễn nhỏ không gây hại nhiều đến tính chính xác (ví dụ suy luận thêm về cảm giác mặc dù ngữ cảnh chỉ ghi chất liệu).
* **1 điểm (Quy đổi: 0.2)**: Câu trả lời chứa nhiều thông tin suy diễn tự do, không dựa vào ngữ cảnh được cung cấp.

### Tiêu chí 1.5. Hallucination (Chống ảo giác)
*Đo lường mức độ tin cậy của thông tin, đánh giá xem mô hình có tự bịa đặt ra các sản phẩm không có thực, giá tiền giả, thuộc tính giả hoặc link giả không tồn tại trong tài liệu hay không.*
* **5 điểm (Quy đổi: 1.0)**: Hoàn toàn không có ảo giác. Tên sản phẩm, thông số chất liệu, giá tiền và link dẫn khớp 100% với database và ngữ cảnh.
* **3 điểm (Quy đổi: 0.6)**: Sản phẩm có thật nhưng bị nhớ sai một vài chi tiết nhỏ (ví dụ: nhầm chất liệu cotton thành thun co giãn, sai lệch nhỏ về giá tiền).
* **1 điểm (Quy đổi: 0.2)**: Tự bịa đặt ra các sản phẩm hoàn toàn không có thực trong database, bịa đặt giá tiền hoặc khuyến mãi vô căn cứ.

---

## 2. Định Dạng Đầu Ra JSON Đánh Giá

Kết quả đánh giá của toàn bộ tập dữ liệu sẽ được lưu dưới dạng một danh sách các đối tượng JSON có cấu trúc như sau:

```json
[
  {
    "id": "Q-001",
    "question": "Tôi rất muốn thêm những chiếc mũ cổ điển vào tủ quần áo...",
    "ground_truth": "Những chiếc mũ fedora, mũ rộng vành, và mũ beret...",
    "contexts": ["..."],
    "metadata": { "category": "timeless_fashion" },
    "retrieved_contexts": ["..."],
    "answer": "Để có phong cách cổ điển, bạn nên chọn mũ fedora hoặc beret màu đen, navy...",
    
    "evaluation": {
      "context_utilization": 1.0, 
      "faithfulness": 0.6, 
      "hallucination": 0.8,
      "trend_compliance": 0.2,
      "reasoning": "Faithfulness bị trừ điểm về mức 0.6 vì tự suy luận thêm một số loại vải không có trong retrieved_contexts."
    }
  }
]
```
