# BÁO CÁO QUÁ TRÌNH LÀM SẠCH VÀ CHẮT LỌC DỮ LIỆU (FASHION MATCH)
**Tài liệu hướng dẫn chi tiết về quy trình tiền xử lý dữ liệu song ngữ từ 40k dòng thô thành 10k dòng tinh túy**

> [!NOTE]
> Báo cáo này giải thích toàn bộ quy trình biến đổi dữ liệu, các tiêu chí loại bỏ nhiễu và cách thức cân bằng các chủ đề thời trang. Báo cáo được thiết kế chi tiết để tất cả các thành viên trong nhóm (kể cả không rành về code) đều có thể dễ dàng nắm bắt được.

---

## PHẦN I: QUY TRÌNH LÀM SẠCH VÀ CHUẨN HÓA DỮ LIỆU (`clean_dataset.py`)
Mục tiêu của giai đoạn này là biến đổi file dữ liệu thô `raw_unfiltered_dataset.csv` (~40k dòng) thành file dữ liệu sạch toàn bộ `cleaned_full_dataset.csv` (~37k dòng) bằng cách loại bỏ các lỗi dịch thuật, lỗi định dạng và trùng lặp.

### 1. Loại bỏ các dòng trống hoặc thiếu thông tin (NaN)
*   **Mục tiêu:** Loại bỏ hoàn toàn các bản ghi bị khuyết thiếu thông tin ở bất kỳ cột nào trong 4 cột: Câu hỏi gốc (EN), Câu trả lời gốc (EN), Câu hỏi dịch (VI), Câu trả lời dịch (VI).
*   **Cách xử lý:** Sử dụng thư viện Pandas để rà soát toàn bộ dataset và xóa ngay các dòng chứa giá trị rỗng (`dropna`).
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:*
        *   `original_input`: "What should I wear for a summer wedding?"
        *   `original_output`: "You should wear a lightweight linen suit."
        *   `translated_input`: "Tôi nên mặc gì cho tiệc cưới mùa hè?"
        *   `translated_output`: `NaN` (Trống do API dịch bị lỗi mạng)
    *   *Kết quả:* Dòng này bị loại bỏ hoàn toàn để tránh việc mô hình học một câu hỏi không có câu trả lời.

### 2. Chuẩn hóa Unicode NFC và dọn dẹp định dạng văn bản
*   **Mục tiêu:** Xử lý các lỗi font chữ tiếng Việt do gõ kiểu tổ hợp, loại bỏ các thẻ HTML thừa, các đường dẫn liên kết (URL), email bị lẫn vào dữ liệu và gộp các khoảng trắng thừa.
*   **Cách xử lý:** 
    *   Chuyển toàn bộ ký tự tiếng Việt về chuẩn NFC (Unicode dựng sẵn).
    *   Dùng các biểu thức chính quy (Regex) để xóa sạch thẻ HTML (`<p>`, `<a>`, `<br>`), đường dẫn `http/https`, email, và dọn dẹp các ký tự khoảng trắng thừa.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:* "Tìm đầm dạ hội đi tiệc <br> đẹp nhất tại trang web https://coolmate.me <p>giá rẻ</p>."
    *   *Kết quả sau xử lý:* "Tìm đầm dạ hội đi tiệc đẹp nhất tại trang web giá rẻ."

### 3. Loại bỏ câu chưa dịch (Dịch lỗi)
*   **Mục tiêu:** Phát hiện và loại bỏ các câu hỏi hoặc câu trả lời mà API dịch thuật bỏ sót (giữ nguyên tiếng Anh thay vì dịch sang tiếng Việt).
*   **Cách xử lý:** Đối chiếu chuỗi văn bản. Nếu câu hỏi dịch giống hệt câu hỏi gốc, hoặc câu trả lời dịch giống hệt câu trả lời gốc, dòng đó sẽ bị xóa.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:* 
        *   `original_output`: "Try wearing cotton shirts."
        *   `translated_output`: "Try wearing cotton shirts." (Dịch lỗi, giữ nguyên tiếng Anh)
    *   *Kết quả:* Dòng này bị loại bỏ vì nếu đưa vào train, mô hình sẽ học thói quen trả lời bằng tiếng Anh khi nhận câu hỏi tiếng Việt.

