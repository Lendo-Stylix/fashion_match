# Báo cáo Benchmark LLM OutfitMatch (Stylist)

**Số lượng mẫu đã đánh giá:** 200 / 200

## 1. LLM-as-a-Judge Scores (Thang 1-5)
| Tiêu chí | Điểm trung bình | Đánh giá |
|----------|-----------------|----------|
| **Natural & Polite** | 4.48/5.0 | Đo lường độ tự nhiên và văn phong chuẩn Stylist |
| **Polite Decline** | 4.96/5.0 | Đo lường khả năng xử lý câu hỏi ngoài lề / chống Jailbreak |
| **Accuracy (No Hallucination)** | 3.85/5.0 | Đo lường tính chuẩn xác của lời khuyên, không bịa thông tin |

## 2. NLP Metrics (Độ trùng khớp với Reference)
| Tiêu chí | Điểm trung bình | Ghi chú |
|----------|-----------------|----------|
| **ROUGE-L F1** | 0.3481 | Độ trùng lặp từ vựng chính xác |
| **Cosine Similarity** | 0.0000 | Độ tương đồng về mặt ý nghĩa ngữ nghĩa |

---
*Báo cáo được tự động tạo từ script benchmark_system.*
