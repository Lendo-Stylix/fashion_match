import json
import os
from rouge_score import rouge_scorer
from tqdm import tqdm

DATA_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\t2_qwen35_9b_outputs_part1.json"
OUTPUT_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\benchmark_system\nlp_scores.json"

def calculate_nlp_metrics():
    print("Loading data...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=False)

    results = []
    print("Calculating metrics...")
    for i, item in enumerate(tqdm(data)):
        ref = item.get("reference_text", "")
        gen = item.get("generated_text", "")

        # Tính ROUGE
        rouge_scores = scorer.score(ref, gen)

        results.append({
            "id": i,
            "rougeL_fmeasure": rouge_scores['rougeL'].fmeasure,
            "cosine_similarity": 0.0 # Bỏ qua vì lỗi môi trường Torch
        })

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Done! NLP scores saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    # Yêu cầu cài đặt: pip install rouge-score sentence-transformers
    calculate_nlp_metrics()