### 4. Khử trùng lặp thông minh (Smart Deduplication)
*   **Mục tiêu:** Xử lý trường hợp 1 câu hỏi tiếng Anh xuất hiện nhiều lần nhưng lại được dịch sang tiếng Việt thành các phiên bản dịch khác nhau (gây nhiễu và khiến mô hình bối rối).
*   **Cách xử lý:**
    *   Tính toán điểm chất lượng bản dịch (`translation_quality_score`) cho từng dòng dựa trên: Tỷ lệ số lượng từ (VI/EN gần mức 1.15 là tốt nhất), tỷ lệ bảo toàn thực thể thời trang và bảo toàn số lượng.
    *   Sắp xếp dữ liệu theo điểm chất lượng giảm dần.
    *   Chỉ giữ lại bản dịch tiếng Việt có chất lượng cao nhất cho mỗi cặp câu hỏi-trả lời tiếng Anh gốc và xóa bỏ các bản dịch kém chất lượng hơn.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị trùng lặp:*
        *   *Phiên bản A:* "Wear a red shirt" ➡️ "Mặc một cái áo sơ mi màu đỏ" (Điểm dịch: 0.95 - Chuẩn thực thể và từ ngữ).
        *   *Phiên bản B:* "Wear a red shirt" ➡️ "mặc đỏ sơ mi" (Điểm dịch: 0.40 - Dịch sai ngữ pháp).
    *   *Kết quả:* Hệ thống tự động giữ lại phiên bản A và xóa bỏ phiên bản B.

### 5. Nhận diện ngôn ngữ (Language Identification)
*   **Mục tiêu:** Đảm bảo cột tiếng Anh thực sự chứa tiếng Anh và cột tiếng Việt chứa tiếng Việt, loại bỏ các dòng bị lỗi ký tự đặc biệt hoặc dịch nhầm sang ngôn ngữ khác (tiếng Trung, tiếng Pháp...).
*   **Cách xử lý:** Sử dụng thư viện `langdetect` để tự động nhận dạng mã ngôn ngữ. Đối với tiếng Việt, nếu bộ nhận diện nghi ngờ nhưng câu có chứa các ký tự đặc trưng của tiếng Việt (`đ`, `á`, `ả`, `ề`...) thì vẫn được giữ lại.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:* 
        *   `translated_output`: "穿红色的衬衫" (Bản dịch bị chuyển nhầm sang tiếng Trung do lỗi mô hình dịch).
    *   *Kết quả:* Dòng này bị phát hiện phi-tiếng Việt và bị loại bỏ ngay lập tức.

### 6. Lọc theo độ dài câu và tỷ lệ số từ (Length & Ratio Filtering)
*   **Mục tiêu:** Loại bỏ các câu quá ngắn (không đủ nghĩa), quá dài (dễ gây tràn bộ nhớ GPU khi train mô hình) hoặc tỷ lệ dịch bị lệch bất thường.
*   **Cách xử lý:**
    *   Tính toán tỷ lệ: Số từ tiếng Việt / Số từ tiếng Anh. Chấp nhận tỷ lệ nằm trong khoảng từ `0.4` đến `2.5`.
    *   Đặt ngưỡng độ dài tối thiểu: Câu hỏi tiếng Việt >= 2 từ, Câu trả lời >= 5 từ.
    *   Đặt ngưỡng độ dài tối đa: Câu hỏi tiếng Việt <= 350 từ, Câu trả lời <= 700 từ.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:* Câu gốc tiếng Anh dài 20 từ nhưng bản dịch tiếng Việt chỉ có đúng 1 từ: "Đẹp" (Tỷ lệ từ: 1/20 = 0.05).
    *   *Kết quả:* Bị loại bỏ vì tỷ lệ quá lệch (nhỏ hơn 0.4), bản dịch đã bị mất mát thông tin nghiêm trọng.

### 7. Đối chiếu ngữ nghĩa - Số lượng và Thực thể thời trang
*   **Mục tiêu:** Đảm bảo các thông tin quan trọng như con số (ví dụ: số lượng sản phẩm, kích thước) và từ khóa thời trang (mùa, chất liệu, dáng người) không bị dịch thiếu hoặc dịch sai nghĩa.
*   **Cách xử lý:**
    *   Tìm kiếm tất cả các con số có từ 2 chữ số trở lên ở câu gốc và câu dịch. Nếu câu gốc có số mà câu dịch bị mất số đó -> Loại bỏ dòng.
    *   Tìm kiếm các từ khóa thời trang chính (ví dụ: dáng người `pear` - quả lê, chất liệu `linen` - vải lanh). Nếu câu gốc có từ khóa thời trang mà câu dịch không chứa bất kỳ từ khóa tiếng Việt tương ứng nào -> Loại bỏ dòng.
*   **Ví dụ minh họa:**
    *   *Dữ liệu thô bị lỗi:* 
        *   `original_input`: "I need 2 cotton t-shirts."
        *   `translated_input`: "Tôi cần các áo thun bông." (Bị mất con số quan trọng "2").
    *   *Kết quả:* Dòng này bị loại bỏ để tránh mô hình học thói quen trả lời thiếu chi tiết định lượng.

---

## PHẦN II: QUY TRÌNH CHẮT LỌC PHÂN TẦNG VÀ CÂN BẰNG NGỮ CẢNH (`prune_dataset.py`)
Mục tiêu của giai đoạn này là lấy file dữ liệu sạch `cleaned_full_dataset.csv` (~37k dòng) để chắt lọc lấy đúng 10,000 dòng chất lượng cao nhất và cân bằng ngữ cảnh các chủ đề, lưu thành `cleaned_balanced_10k_dataset.csv` và `training_ready_10k_dataset.jsonl`.

