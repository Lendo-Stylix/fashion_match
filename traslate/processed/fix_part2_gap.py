import json
import os
import random
import pandas as pd

base_dir = r"d:\Learning\ky_5\DPL302m\Project\fashion_match\traslate\processed"

# Load current files
test1_path = os.path.join(base_dir, "test_part1_200.json")
test2_path = os.path.join(base_dir, "test_part2_200.json")

with open(test1_path, 'r', encoding='utf-8') as f:
    part1 = json.load(f)
with open(test2_path, 'r', encoding='utf-8') as f:
    part2 = json.load(f)

# Load datasets to sample from
full_df = pd.read_csv(os.path.join(base_dir, "cleaned_full_dataset.csv"))
balanced_df = pd.read_csv(os.path.join(base_dir, "cleaned_balanced_10k_dataset.csv"))

balanced_inputs = set(balanced_df['translated_input'].dropna().str.strip().str.lower().tolist())

# Deduplicate Part 1 and Part 2 internally and against each other first
seen_in_current = set()
dedup_part1 = []
for item in part1:
    q = item['messages'][0]['content'].strip().lower()
    if q not in seen_in_current:
        seen_in_current.add(q)
        dedup_part1.append(item)

dedup_part2 = []
for item in part2:
    q = item['messages'][0]['content'].strip().lower()
    if q not in seen_in_current:
        seen_in_current.add(q)
        dedup_part2.append(item)

print(f"After deduplication: Part 1 = {len(dedup_part1)} items, Part 2 = {len(dedup_part2)} items.")

# Get all inputs currently used in either part
all_used_inputs = seen_in_current.copy()
# Also add balanced 10k inputs to prevent any overlap
all_used_inputs.update(balanced_inputs)

# Filter pool
filtered_df = full_df[~full_df['translated_input'].dropna().str.strip().str.lower().isin(all_used_inputs)]
print(f"Remaining non-overlapping pool size: {len(filtered_df)}")

def format_direct_qa(pool):
    formatted = []
    for row in pool:
        prompt = row['translated_input'].strip()
        response = row['translated_output'].strip()
        formatted.append({
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "model", "content": response}
            ]
        })
    return formatted

# Fill Part 1 if short
if len(dedup_part1) < 200:
    needed = 200 - len(dedup_part1)
    print(f"Adding {needed} items to Part 1...")
    fill_rows = filtered_df.sample(needed, random_state=42).to_dict('records')
    dedup_part1.extend(format_direct_qa(fill_rows))
    # Update used
    for r in fill_rows:
        all_used_inputs.add(r['translated_input'].strip().lower())
    # Refilter
    filtered_df = full_df[~full_df['translated_input'].dropna().str.strip().str.lower().isin(all_used_inputs)]

# Fill Part 2 if short
if len(dedup_part2) < 200:
    needed = 200 - len(dedup_part2)
    print(f"Adding {needed} items to Part 2...")
    fill_rows = filtered_df.sample(needed, random_state=100).to_dict('records')
    dedup_part2.extend(format_direct_qa(fill_rows))

# Shuffle and Save
random.seed(42)
random.shuffle(dedup_part1)
random.shuffle(dedup_part2)

with open(test1_path, 'w', encoding='utf-8') as f:
    json.dump(dedup_part1, f, ensure_ascii=False, indent=2)

with open(test2_path, 'w', encoding='utf-8') as f:
    json.dump(dedup_part2, f, ensure_ascii=False, indent=2)

print("Verification check:")
print(f"  Part 1 final length: {len(dedup_part1)}")
print(f"  Part 2 final length: {len(dedup_part2)}")
print(f"  Overlap count: {len(set([i['messages'][0]['content'].strip().lower() for i in dedup_part1]).intersection(set([i['messages'][0]['content'].strip().lower() for i in dedup_part2])))}")
