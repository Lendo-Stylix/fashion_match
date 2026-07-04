import pandas as pd
import json
import os
import sys
import re

# Thiết lập encoding UTF-8 cho Windows console
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_FULL = os.path.join(SCRIPT_DIR, "processed", "cleaned_full_dataset.csv")
FILE_10K = os.path.join(SCRIPT_DIR, "processed", "cleaned_balanced_10k_dataset.csv")
FILE_OUTPUT_JSON = os.path.join(SCRIPT_DIR, "processed", "test_next_500_dataset.json")

# Thực thể để tính toán số lượng điều kiện trong Prompt (giống prune_dataset.py)
entities = {
    "Mùa (Seasons)": ["summer", "winter", "spring", "autumn", "fall"],
    "Dáng người (Body Shape)": ["inverted triangle", "hourglass", "pear", "rectangle", "apple", "tall", "short", "skinny", "stocky", "muscular"],
    "Dịp (Occasions)": ["retreat", "wedding", "vacation", "work", "office", "casual", "party", "formal"],
    "Phong cách (Styles)": ["heritage", "bohemian", "classic", "timeless", "modern", "sporty", "vintage"],
    "Chất liệu (Materials)": ["linen", "cotton", "denim", "wool", "felt", "straw", "silk", "chiffon", "leather", "canvas", "suede", "velvet", "tweed"],
    "Ngân sách (Budget)": ["budget", "affordable", "luxury"],
    "Danh mục (Categories)": ["shirt", "pants", "suit", "skirt", "dress", "shoe", "boot", "hat", "accessory", "blouse", "jeans", "blazer", "jacket"]
}

# Các bộ từ khóa phân loại chủ đề
categories_english = {
    "Dáng người (Body Shape)": ["inverted triangle", "hourglass", "pear", "rectangle", "apple", "tall", "short", "skinny", "stocky", "muscular"],
    "Mùa & Thời tiết (Weather & Seasons)": ["summer", "winter", "spring", "autumn", "fall", "weather", "hot", "cold", "warm", "cool", "temperature", "rain", "rainy", "sunny", "windy"],
    "Dịp (Occasions)": ["retreat", "wedding", "vacation", "work", "office", "casual", "party", "formal", "interview", "date", "travel", "holiday"],
    "Phong cách (Styles)": ["heritage", "bohemian", "classic", "timeless", "modern", "sporty", "vintage", "chic", "streetwear", "minimalist", "preppy", "retro"],
    "Chất liệu (Materials)": ["linen", "cotton", "denim", "wool", "felt", "straw", "silk", "chiffon", "leather", "canvas", "suede", "velvet", "tweed", "polyester", "satin", "lace"],
    "Ngân sách (Budget)": ["budget", "affordable", "luxury", "expensive", "cheap", "price", "cost"],
    "Danh mục (Categories)": ["shirt", "pants", "suit", "skirt", "dress", "shoe", "boot", "hat", "accessory", "blouse", "jeans", "blazer", "jacket", "t-shirt", "coat", "sneakers", "bag"]
}

def calculate_pruning_score(row):
    en_in = str(row['original_input'])
    en_out = str(row['original_output'])
    vi_in = str(row['translated_input'])
    vi_out = str(row['translated_output'])
    
    vi_in_wc = len(vi_in.split())
    vi_out_wc = len(vi_out.split())
    
    # 1. Điểm phong phú của đầu ra (Output Richness)
    if vi_out_wc >= 80 and vi_out_wc <= 300:
        richness_score = 1.0
    elif vi_out_wc < 80:
        richness_score = vi_out_wc / 80.0
    else:
        richness_score = max(0.5, 1.0 - (vi_out_wc - 300) / 400.0)
        
    # 2. Điểm số lượng ràng buộc trong Prompt (Input Constraints)
    input_entities = 0
    en_in_lower = en_in.lower()
    for cat, terms in entities.items():
        for term in terms:
            if re.search(r'\b' + re.escape(term) + r'\b', en_in_lower):
                input_entities += 1
                break
                
    input_score = min(input_entities / 3.0, 1.0)
    
    # 3. Điểm căn chỉnh tỷ lệ từ (Ratio Alignment)
    en_in_wc = max(len(en_in.split()), 1)
    en_out_wc = max(len(en_out.split()), 1)
    in_ratio = vi_in_wc / en_in_wc
    out_ratio = vi_out_wc / en_out_wc
    ratio_diff = (abs(in_ratio - 1.15) + abs(out_ratio - 1.15)) / 2.0
    ratio_score = 1.0 - min(ratio_diff, 1.0)
    
    total_score = richness_score * 0.5 + input_score * 0.3 + ratio_score * 0.2
    return total_score

def classify_row_en(row):
    text = (str(row['original_input']) + " " + str(row['original_output'])).lower()
    for cat, terms in categories_english.items():
        for term in terms:
            if re.search(r'\b' + re.escape(term) + r'\b', text):
                return cat
    return "Chung (General)"

