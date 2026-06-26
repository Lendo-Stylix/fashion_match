# Module Tiền xử lý và Chuẩn hóa Dữ liệu Thời trang (Fashion Match Preprocessing)

Thư mục này chứa toàn bộ các công cụ, mã nguồn và tài liệu phục vụ cho quy trình tiền xử lý, làm sạch và chắt lọc dữ liệu song ngữ (Anh - Việt) phục vụ cho việc Fine-tuning mô hình ngôn ngữ lớn (LLM) trong dự án **Fashion Match**.

---

## 📂 Cấu trúc Thư mục và Các File Dữ liệu

Dành cho các thành viên trong nhóm, cấu trúc thư mục được sắp xếp hợp lý như sau:

```text
traslate/
├── 📂 raw/                              # [DỮ LIỆU ĐẦU VÀO] Chứa dữ liệu dịch thô ban đầu
│   ├── 📄 raw_unfiltered_dataset.csv    - File dữ liệu gốc thô gồm ~40k dòng (chứa nhiều lỗi và nhiễu)
│   └── 📓 visualize.ipynb               - Jupyter Notebook để xem phân tích dữ liệu thô
├── 📂 processed/                        # [DỮ LIỆU ĐẦU RA SẠCH] Kết quả sau khi xử lý và lọc
│   ├── 📄 cleaned_full_dataset.csv      - File dữ liệu đã làm sạch 100% các lỗi dịch thuật (~37k dòng)
│   ├── 📄 cleaned_balanced_10k_dataset.csv - Bản đối chiếu 10k dòng tinh tuyển dạng bảng CSV
│   ├── 📄 training_ready_10k_dataset.jsonl - File dữ liệu 10k dòng dạng ChatML dùng trực tiếp để train LLM
│   └── 📓 visualize_processed.ipynb     - Jupyter Notebook trực quan hóa kết quả sau làm sạch
├── 📂 translated/                       # [CHECKPOINTS] Nơi lưu tiến trình dịch thuật trung gian
├── 📄 clean_dataset.py                  # [SCRIPT 1] Mã nguồn chạy làm sạch dữ liệu
├── 📄 prune_dataset.py                  # [SCRIPT 2] Mã nguồn phân tầng và lọc dữ liệu 10k dòng
├── 📄 bao_cao_thong_ke_chuan_hoa.docx   # Báo cáo quá trình xử lý chi tiết (Định dạng Word chuyên nghiệp)
├── 📄 bao_cao_thong_ke_chuan_hoa.md     # Báo cáo quá trình xử lý chi tiết (Xem nhanh dạng Markdown)
├── 📄 translate.py / repair.py          # Các công cụ hỗ trợ dịch thuật tự động qua API Gemini
├── 📓 finetune.ipynb                    # Jupyter Notebook hướng dẫn chạy train mô hình trên Kaggle
└── 📄 README.md                         # Hướng dẫn này
```

---

## 🚀 Hướng dẫn Quy trình Chạy 2 Bước đơn giản

Nếu bạn muốn chạy lại quy trình xử lý dữ liệu từ đầu để cập nhật file mới, hãy mở cửa sổ dòng lệnh (Terminal) và chạy 2 lệnh sau:

### Bước 1: Làm sạch dữ liệu gốc
Lệnh này sẽ quét file thô `raw_unfiltered_dataset.csv`, loại bỏ các dòng bị dịch lỗi, trùng lặp, sai ngữ pháp, và xuất ra file sạch toàn bộ `cleaned_full_dataset.csv`.
```bash
python clean_dataset.py
```

### Bước 2: Chắt lọc phân tầng và xuất tập dữ liệu 10k dòng
Lệnh này sẽ lấy file sạch ở Bước 1, chấm điểm chất lượng câu tư vấn, phân nhóm chủ đề, tự động cân bằng số lượng câu hỏi giữa các nhóm (Dáng người, Thời tiết, Phong cách, Dịp...) và xuất ra file huấn luyện `training_ready_10k_dataset.jsonl`.
```bash
python prune_dataset.py
```

---

## 📈 Cách Sử dụng Dữ liệu để Train mô hình trên Kaggle

1. Copy (hoặc tải lên) file **`processed/training_ready_10k_dataset.jsonl`** lên hệ thống Kaggle Dataset của bạn.
2. Mở file [finetune.ipynb](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/traslate/finetune.ipynb) bằng Jupyter Notebook hoặc import trực tiếp notebook này vào Kaggle.
3. Thay đổi đường dẫn `data_path` trỏ đến file `.jsonl` bạn vừa tải lên trên Kaggle và nhấn nút Run All để bắt đầu quá trình huấn luyện mô hình.

---

## 📄 Tài liệu Đọc thêm
*   Để hiểu chi tiết các thuật toán lọc câu trống (NaN), lọc độ dài, đối chiếu thực thể thời trang cũng như thuật toán phân tầng, vui lòng đọc bản báo cáo quá trình tại: [bao_cao_thong_ke_chuan_hoa.md](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/traslate/bao_cao_thong_ke_chuan_hoa.md) hoặc mở trực tiếp file Word [bao_cao_thong_ke_chuan_hoa.docx](file:///d:/Learning/ky_5/DPL302m/Project/fashion_match/traslate/bao_cao_thong_ke_chuan_hoa.docx).
