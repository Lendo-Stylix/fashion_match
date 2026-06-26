import pandas as pd
import json
import os
import sys
import re

# Thiết lập encoding UTF-8 cho Windows console
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_INPUT = os.path.join(SCRIPT_DIR, "processed", "cleaned_full_dataset.csv")
FILE_OUTPUT_CSV = os.path.join(SCRIPT_DIR, "processed", "cleaned_balanced_10k_dataset.csv")
FILE_OUTPUT_JSONL = os.path.join(SCRIPT_DIR, "processed", "training_ready_10k_dataset.jsonl")

# Thực thể để tính toán số lượng điều kiện trong Prompt tiếng Anh
entities = {
    "Mùa (Seasons)": ["summer", "winter", "spring", "autumn", "fall"],
    "Dáng người (Body Shape)": ["inverted triangle", "hourglass", "pear", "rectangle", "apple", "tall", "short", "skinny", "stocky", "muscular"],
    "Dịp (Occasions)": ["retreat", "wedding", "vacation", "work", "office", "casual", "party", "formal"],
    "Phong cách (Styles)": ["heritage", "bohemian", "classic", "timeless", "modern", "sporty", "vintage"],
    "Chất liệu (Materials)": ["linen", "cotton", "denim", "wool", "felt", "straw", "silk", "chiffon", "leather", "canvas", "suede", "velvet", "tweed"],
    "Ngân sách (Budget)": ["budget", "affordable", "luxury"],
    "Danh mục (Categories)": ["shirt", "pants", "suit", "skirt", "dress", "shoe", "boot", "hat", "accessory", "blouse", "jeans", "blazer", "jacket"]
}

# Các bộ từ khóa phân loại chủ đề (dựa trên tiếng Anh gốc với ranh giới từ \b để đảm bảo chính xác)
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
    # Ưu tiên câu trả lời chi tiết và giải thích sâu sắc (từ 80 đến 300 từ)
    if vi_out_wc >= 80 and vi_out_wc <= 300:
        richness_score = 1.0
    elif vi_out_wc < 80:
        richness_score = vi_out_wc / 80.0  # Giảm tuyến tính nếu quá ngắn
    else:
        richness_score = max(0.5, 1.0 - (vi_out_wc - 300) / 400.0) # Giảm nhẹ nếu quá dài
        
    # 2. Điểm số lượng ràng buộc trong Prompt (Input Constraints)
    # Đếm số nhóm thực thể xuất hiện trong Prompt tiếng Anh
    input_entities = 0
    en_in_lower = en_in.lower()
    for cat, terms in entities.items():
        for term in terms:
            if re.search(r'\b' + re.escape(term) + r'\b', en_in_lower):
                input_entities += 1
                break  # Chỉ đếm mỗi nhóm thực thể tối đa 1 lần
                
    # Chuẩn hóa theo mức tối đa thực tế là 3 điều kiện
    input_score = min(input_entities / 3.0, 1.0)
    
    # 3. Điểm căn chỉnh tỷ lệ từ (Ratio Alignment)
    # Càng sát tỷ lệ lý tưởng 1.15 càng tốt
    en_in_wc = max(len(en_in.split()), 1)
    en_out_wc = max(len(en_out.split()), 1)
    in_ratio = vi_in_wc / en_in_wc
    out_ratio = vi_out_wc / en_out_wc
    ratio_diff = (abs(in_ratio - 1.15) + abs(out_ratio - 1.15)) / 2.0
    ratio_score = 1.0 - min(ratio_diff, 1.0)
    
    # Điểm tổng hợp: Đầu ra chi tiết (50%), Ràng buộc phong phú (30%), Tỷ lệ dịch chuẩn (20%)
    total_score = richness_score * 0.5 + input_score * 0.3 + ratio_score * 0.2
    return total_score

def classify_row_en(row):
    """Phân loại một dòng vào chủ đề dựa trên mức độ ưu tiên từ khóa tiếng Anh gốc"""
    text = (str(row['original_input']) + " " + str(row['original_output'])).lower()
    for cat, terms in categories_english.items():
        for term in terms:
            if re.search(r'\b' + re.escape(term) + r'\b', text):
                return cat
    return "Chung (General)"

