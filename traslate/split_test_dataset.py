import pandas as pd
import json
import os
import sys
import re

# Thiết lập encoding UTF-8 cho Windows console
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_INPUT = os.path.join(SCRIPT_DIR, "processed", "cleaned_balanced_10k_dataset.csv")

FILE_TRAIN_CSV = os.path.join(SCRIPT_DIR, "processed", "cleaned_balanced_9.5k_dataset.csv")
FILE_TRAIN_JSONL = os.path.join(SCRIPT_DIR, "processed", "training_ready_9.5k_dataset.jsonl")

FILE_TEST_CSV = os.path.join(SCRIPT_DIR, "processed", "test_balanced_500_dataset.csv")
FILE_TEST_JSONL = os.path.join(SCRIPT_DIR, "processed", "test_ready_500_dataset.jsonl")

# Các bộ từ khóa phân loại chủ đề (đồng bộ với prune_dataset.py)
categories_english = {
    "Dáng người (Body Shape)": ["inverted triangle", "hourglass", "pear", "rectangle", "apple", "tall", "short", "skinny", "stocky", "muscular"],
    "Mùa & Thời tiết (Weather & Seasons)": ["summer", "winter", "spring", "autumn", "fall", "weather", "hot", "cold", "warm", "cool", "temperature", "rain", "rainy", "sunny", "windy"],
    "Dịp (Occasions)": ["retreat", "wedding", "vacation", "work", "office", "casual", "party", "formal", "interview", "date", "travel", "holiday"],
    "Phong cách (Styles)": ["heritage", "bohemian", "classic", "timeless", "modern", "sporty", "vintage", "chic", "streetwear", "minimalist", "preppy", "retro"],
    "Chất liệu (Materials)": ["linen", "cotton", "denim", "wool", "felt", "straw", "silk", "chiffon", "leather", "canvas", "suede", "velvet", "tweed", "polyester", "satin", "lace"],
    "Ngân sách (Budget)": ["budget", "affordable", "luxury", "expensive", "cheap", "price", "cost"],
    "Danh mục (Categories)": ["shirt", "pants", "suit", "skirt", "dress", "shoe", "boot", "hat", "accessory", "blouse", "jeans", "blazer", "jacket", "t-shirt", "coat", "sneakers", "bag"]
}

def classify_row_en(row):
    """Phân loại một dòng vào chủ đề dựa trên mức độ ưu tiên từ khóa tiếng Anh gốc"""
    text = (str(row['original_input']) + " " + str(row['original_output'])).lower()
    for cat, terms in categories_english.items():
        for term in terms:
            if re.search(r'\b' + re.escape(term) + r'\b', text):
                return cat
    return "Chung (General)"

def save_to_jsonl(df, output_path):
    """Lưu dataframe sang định dạng JSONL (ChatML cho Gemma 3)"""
    jsonl_records = []
    for idx, row in df.iterrows():
        record = {
            "messages": [
                {"role": "user", "content": str(row['translated_input'])},
                {"role": "model", "content": str(row['translated_output'])}
            ]
        }
        jsonl_records.append(record)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        for rec in jsonl_records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def main():
    print("="*60)
    print("🚀 Bắt đầu phân tách tập dữ liệu Train (9.5k) và Test (500) phân tầng...")
    print("="*60)
    
    if not os.path.exists(FILE_INPUT):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu 10k tại {FILE_INPUT}")
        sys.exit(1)
        
    df = pd.read_csv(FILE_INPUT)
    print(f"📦 Đã tải dữ liệu 10k: {len(df):,} dòng.")
    
    # 1. Phân loại lại danh mục cho các dòng để phân tách phân tầng chính xác
    print("⏳ Đang phân loại chủ đề dữ liệu...")
    df['category'] = df.apply(classify_row_en, axis=1)
    
    # 2. Tính toán số lượng mẫu test cần lấy cho mỗi danh mục sao cho tổng bằng 500
    print("⏳ Đang tính toán tỷ lệ lấy mẫu phân tầng...")
    category_counts = df['category'].value_counts()
    total_rows = len(df)
    target_test_total = 500
    
    # Tính số dòng test thô theo tỷ lệ 5%
    test_allocations = {}
    for cat, count in category_counts.items():
        test_allocations[cat] = int(round(count * (target_test_total / total_rows)))
        
    # Điều chỉnh để đảm bảo tổng số lượng test bằng đúng 500
    current_sum = sum(test_allocations.values())
    diff = target_test_total - current_sum
    
    if diff != 0:
        print(f"⚠️ Tổng số lượng mẫu thô là {current_sum}. Điều chỉnh {diff:+d} dòng...")
        # Cộng/trừ chênh lệch vào các nhóm lớn nhất
        sorted_cats = sorted(test_allocations.keys(), key=lambda k: category_counts[k], reverse=True)
        for i in range(abs(diff)):
            cat = sorted_cats[i % len(sorted_cats)]
            if diff > 0:
                test_allocations[cat] += 1
            else:
                test_allocations[cat] -= 1
                
    print(f"📋 Chỉ tiêu phân bổ tập Test (Tổng {sum(test_allocations.values())} dòng):")
    for cat, alloc in test_allocations.items():
        total_cat = category_counts[cat]
        print(f"   - {cat}: Lấy {alloc} dòng từ tổng số {total_cat} dòng ({alloc/total_cat*100:.2f}%)")
        
    # 3. Tiến hành lấy mẫu ngẫu nhiên (random_state=42 để đảm bảo tính tái lập)
    test_dfs = []
    for cat, alloc in test_allocations.items():
        cat_df = df[df['category'] == cat]
        test_sample = cat_df.sample(n=alloc, random_state=42)
        test_dfs.append(test_sample)
        
    df_test = pd.concat(test_dfs).sample(frac=1, random_state=42) # Shuffle tập test
    df_train = df.drop(df_test.index).sample(frac=1, random_state=42) # Shuffle tập train
    
    print(f"\n📊 Kích thước phân tách thành công:")
    print(f"   - Tập Train: {len(df_train):,} dòng")
    print(f"   - Tập Test:  {len(df_test):,} dòng")
    
    # Xóa cột bổ trợ 'category' trước khi lưu
    df_train_save = df_train.drop(columns=['category'])
    df_test_save = df_test.drop(columns=['category'])
    
    # 4. Lưu kết quả ra file
    print("\n💾 Đang lưu các tập dữ liệu...")
    
    # Lưu CSV
    df_train_save.to_csv(FILE_TRAIN_CSV, index=False, encoding='utf-8')
    df_test_save.to_csv(FILE_TEST_CSV, index=False, encoding='utf-8')
    print(f"   - Đã lưu CSV Train tại: {FILE_TRAIN_CSV}")
    print(f"   - Đã lưu CSV Test tại:  {FILE_TEST_CSV}")
    
    # Lưu JSONL
    save_to_jsonl(df_train_save, FILE_TRAIN_JSONL)
    save_to_jsonl(df_test_save, FILE_TEST_JSONL)
    print(f"   - Đã lưu JSONL Train tại: {FILE_TRAIN_JSONL}")
    print(f"   - Đã lưu JSONL Test tại:  {FILE_TEST_JSONL}")
    
    print("\n" + "="*60)
    print("🎉 QUY TRÌNH PHÂN TÁCH TẬP TRAIN/TEST HOÀN THÀNH XUẤT SẮC!")
    print("="*60)

if __name__ == "__main__":
    main()