### 1. Cách chấm điểm chất lượng câu (`pruning_score`)
Mỗi dòng dữ liệu được chấm điểm từ 0.0 đến 1.0 dựa trên 3 tiêu chí chính:
*   **Độ dài câu trả lời (Chiếm 50% số điểm):** Ưu tiên các câu trả lời tư vấn chi tiết từ 80 đến 300 từ. Nếu câu trả lời quá ngắn hoặc quá dài sẽ bị trừ điểm.
*   **Độ phức tạp của câu hỏi (Chiếm 30% số điểm):** Đếm số nhóm thực thể thời trang xuất hiện trong câu hỏi (Dáng người, Mùa, Chất liệu...). Càng nhiều thực thể phối hợp (tối đa 3), điểm càng cao.
*   **Tỷ lệ từ dịch thuật (Chiếm 20% số điểm):** Độ lệch từ dịch càng sát tỷ lệ chuẩn 1.15 càng được điểm tối đa.

### 2. Thuật toán lấy mẫu phân tầng theo hạn ngạch (Stratified Quota Sampling)
Thay vì lọc Top-K toàn cục (dễ dẫn đến việc các câu hỏi thuộc chủ đề hiếm như dáng người bị loại sạch), thuật toán thực hiện chia hạn ngạch (quota) chi tiết cho từng nhóm chủ đề chính:
*   **Bước 1 - Phân loại chủ đề:** Dựa vào từ khóa tiếng Anh để phân loại các câu vào 8 chủ đề chính: *Dáng người, Phong cách, Mùa & Thời tiết, Ngân sách, Chất liệu, Dịp, Danh mục sản phẩm, và Chung (General)*.
*   **Bước 2 - Lọc theo hạn ngạch chủ đề:**
    *   **Nhóm hiếm (Dáng người, Ngân sách):** Nếu số câu thực tế nhỏ hơn hạn ngạch (ví dụ Dáng người chỉ có 1,269 câu trong khi chỉ tiêu là 2,000), hệ thống **giữ lại toàn bộ 100%** dữ liệu của nhóm đó để tránh mất ngữ cảnh.
    *   **Nhóm thừa (Phong cách, Dịp...):** Hệ thống chỉ lọc lấy số lượng câu có điểm `pruning_score` cao nhất cho tới khi vừa đủ hạn ngạch đặt ra.
*   **Bước 3 - Bù đắp từ pool dư thừa:** Sau lượt lọc đầu tiên, số lượng dòng thu được là 8,397 dòng (do các nhóm hiếm không đủ quota). Hệ thống gom toàn bộ dữ liệu dư thừa của tất cả các nhóm, xếp theo điểm chất lượng và lấy 1,603 dòng tốt nhất để bù đắp cho đủ 10,000 dòng.

### 3. Kết quả phân bổ danh mục trong tập 10k cuối cùng
*   👗 **Dịp (Occasions):** 2,403 dòng (24.03%) - Tư vấn phối đồ đi làm, đi chơi, đám cưới...
*   🎨 **Phong cách (Styles):** 2,000 dòng (20.00%) - Thời trang streetwear, tối giản, retro...
*   ☀️ **Mùa & Thời tiết (Weather & Seasons):** 1,500 dòng (15.00%) - Lựa chọn trang phục theo mùa đông, hè, xuân, thu...
*   💬 **Chung (General):** 1,400 dòng (14.00%) - Các tư vấn chung không chứa nhãn.
*   👤 **Dáng người (Body Shape):** 1,269 dòng (12.69%) - Đầy đủ dáng đồng hồ cát, dáng lê, dáng táo, tam giác ngược...
*   🧶 **Chất liệu (Materials):** 800 dòng (8.00%) - Chất vải cotton, linen, da, len, nhung...
*   🎒 **Danh mục (Categories):** 500 dòng (5.00%) - Các loại quần áo như đầm, vest, blazer, sơ mi...
*   💰 **Ngân sách (Budget):** 128 dòng (1.28%) - Phân khúc giá rẻ, trung bình, đồ cao cấp...

---

## KẾT LUẬN
Nhờ quy trình xử lý 2 giai đoạn làm sạch và phân tầng này:
1.  **Dữ liệu không còn nhiễu hại:** Tránh được các lỗi dịch thuật, lỗi font chữ và trùng lặp bản dịch.
2.  **Mô hình có tư duy toàn diện:** Tỷ lệ phân bổ 10k dòng cân bằng giúp mô hình có tri thức rộng khắp các chủ đề thời trang, đặc biệt là tư vấn dáng người và chất liệu, không bị tình trạng thiên lệch hoặc chỉ trả lời tốt một chủ đề cố định.
