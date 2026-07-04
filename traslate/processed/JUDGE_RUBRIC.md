# Hướng Dẫn Chấm Điểm & Tiêu Chí Đánh Giá (JUDGE_RUBRIC)

Tài liệu này định nghĩa chi tiết tiêu chí chấm điểm và phương pháp đo lường đối với 3 loại Benchmark chính để đánh giá năng lực của các mô hình trợ lý thời trang (OutfitMatch Stylist).

---

## Loại Benchmark 1: Tool-Call Accuracy (Độ chính xác gọi Tool theo Trường)

Thay vì chỉ đo điểm F1 tổng quát, tiêu chí này đánh giá độ chính xác (Accuracy) bóc tách thực thể (entity extraction) của mô hình đối với từng trường dữ liệu (Field) cấu hình trong Tool-Call JSON.

### Các trường thực thể cần đánh giá:
1. **`occasion` (Dịp mặc / Bối cảnh)**: Đánh giá khả năng nhận diện bối cảnh sử dụng (đi làm, đi chơi, đám cưới, mùa đông, dạo phố, v.v.).
2. **`budget` (Ngân sách)**: Đánh giá khả năng trích xuất chính xác khoảng giá tiền mong muốn của khách hàng.
3. **`style_preference` (Phong cách ưa thích)**: Đánh giá khả năng bóc tách phong cách cụ thể (cổ điển, hiện đại, hiphop, tối giản, v.v.).
4. **`color_preference` (Màu sắc ưa thích)**: Trích xuất màu sắc khách hàng yêu cầu hoặc gợi ý.
5. **`body_shape` (Hình dáng cơ thể)**: Trích xuất khuyết điểm hoặc đặc điểm cơ thể cần che/làm nổi bật (dáng quả lê, vai rộng, thấp bé, v.v.).

### Thang chấm chi tiết từng trường:
* **Khớp hoàn toàn (100% Accuracy)**: Trích xuất đúng và đủ thực thể từ yêu cầu của người dùng sang đúng trường tương ứng trong JSON.
* **Khớp một phần (50% Accuracy)**: Trích xuất thiếu một số thực thể phụ hoặc bị sai lệch nhỏ (ví dụ: bối cảnh là "đi đám cưới mùa hè" nhưng chỉ trích xuất là "đi chơi").
* **Sai lệch hoàn toàn (0% Accuracy)**: Không trích xuất được thực thể hoặc gán sai trường (ví dụ: đưa giá tiền vào trường bối cảnh, bỏ qua hoàn toàn trường ngân sách).

---

## Loại Benchmark 2: Format Compliance (Độ chuẩn hóa định dạng đầu ra)

Đảm bảo đầu ra của luồng gọi tool (tool call flow) tuân thủ nghiêm ngặt cấu trúc định dạng máy (Machine-readable) mà không chứa ký tự rác.

### Tiêu chí đánh giá định dạng:
* **Chuẩn JSON / XML**: Đầu ra phải là chuỗi JSON hoặc XML chuẩn, có thể parse trực tiếp bằng các thư viện lập trình (`json.loads()` hoặc `xml.etree.ElementTree`) mà không phát sinh lỗi cú pháp (SyntaxError).
* **Không có ký tự rác**: Đầu ra không được chứa các ký tự rác đi kèm bên ngoài khối JSON/XML, ví dụ như:
  * Không chứa các đoạn hội thoại thừa: *"Đây là kết quả của bạn: { ... }"*
  * Không chứa các ký tự Markdown ngoài luồng bên ngoài khối code block (như văn bản tự do trước/sau ```json).
  * Không bị cắt cụt do hết giới hạn max_tokens.

### Thang đo:
* **Đạt (100%)**: Output parse được 100%, không chứa bất kỳ văn bản rác nào bên ngoài.
* **Không Đạt (0%)**: Output lỗi cú pháp, bị thiếu ngoặc, hoặc chứa văn bản rác dẫn đến parser bị crash.

---

## Loại Benchmark 3: LLM-as-a-Judge (Đánh giá chất lượng câu trả lời cuối cùng)

Dùng một mô hình ngôn ngữ lớn làm giám khảo (Judge) để chấm điểm câu trả lời tư vấn cuối cùng trên thang điểm từ 1 đến 5 (số nguyên) dựa trên 3 tiêu chí cốt lõi sau:

### Tiêu chí 3.1. Grounding Factuality (Độ xác thực căn cứ)
*Đánh giá xem lời khuyên của Stylist có dựa trên thông tin sản phẩm thực tế được tìm kiếm từ database (Database items) hay không.*
* **5 điểm**: Giải thích chính xác, dẫn chứng rõ ràng mã sản phẩm, mô tả sản phẩm hoàn toàn khớp với database.
* **3 điểm**: Trích dẫn đúng sản phẩm nhưng giải thích công dụng còn hời hợt, chưa gắn kết chặt chẽ với mô tả sản phẩm.
* **1 điểm**: Không sử dụng sản phẩm được tìm kiếm mà tự khuyên dùng sản phẩm ngẫu nhiên ngoài database.

### Tiêu chí 3.2. Anti-Hallucination (Chống ảo giác)
*Đánh giá xem mô hình có tự bịa đặt ra các sản phẩm không có thực trong database hoặc tự bịa ra giá tiền/khuyến mãi sai lệch hay không.*
* **5 điểm**: Hoàn toàn không có ảo giác. Tên sản phẩm, thông số chất liệu và giá tiền khớp 100% với database.
* **3 điểm**: Sản phẩm có thật nhưng bị nhớ sai một vài chi tiết nhỏ (ví dụ: nhầm chất liệu cotton thành thun co giãn).
* **1 điểm**: Áo/quần hoàn toàn do mô hình tự bịa ra, giá tiền bịa đặt vô căn cứ.

### Tiêu chí 3.3. Fashion Logic (Tư duy thời trang thực tế)
*Đánh giá chất lượng chuyên môn thời trang của lời khuyên mix-match (phối màu, che khuyết điểm cơ thể, cân đối tỷ lệ).*
* **5 điểm**: Lời khuyên cực kỳ chuyên nghiệp, đúng quy luật phối màu thời trang thực tế, đưa ra giải pháp che khuyết điểm cơ thể tối ưu (ví dụ: dáng quả lê nên mặc quần suông rộng/chân váy chữ A).
* **3 điểm**: Tư vấn đúng nhưng cơ bản, chưa sâu sắc, văn phong giống đọc sách giáo khoa lý thuyết hơn là tư vấn thực tế.
* **1 điểm**: Lời khuyên phản khoa học, sai quy tắc phối đồ cơ bản (ví dụ: người béo bụng khuyên mặc áo thun bó sát màu sáng).

---

## Định dạng Output JSON của Judge
Mỗi mẫu đánh giá phải được mô hình Judge xuất ra dưới dạng JSON object có cấu trúc:
```json
{
  "id": 1,
  "tool_call_compliance": 1.0,
  "format_compliance": 1.0,
  "llm_judge": {
    "grounding_factuality": 5,
    "anti_hallucination": 5,
    "fashion_logic": 4,
    "average": 4.67
  },
  "reasoning": "Mô hình bóc tách thực thể rất tốt, format chuẩn JSON. Lời khuyên có căn cứ sản phẩm thực tế, không bịa giá, tư vấn phối đồ hợp lý nhưng phần giải thích màu sắc cần chi tiết thêm."
}
```