def main():
    print("="*60)
    print("🚀 Bắt đầu quy trình trích xuất 500 dòng test phân tầng tiếp theo...")
    print("="*60)
    
    # Kiểm tra các file đầu vào
    if not os.path.exists(FILE_FULL):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu sạch đầy đủ tại {FILE_FULL}")
        sys.exit(1)
    if not os.path.exists(FILE_10K):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu train 10k tại {FILE_10K}")
        sys.exit(1)
        
    df_full = pd.read_csv(FILE_FULL)
    df_10k = pd.read_csv(FILE_10K)
    
    print(f"📦 Đã tải tập dữ liệu sạch đầy đủ: {len(df_full):,} dòng.")
    print(f"📦 Đã tải tập dữ liệu train 10k:     {len(df_10k):,} dòng.")
    
    # 1. Loại bỏ các dòng đã có trong tập train 10k để tránh trùng lặp (tránh Data Leakage)
    print("⏳ Đang thực hiện loại trừ các dòng đã dùng cho tập train...")
    merged = df_full.merge(
        df_10k[['original_input', 'original_output', 'translated_input', 'translated_output']], 
        on=['original_input', 'original_output', 'translated_input', 'translated_output'], 
        how='left', 
        indicator=True
    )
    df_remaining = merged[merged['_merge'] == 'left_only'].drop(columns=['_merge'])
    print(f"🔹 Số lượng dòng còn lại sau khi loại trừ: {len(df_remaining):,} dòng.")
    
    # 2. Tính toán điểm chắt lọc cho tập còn lại
    print("⏳ Đang tính toán điểm chất lượng pruning_score cho các dòng còn lại...")
    df_remaining['pruning_score'] = df_remaining.apply(calculate_pruning_score, axis=1)
    
    # Phân loại danh mục
    print("⏳ Đang phân loại chủ đề dữ liệu còn lại...")
    df_remaining['category'] = df_remaining.apply(classify_row_en, axis=1)
    
    # 3. Lấy mẫu phân tầng từ tập còn lại để đảm bảo tính đa dạng (tránh lệch 100% về một chủ đề)
    # Vì Dáng người và Ngân sách đã cạn kiệt (0 dòng còn lại), ta tập trung phân bổ vào 6 nhóm còn lại
    print("⏳ Đang phân tách phân tầng theo hạn ngạch cho tập Test 500 dòng...")
    test_targets = {
        "Phong cách (Styles)": 100,
        "Dịp (Occasions)": 100,
        "Mùa & Thời tiết (Weather & Seasons)": 100,
        "Chất liệu (Materials)": 100,
        "Danh mục (Categories)": 80,
        "Chung (General)": 20
    }
    
    selected_test_dfs = []
    for cat, target in test_targets.items():
        cat_df = df_remaining[df_remaining['category'] == cat].sort_values(by='pruning_score', ascending=False)
        available = len(cat_df)
        take_count = min(available, target)
        selected_test_dfs.append(cat_df.head(take_count))
        print(f"   - Lọc lấy top {take_count}/{available} dòng thuộc chủ đề: {cat}")
        
    df_test = pd.concat(selected_test_dfs).sample(frac=1, random_state=42) # Shuffle tập test
    
    # 4. Định dạng sang JSON ChatML
    print("\n⏳ Đang định dạng sang cấu trúc hội thoại JSON...")
    test_records = []
    for idx, row in df_test.iterrows():
        record = {
            "messages": [
                {"role": "user", "content": str(row['translated_input'])},
                {"role": "model", "content": str(row['translated_output'])}
            ]
        }
        test_records.append(record)
        
    # Tạo thư mục nếu chưa tồn tại
    os.makedirs(os.path.dirname(FILE_OUTPUT_JSON), exist_ok=True)
    
    # Lưu ra file JSON chuẩn (dạng list các object)
    with open(FILE_OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(test_records, f, ensure_ascii=False, indent=2)
        
    print(f"💾 Đã lưu file test JSON tại: {FILE_OUTPUT_JSON}")
    
    # --- Thống kê số liệu tập test 500 ---
    print("\n" + "="*60)
    print("📊 THỐNG KÊ CHI TIẾT TẬP TEST 500 DÒNG TIẾP THEO")
    print("="*60)
    avg_in_len = df_test['translated_input'].apply(lambda x: len(str(x).split())).mean()
    avg_out_len = df_test['translated_output'].apply(lambda x: len(str(x).split())).mean()
    avg_score = df_test['pruning_score'].mean()
    
    print(f"🔹 Số lượng dòng test: {len(df_test):,} dòng")
    print(f"🔹 Điểm chất lượng trung bình (pruning_score): {avg_score:.4f}")
    print(f"🔹 Độ dài trung bình Prompt (User): {avg_in_len:.1f} từ")
    print(f"🔹 Độ dài trung bình Completion (Model): {avg_out_len:.1f} từ")
    
    # Kiểm tra trùng lặp lần cuối để đảm bảo an toàn tuyệt đối
    double_check_merge = df_test.merge(
        df_10k[['original_input', 'original_output', 'translated_input', 'translated_output']], 
        on=['original_input', 'original_output', 'translated_input', 'translated_output'], 
        how='inner'
    )
    print(f"🔹 Số lượng trùng lặp với tập train 10k: {len(double_check_merge)} dòng (Yêu cầu = 0)")
    
    print("\n🔹 Phân bổ danh mục trong tập test 500 dòng mới:")
    final_counts = df_test['category'].value_counts()
    for cat, count in final_counts.items():
        pct = (count / len(df_test)) * 100
        print(f"   - {cat}: {count} dòng ({pct:.2f}%)")
        
    print("="*60)
    print("🎉 QUY TRÌNH TRÍCH XUẤT TẬP TEST HOÀN THÀNH XUẤT SẮC!")
    print("="*60)

if __name__ == "__main__":
    main()
