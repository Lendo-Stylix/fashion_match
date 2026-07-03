import json
import os

DATA_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\t2_qwen35_9b_outputs_part1.json"
STATE_FILE = r"d:\FPT\Ki_V\DPL302m\group_project\kaggle\benchmark_system\eval_state.json"
BATCH_SIZE = 10

def get_next_batch():
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    start_idx = state["processed_count"]
    if start_idx >= state["total_samples"]:
        return "Đã chấm xong toàn bộ 200 câu!"

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    batch = data[start_idx : start_idx + BATCH_SIZE]
    
    batch_text = f"=== BATCH {state['last_batch_id'] + 1} (Từ câu {start_idx} đến {start_idx + len(batch) - 1}) ===\n\n"
    for i, item in enumerate(batch):
        idx = start_idx + i
        batch_text += f"--- Câu {idx} ---\n"
        batch_text += f"**Prompt:** {item.get('prompt')}\n"
        batch_text += f"**Reference:** {item.get('reference_text')}\n"
        batch_text += f"**Generated:** {item.get('generated_text')}\n\n"
    
    return batch_text

def save_batch_results(results_list):
    """
    results_list: list các dict chứa điểm số của LLM.
    """
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    state["results"].extend(results_list)
    state["processed_count"] += len(results_list)
    state["last_batch_id"] += 1
    
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print(f"Đã lưu thành công. Tổng số câu đã chấm: {state['processed_count']}/{state['total_samples']}")

if __name__ == "__main__":
    # In ra batch tiếp theo để AI đọc và chấm điểm
    print(get_next_batch())
