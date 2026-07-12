import json
import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

base_dir = r"d:\Learning\ky_5\DPL302m\Project\fashion_match\traslate\processed"

# Load files
test1_path = os.path.join(base_dir, "test_part1_200.json")
test2_path = os.path.join(base_dir, "test_part2_200.json")
balanced_path = os.path.join(base_dir, "cleaned_balanced_10k_dataset.csv")

if not os.path.exists(test1_path) or not os.path.exists(test2_path):
    print("Error: test files do not exist yet!")
    sys.exit(1)

with open(test1_path, 'r', encoding='utf-8') as f:
    part1 = json.load(f)
with open(test2_path, 'r', encoding='utf-8') as f:
    part2 = json.load(f)

balanced_df = pd.read_csv(balanced_path)
balanced_inputs = set(balanced_df['translated_input'].dropna().str.strip().str.lower().tolist())

print("=== VERIFYING GENERATED TEST DATASETS ===")

# 1. Check counts
print(f"Part 1 length: {len(part1)} (Expected: 200) - {'PASS' if len(part1) == 200 else 'FAIL'}")
print(f"Part 2 length: {len(part2)} (Expected: 200) - {'PASS' if len(part2) == 200 else 'FAIL'}")

# 2. Check overlap with 10k dataset
part1_inputs = [item['messages'][0]['content'].strip().lower() for item in part1]
part2_inputs = [item['messages'][0]['content'].strip().lower() for item in part2]

part1_overlap = sum(1 for q in part1_inputs if q in balanced_inputs)
part2_overlap = sum(1 for q in part2_inputs if q in balanced_inputs)

print(f"Part 1 overlap with 10k: {part1_overlap} (Expected: 0) - {'PASS' if part1_overlap == 0 else 'FAIL'}")
print(f"Part 2 overlap with 10k: {part2_overlap} (Expected: 0) - {'PASS' if part2_overlap == 0 else 'FAIL'}")

# 3. Check overlap between Part 1 and Part 2
p1_set = set(part1_inputs)
p2_set = set(part2_inputs)
inter_count = len(p1_set.intersection(p2_set))
print(f"Overlap between Part 1 and Part 2: {inter_count} (Expected: 0) - {'PASS' if inter_count == 0 else 'FAIL'}")

# 4. Check special cases
def check_special_cases(name, data):
    print(f"\n--- Special cases check for {name} ---")
    
    # Check for Weekend Casual & Athleisure comparison
    cross_count = sum(1 for item in data if any(k in item['messages'][0]['content'].lower() for k in ["weekend casual", "athleisure"]))
    print(f"  Cross-reasoning (Weekend Casual/Athleisure): {cross_count} questions found")
    
    # Check for jeans work conflict
    conflict_count = sum(1 for item in data if "jean" in item['messages'][0]['content'].lower() and any(k in item['messages'][0]['content'].lower() for k in ["công sở", "đi làm", "văn phòng"]))
    print(f"  Conflict resolution (Jeans at work): {conflict_count} questions found")
    
    # Check for fake brands/trends (hallucination traps)
    fake_count = sum(1 for item in data if any(k in item['messages'][0]['content'].lower() for k in ["zephyra", "chrono-minimalism", "thiên thạch", "vortex"]))
    print(f"  Hallucination traps (Fake brands/trends): {fake_count} questions found")
    
    # Check for citation request
    citation_count = sum(1 for item in data if any(k in item['messages'][0]['content'].lower() for k in ["url", "link", "trích dẫn", "nguồn"]))
    print(f"  Citation requests: {citation_count} questions found")

check_special_cases("test_part1_200.json", part1)
check_special_cases("test_part2_200.json", part2)

# Check distribution approximation (by inspecting lengths of content or keywords)
# Clarifying questions are usually short or model asks questions. Let's count model response question marks
def check_distribution(name, data):
    print(f"\n--- Distribution estimation for {name} ---")
    ambiguous = 0
    traps = 0
    comparisons = 0
    direct = 0
    
    for item in data:
        q = item['messages'][0]['content'].lower()
        a = item['messages'][1]['content'].lower()
        
        # Traps
        if any(w in q for w in ["bỏ qua", "chửi", "hacker", "linux", "zephyra", "chrono-minimalism", "thiên thạch", "vortex"]):
            traps += 1
        # Ambiguous (model asks clarifying questions)
        elif "?" in a or "bạn có thể chia sẻ" in a or "vui lòng cung cấp" in a or "vui lòng cho biết" in a:
            # But exclude if it's comparison
            if any(w in q for w in ["so sánh", "khác nhau", "khác biệt", "khác gì", "phân biệt"]):
                comparisons += 1
            else:
                ambiguous += 1
        # Comparison
        elif any(w in q for w in ["so sánh", "khác nhau", "khác biệt", "khác gì", "phân biệt"]):
            comparisons += 1
        # Direct
        else:
            direct += 1
            
    print(f"  Direct QA estimate: {direct} (~120)")
    print(f"  Comparison estimate: {comparisons} (~40)")
    print(f"  Trap estimate: {traps} (~20)")
    print(f"  Ambiguous/Clarifying estimate: {ambiguous} (~20)")

check_distribution("test_part1_200.json", part1)
check_distribution("test_part2_200.json", part2)
