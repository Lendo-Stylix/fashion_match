# Hệ thống Benchmark OutfitMatch (Stylist LLM)

Thư mục này chứa toàn bộ mã nguồn và công cụ tự động hóa để đánh giá năng lực của các mô hình LLM đóng vai trò là "Trợ lý Thời trang" (OutfitMatch), cụ thể là mô hình Qwen3.5-9B. 

Hệ thống kết hợp giữa **phương pháp đánh giá tự động (NLP Metrics)** và **sức mạnh suy luận (LLM-as-a-judge)** để mang lại kết quả toàn diện nhất.

## 📦 Yêu cầu cài đặt
Hãy đảm bảo bạn đã cài đặt các thư viện cần thiết trước khi chạy:
```bash
pip install rouge-score sentence-transformers torch tqdm
```

## 🚀 Luồng thực thi (Pipeline)

Hệ thống được thiết kế chạy qua 3 bước độc lập, giúp bạn dễ dàng theo dõi và xử lý nếu bị ngắt quãng.

### Bước 1: Tính toán các chỉ số NLP truyền thống
Script này sẽ quét qua file kết quả (ví dụ `t2_qwen35_9b_outputs_part1.json`) và so sánh nó với nhãn tham chiếu (Reference) bằng thuật toán ROUGE-L.
```bash
python run_nlp_metrics.py
```
> **Kết quả:** Sinh ra file `nlp_scores.json` lưu trữ điểm độ chính xác từ vựng cho từng câu.

### Bước 2: Đánh giá bằng LLM-as-a-judge
Đây là lõi của hệ thống. Dựa trên file `JUDGE_RUBRIC.md` (Thang điểm 1-5 cực kỳ nghiêm ngặt), script này sẽ sử dụng một LLM độc lập làm giám khảo.
Để tránh quá tải Context Window, hệ thống sẽ chia data thành nhiều batch (mặc định 10 câu/batch).
```bash
python auto_judge.py
```
> **Kết quả:** Sinh ra và cập nhật file `eval_state.json`. Nếu chạy bị lỗi giữa chừng, lần chạy sau hệ thống sẽ tự động resume (chạy tiếp) từ batch bị lỗi.

### Bước 3: Xuất báo cáo tổng hợp
Cuối cùng, script này sẽ đọc điểm NLP từ Bước 1 và điểm LLM từ Bước 2 để xuất ra bản tổng hợp.
```bash
python generate_report.py
```
> **Kết quả:** Tạo ra file `FINAL_REPORT.md` với các thống kê điểm số.

## 📂 Cấu trúc các file chính
- `run_nlp_metrics.py`: Tính điểm ROUGE.
- `batch_manager.py`: Chứa các class hỗ trợ lưu và tải file JSON an toàn.
- `auto_judge.py`: Gọi bộ đánh giá tự động.
- `generate_report.py`: Script xuất báo cáo.
- `JUDGE_RUBRIC.md`: Tiêu chuẩn để LLM Judge căn cứ vào đó chấm điểm (Chống thiên kiến và ảo giác).
- `eval_state.json`: File lưu trạng thái chấm điểm (sẽ được tự động tạo).
- `FINAL_REPORT.md`: Báo cáo kết quả cuối cùng.

---
**Lưu ý cho Team:** 
Vui lòng tham khảo thêm file `benchmark_analysis.md` đính kèm trong thư mục này để xem phân tích chuyên sâu về lý do tại sao mô hình bị mất điểm và định hướng Fine-Tuning tiếp theo.