def main():
    print("="*60)
    print("🚀 Bắt đầu quy trình chắt lọc bộ dữ liệu 10k dòng phân tầng (Stratified)...")
    print("="*60)
    
    if not os.path.exists(FILE_INPUT):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu sạch tại {FILE_INPUT}")
        print("Hãy chạy clean_dataset.py hoặc visualize_processed.ipynb trước.")
        sys.exit(1)
        
    df = pd.read_csv(FILE_INPUT)
    initial_rows = len(df)
    print(f"📦 Đã tải dữ liệu sạch: {initial_rows:,} dòng.")
    
    # 1. Tính toán điểm chắt lọc cho từng dòng
    print("⏳ Đang phân tích độ phức tạp và chấm điểm chất lượng từng dòng...")
    df['pruning_score'] = df.apply(calculate_pruning_score, axis=1)
    
    # Phân loại chủ đề cho từng dòng
    print("⏳ Đang phân loại chủ đề dữ liệu dựa trên từ khóa...")
    df['category'] = df.apply(classify_row_en, axis=1)
    
    # 2. Thực hiện lấy mẫu phân tầng với hạn ngạch (quota) cố định
    print("⏳ Đang thực hiện chọn lọc phân tầng theo hạn ngạch chủ đề...")
    
    # Định nghĩa chỉ tiêu phân bổ cho 10k dòng
    targets = {
        "Dáng người (Body Shape)": 2000,
        "Phong cách (Styles)": 2000,
        "Mùa & Thời tiết (Weather & Seasons)": 1500,
        "Ngân sách (Budget)": 1000,
        "Chất liệu (Materials)": 800,
        "Dịp (Occasions)": 800,
        "Danh mục (Categories)": 500,
        "Chung (General)": 1400
    }
    
    selected_dfs = []
    residual_pool = []
    total_needed = 10000
    
    # Bước 1: Lấy tối đa theo quota của từng danh mục
    for cat, target in targets.items():
        cat_df = df[df['category'] == cat].sort_values(by='pruning_score', ascending=False)
        available = len(cat_df)
        if available <= target:
            selected_dfs.append(cat_df)
            print(f"🔹 Chủ đề '{cat}': Giữ lại toàn bộ {available:,}/{available:,} dòng (chỉ tiêu {target})")
        else:
            selected_dfs.append(cat_df.head(target))
            residual_pool.append(cat_df.iloc[target:])
            print(f"🔹 Chủ đề '{cat}': Lọc lấy top {target:,}/{available:,} dòng tốt nhất")
            
    df_selected = pd.concat(selected_dfs)
    current_count = len(df_selected)
    
    # Bước 2: Nếu chưa đủ 10k dòng, bù đắp từ các dòng dư thừa tốt nhất của pool chung
    if current_count < total_needed:
        remaining_needed = total_needed - current_count
        print(f"\n⚡ Đang bù đắp {remaining_needed:,} dòng còn thiếu từ danh sách dư thừa có điểm cao nhất...")
        df_residuals = pd.concat(residual_pool).sort_values(by='pruning_score', ascending=False)
        df_selected = pd.concat([df_selected, df_residuals.head(remaining_needed)])
        
    df_10k = df_selected.copy()
    
    # Xóa các cột điểm bổ trợ trước khi lưu CSV
    df_10k_csv = df_10k.drop(columns=['pruning_score', 'category'])
    
    # 3. Lưu file CSV sạch
    df_10k_csv.to_csv(FILE_OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"\n💾 Đã lưu CSV phân tầng tại: {FILE_OUTPUT_CSV}")
    
    # 4. Xuất sang file định dạng JSONL (ChatML cho Gemma 3)
    print("⏳ Đang chuyển đổi định dạng sang JSON Lines (ChatML)...")
    jsonl_records = []
    for idx, row in df_10k.iterrows():
        record = {
            "messages": [
                {"role": "user", "content": str(row['translated_input'])},
                {"role": "model", "content": str(row['translated_output'])}
            ]
        }
        jsonl_records.append(record)
        
    with open(FILE_OUTPUT_JSONL, 'w', encoding='utf-8') as f:
        for rec in jsonl_records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            
    print(f"💾 Đã lưu JSONL phân tầng tại: {FILE_OUTPUT_JSONL}")
    
    # --- Thống kê số liệu tập 10k ---
    print("\n" + "="*60)
    print("📊 THỐNG KÊ CHI TIẾT BỘ DỮ LIỆU PHÂN TẦNG 10K")
    print("="*60)
    avg_in_len = df_10k['translated_input'].apply(lambda x: len(str(x).split())).mean()
    avg_out_len = df_10k['translated_output'].apply(lambda x: len(str(x).split())).mean()
    print(f"🔹 Tổng số dòng được trích xuất:  10,000 dòng")
    print(f"🔹 Độ dài trung bình Prompt (User): {avg_in_len:.1f} từ")
    print(f"🔹 Độ dài trung bình Completion (Model): {avg_out_len:.1f} từ")
    
    print("\n🔹 Phân bổ danh mục trong dataset 10k cuối cùng:")
    final_counts = df_10k['category'].value_counts()
    for cat, count in final_counts.items():
        pct = (count / total_needed) * 100
        print(f"   - {cat}: {count:,} dòng ({pct:.2f}%)")
        
    print("="*60)
    print("🎉 QUY TRÌNH CHẤT LỌC PHÂN TẦNG HOÀN THÀNH XUẤT SẮC!")
    print("Tập dữ liệu 10k hiện tại đã cực kỳ cân bằng ngữ cảnh, sẵn sàng mang đi Train!")
    print("="*60)

if __name__ == "__main__":
    main()
