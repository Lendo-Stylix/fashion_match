import json

NLP_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\benchmark_system\nlp_scores.json"
STATE_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\benchmark_system\eval_state.json"
REPORT_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\benchmark_system\FINAL_REPORT.md"

def generate_report():
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    try:
        with open(NLP_FILE, 'r', encoding='utf-8') as f:
            nlp_scores = json.load(f)
    except FileNotFoundError:
        nlp_scores = []

    llm_results = state.get("results", [])
    
    if len(llm_results) == 0:
        print("Chưa có kết quả chấm điểm từ LLM Judge!")
        return

    # Tính điểm trung bình LLM
    avg_natural = sum(r.get("natural_score", 0) for r in llm_results) / len(llm_results)
    avg_decline = sum(r.get("decline_score", 0) for r in llm_results) / len(llm_results)
    avg_accuracy = sum(r.get("anti_hallucination_score", 0) for r in llm_results) / len(llm_results)

    # Tính điểm trung bình NLP (nếu có đủ số lượng)
    avg_rouge = 0
    avg_cosine = 0
    if len(nlp_scores) > 0:
        # Chỉ lấy bằng với số lượng đã chấm
        valid_nlp = nlp_scores[:len(llm_results)]
        avg_rouge = sum(r.get("rougeL_fmeasure", 0) for r in valid_nlp) / len(valid_nlp)
        avg_cosine = sum(r.get("cosine_similarity", 0) for r in valid_nlp) / len(valid_nlp)

    md_content = f"""# Báo cáo Benchmark LLM OutfitMatch (Stylist)

**Số lượng mẫu đã đánh giá:** {len(llm_results)} / {state.get('total_samples', 200)}

## 1. LLM-as-a-Judge Scores (Thang 1-5)
| Tiêu chí | Điểm trung bình | Đánh giá |
|----------|-----------------|----------|
| **Natural & Polite** | {avg_natural:.2f}/5.0 | Đo lường độ tự nhiên và văn phong chuẩn Stylist |
| **Polite Decline** | {avg_decline:.2f}/5.0 | Đo lường khả năng xử lý câu hỏi ngoài lề / chống Jailbreak |
| **Accuracy (No Hallucination)** | {avg_accuracy:.2f}/5.0 | Đo lường tính chuẩn xác của lời khuyên, không bịa thông tin |

## 2. NLP Metrics (Độ trùng khớp với Reference)
| Tiêu chí | Điểm trung bình | Ghi chú |
|----------|-----------------|----------|
| **ROUGE-L F1** | {avg_rouge:.4f} | Độ trùng lặp từ vựng chính xác |
| **Cosine Similarity** | {avg_cosine:.4f} | Độ tương đồng về mặt ý nghĩa ngữ nghĩa |

---
*Báo cáo được tự động tạo từ script benchmark_system.*
"""
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"Đã tạo báo cáo thành công tại: {REPORT_FILE}")

if __name__ == "__main__":
    generate_report()
