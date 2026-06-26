import pandas as pd
import numpy as np
import re
import os
import sys
import unicodedata
from langdetect import detect

# Thiết lập encoding UTF-8 cho stdout để tránh lỗi in kí tự đặc biệt trên Windows
sys.stdout.reconfigure(encoding='utf-8')

# Đường dẫn tương đối
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_INPUT = os.path.join(SCRIPT_DIR, "raw", "raw_unfiltered_dataset.csv")
FILE_OUTPUT = os.path.join(SCRIPT_DIR, "processed", "cleaned_full_dataset.csv")


# Định nghĩa các thực thể thời trang phục vụ cho việc đối chiếu
entities = {
    "Mùa (Seasons)": {
        "summer": ["mùa hè", "hè", "summer"],
        "winter": ["mùa đông", "đông", "winter"],
        "spring": ["mùa xuân", "xuân", "spring"],
        "autumn": ["mùa thu", "thu", "autumn"],
        "fall": ["mùa thu", "thu", "fall"]
    },
    "Dáng người (Body Shape)": {
        "inverted triangle": ["tam giác ngược", "inverted triangle"],
        "hourglass": ["đồng hồ cát", "hourglass"],
        "pear": ["quả lê", "dáng lê", "pear"],
        "rectangle": ["hình chữ nhật", "dáng suông", "rectangle"],
        "apple": ["quả táo", "apple"],
        "tall": ["cao", "tall"],
        "short": ["thấp", "nấm lùn", "short"],
        "skinny": ["gầy", "ốm", "skinny"],
        "stocky": ["đậm người", "mập mạp", "đô con", "stocky"],
        "muscular": ["cơ bắp", "muscular"]
    },
    "Dịp (Occasions)": {
        "retreat": ["dã ngoại", "nghỉ dưỡng", "retreat"],
        "wedding": ["tiệc cưới", "đám cưới", "wedding"],
        "vacation": ["kỳ nghỉ", "vacation", "du lịch"],
        "work": ["văn phòng", "công sở", "đi làm", "work"],
        "office": ["văn phòng", "công sở", "office"],
        "casual": ["thường ngày", "hàng ngày", "casual"],
        "party": ["tiệc", "party"],
        "formal": ["trang trọng", "lịch sự", "formal"]
    },
    "Phong cách (Styles)": {
        "heritage": ["di sản", "heritage", "rugged heritage"],
        "bohemian": ["bohemian", "boho"],
        "classic": ["cổ điển", "classic"],
        "timeless": ["kinh điển", "trường tồn", "vĩnh cửu", "timeless", "thời thượng"],
        "modern": ["hiện đại", "modern"],
        "sporty": ["thể thao", "sporty"],
        "vintage": ["vintage", "cổ xưa"]
    },
    "Chất liệu (Materials)": {
        "linen": ["linen", "lanh"],
        "cotton": ["cotton", "bông"],
        "denim": ["denim", "bò"],
        "wool": ["len", "wool"],
        "felt": ["nỉ", "dạ", "felt"],
        "straw": ["cói", "rơm", "straw"],
        "silk": ["lụa", "tơ tằm", "silk"],
        "chiffon": ["voan", "chiffon"],
        "leather": ["da", "leather"],
        "canvas": ["bạt", "canvas"],
        "suede": ["da lộn", "suede"],
        "velvet": ["nhung", "velvet"],
        "tweed": ["tweed", "dạ tweed"]
    },
    "Ngân sách (Budget)": {
        "budget": ["ngân sách", "tiết kiệm", "giá rẻ", "budget"],
        "affordable": ["phải chăng", "hợp lý", "affordable"],
        "luxury": ["sang trọng", "xa xỉ", "luxury"]
    },
    "Danh mục (Categories)": {
        "shirt": ["áo", "sơ mi", "áo thun", "shirt"],
        "pants": ["quần", "pants"],
        "suit": ["suit", "vest", "bộ âu phục"],
        "skirt": ["váy", "chân váy", "skirt"],
        "dress": ["đầm", "váy", "dress"],
        "shoe": ["giày", "shoe", "shoes"],
        "boot": ["boot", "bốt", "boots"],
        "hat": ["mũ", "nón", "hat"],
        "accessory": ["phụ kiện", "trang sức", "accessory", "accessories"],
        "blouse": ["blouse", "áo blouse"],
        "jeans": ["jeans", "quần jeans"],
        "blazer": ["blazer", "áo khoác"],
        "jacket": ["áo khoác", "jacket"]
    }
}

# Regex pre-compiled để tối ưu tốc độ
re_html = re.compile(r'<[^>]*>')
re_url = re.compile(r'https?://\S+|www\.\S+')
re_email = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
re_spaces = re.compile(r'\s+')
re_numbers = re.compile(r'\b\d+\b')
re_vi_chars = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', re.IGNORECASE)

def clean_and_normalize_text(text):
    if not isinstance(text, str):
        return ""
    # NFC Unicode Normalization
    text = unicodedata.normalize('NFC', text)
    # Loại bỏ HTML tags
    text = re_html.sub(' ', text)
    # Loại bỏ URLs
    text = re_url.sub(' ', text)
    # Loại bỏ Email
    text = re_email.sub(' ', text)
    # Gộp khoảng trắng thừa
    text = re_spaces.sub(' ', text).strip()
    return text

def score_translation(row):
    """Tính điểm chất lượng bản dịch để phục vụ cho Deduplication"""
    en_in = str(row['original_input'])
    en_out = str(row['original_output'])
    vi_in = str(row['translated_input'])
    vi_out = str(row['translated_output'])
    
    en_in_wc = max(len(en_in.split()), 1)
    en_out_wc = max(len(en_out.split()), 1)
    vi_in_wc = len(vi_in.split())
    vi_out_wc = len(vi_out.split())
    
    # 1. Điểm Tỷ lệ độ dài từ (tối ưu nằm trong khoảng 1.1 đến 1.3)
    in_ratio = vi_in_wc / en_in_wc
    out_ratio = vi_out_wc / en_out_wc
    
    in_ratio_score = 1.0 - min(abs(in_ratio - 1.15), 1.0)
    out_ratio_score = 1.0 - min(abs(out_ratio - 1.15), 1.0)
    ratio_score = (in_ratio_score + out_ratio_score) / 2.0
    
    # 2. Điểm Bảo toàn thực thể thời trang
    entity_matches = 0
    entity_detections = 0
    for cat, terms in entities.items():
        for en_term, vi_terms in terms.items():
            if re.search(r'\b' + re.escape(en_term) + r'\b', (en_in + " " + en_out).lower()):
                entity_detections += 1
                if any(vi_term in (vi_in + " " + vi_out).lower() for vi_term in vi_terms):
                    entity_matches += 1
                    
    entity_score = (entity_matches / entity_detections) if entity_detections > 0 else 1.0
    
    # 3. Điểm phạt nếu thiếu số quan trọng
    en_numbers = set(re_numbers.findall(en_in + " " + en_out))
    vi_numbers = set(re_numbers.findall(vi_in + " " + vi_out))
    # Chỉ xét những con số có ý nghĩa (>=2 ký tự, tránh số 1, 2, 3...)
    key_en_numbers = {num for num in en_numbers if len(num) >= 2}
    key_vi_numbers = {num for num in vi_numbers if len(num) >= 2}
    
    number_score = 1.0
    if key_en_numbers:
        num_preserved = len(key_en_numbers.intersection(key_vi_numbers))
        number_score = num_preserved / len(key_en_numbers)
        
    # Tính điểm tổng hợp (Số lượng: 40%, Thực thể: 30%, Tỷ lệ độ dài: 30%)
    total_score = ratio_score * 0.3 + entity_score * 0.3 + number_score * 0.4
    return total_score

def check_language(row):
    """Kiểm tra nhận diện ngôn ngữ sử dụng langdetect"""
    en_text = str(row['original_input']) + " " + str(row['original_output'])
    vi_text = str(row['translated_input']) + " " + str(row['translated_output'])
    
    # Check English
    if len(en_text.strip()) > 15:
        try:
            detected = detect(en_text)
            # Chấp nhận một số mã phát hiện lỗi phổ biến cho text ngắn
            if detected != 'en' and detected not in ['en', 'ca', 'ro', 'it', 'fr']:
                return False
        except Exception:
            pass
            
    # Check Vietnamese
    if len(vi_text.strip()) > 15:
        try:
            detected = detect(vi_text)
            has_vi_chars = bool(re_vi_chars.search(vi_text))
            # Nếu langdetect không nhận ra tiếng Việt nhưng câu chứa kí tự tiếng Việt đặc trưng -> Vẫn hợp lệ
            if detected != 'vi' and not has_vi_chars:
                return False
        except Exception:
            pass
            
    return True

def main():
    print("="*60)
    print("🚀 Bắt đầu quy trình chuẩn hóa và làm sạch dataset song ngữ thời trang...")
    print("="*60)
    
    if not os.path.exists(FILE_INPUT):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu đầu vào tại {FILE_INPUT}")
        sys.exit(1)
        
    df = pd.read_csv(FILE_INPUT)
    initial_rows = len(df)
    print(f"📦 Đã tải dataset thành công: {initial_rows:,} dòng dữ liệu.")
    
    # --- Bước 1: Xử lý giá trị rỗng (NaN) ---
    print("\n[Bước 1] Loại bỏ các dòng chứa giá trị rỗng (NaN)...")
    cols_to_check = ['original_input', 'original_output', 'translated_input', 'translated_output']
    df_clean = df.dropna(subset=cols_to_check).copy()
    rows_after_nan = len(df_clean)
    dropped_nan = initial_rows - rows_after_nan
    print(f"👉 Loại bỏ {dropped_nan:,} dòng chứa giá trị rỗng. Còn lại {rows_after_nan:,} dòng.")
    
    # --- Bước 2: Chuẩn hóa văn bản cơ bản & Unicode NFC ---
    print("\n[Bước 2] Thực hiện chuẩn hóa Unicode NFC và dọn dẹp văn bản (HTML, URL, khoảng trắng)...")
    for col in cols_to_check:
        df_clean[col] = df_clean[col].apply(clean_and_normalize_text)
        
    # Xử lý các dòng bị làm sạch hoàn toàn thành chuỗi rỗng
    empty_mask = (df_clean['original_input'] == "") | (df_clean['original_output'] == "") | \
                 (df_clean['translated_input'] == "") | (df_clean['translated_output'] == "")
    df_clean = df_clean[~empty_mask].copy()
    rows_after_norm = len(df_clean)
    print(f"👉 Dọn dẹp khoảng trắng & loại chuỗi rỗng hoàn tất. Còn lại {rows_after_norm:,} dòng.")
    
    # --- Bước 3: Lọc các câu chưa dịch (VI == EN) ---
    print("\n[Bước 3] Loại bỏ các bản dịch trùng lặp câu gốc (dịch lỗi chưa dịch)...")
    untrans_mask = (
        (df_clean['original_input'].str.strip() == df_clean['translated_input'].str.strip()) |
        (df_clean['original_output'].str.strip() == df_clean['translated_output'].str.strip())
    )
    df_clean = df_clean[~untrans_mask].copy()
    rows_after_untrans = len(df_clean)
    dropped_untrans = rows_after_norm - rows_after_untrans
    print(f"👉 Loại bỏ {dropped_untrans:,} dòng chưa dịch. Còn lại {rows_after_untrans:,} dòng.")
    
    # --- Bước 4: Xử lý trùng lặp nguồn - khác đích thông minh (Smart Deduplication) ---
    print("\n[Bước 4] Áp dụng logic khử trùng lặp và tính điểm chất lượng bản dịch (Smart Deduplication)...")
    # Tính điểm chất lượng bản dịch cho toàn bộ dataset
    df_clean['translation_quality_score'] = df_clean.apply(score_translation, axis=1)
    
    # Sắp xếp giảm dần theo điểm chất lượng và giữ lại bản dịch có điểm cao nhất cho mỗi cặp English QA
    df_clean = df_clean.sort_values(by='translation_quality_score', ascending=False)
    df_clean = df_clean.drop_duplicates(subset=['original_input', 'original_output'], keep='first').copy()
    df_clean = df_clean.drop(columns=['translation_quality_score'])
    rows_after_dedup = len(df_clean)
    dropped_dedup = rows_after_untrans - rows_after_dedup
    print(f"👉 Khử trùng lặp thông minh hoàn tất (Đã loại bỏ {dropped_dedup:,} dòng trùng lặp). Còn lại {rows_after_dedup:,} dòng.")
    
    # --- Bước 5: Nhận diện ngôn ngữ (Language Identification) ---
    print("\n[Bước 5] Kiểm tra phân loại nhận diện ngôn ngữ sử dụng langdetect...")
    lang_mask = df_clean.apply(check_language, axis=1)
    df_clean = df_clean[lang_mask].copy()
    rows_after_lang = len(df_clean)
    dropped_lang = rows_after_dedup - rows_after_lang
    print(f"👉 Loại bỏ {dropped_lang:,} dòng lỗi ngôn ngữ/dịch sai tiếng. Còn lại {rows_after_lang:,} dòng.")
    
    # --- Bước 6: Lọc theo độ dài và tỷ lệ (Length & Ratio) ---
    print("\n[Bước 6] Áp dụng lọc độ dài tối đa/tối thiểu và tỷ lệ số từ (Length & Ratio Filtering)...")
    # Tính toán lại số từ và tỷ lệ phục vụ lọc
    epsilon = 1e-5
    df_clean['en_in_wc'] = df_clean['original_input'].apply(lambda x: len(x.split()))
    df_clean['en_out_wc'] = df_clean['original_output'].apply(lambda x: len(x.split()))
    df_clean['vi_in_wc'] = df_clean['translated_input'].apply(lambda x: len(x.split()))
    df_clean['vi_out_wc'] = df_clean['translated_output'].apply(lambda x: len(x.split()))
    
    df_clean['in_ratio'] = df_clean['vi_in_wc'] / (df_clean['en_in_wc'] + epsilon)
    df_clean['out_ratio'] = df_clean['vi_out_wc'] / (df_clean['en_out_wc'] + epsilon)
    
    # Thiết lập bộ lọc
    valid_length_mask = (
        # Tỷ lệ từ lý tưởng
        (df_clean['in_ratio'] >= 0.4) & (df_clean['in_ratio'] <= 2.5) &
        (df_clean['out_ratio'] >= 0.4) & (df_clean['out_ratio'] <= 2.5) &
        # Độ dài tối thiểu
        (df_clean['vi_in_wc'] >= 2) & (df_clean['vi_out_wc'] >= 5) &
        # Độ dài tối đa (Chống OOM GPU khi fine-tune LLM)
        (df_clean['vi_in_wc'] <= 350) & (df_clean['vi_out_wc'] <= 700)
    )
    df_clean = df_clean[valid_length_mask].copy()
    rows_after_len = len(df_clean)
    dropped_len = rows_after_lang - rows_after_len
    print(f"👉 Loại bỏ {dropped_len:,} dòng lệch tỷ lệ hoặc quá dài/quá ngắn. Còn lại {rows_after_len:,} dòng.")
    
    # --- Bước 7: Lọc ngữ nghĩa đối chiếu chữ số & thực thể (Heuristic Semantic Alignment) ---
    print("\n[Bước 7] Thực hiện đối chiếu ngữ nghĩa (Heuristic Number & Entity Alignment)...")
    
    def check_heuristics(row):
        en_in = str(row['original_input'])
        en_out = str(row['original_output'])
        vi_in = str(row['translated_input'])
        vi_out = str(row['translated_output'])
        
        en_text = (en_in + " " + en_out).lower()
        vi_text = (vi_in + " " + vi_out).lower()
        
        # 1. Đối chiếu Số lượng
        en_numbers = set(re_numbers.findall(en_text))
        vi_numbers = set(re_numbers.findall(vi_text))
        # Chỉ xét số lượng có nghĩa (2 chữ số trở lên)
        key_en_numbers = {num for num in en_numbers if len(num) >= 2}
        key_vi_numbers = {num for num in vi_numbers if len(num) >= 2}
        if key_en_numbers and not key_en_numbers.issubset(key_vi_numbers):
            # Nếu câu tiếng Anh có con số cụ thể mà tiếng Việt bị mất/sai số -> Loại bỏ
            return False
            
        # 2. Đối chiếu thực thể thời trang quan trọng (Mất 100% thực thể khi câu gốc có -> Loại bỏ)
        entity_detections = 0
        entity_matches = 0
        for cat, terms in entities.items():
            for en_term, vi_terms in terms.items():
                if re.search(r'\b' + re.escape(en_term) + r'\b', en_text):
                    entity_detections += 1
                    if any(vi_term in vi_text for vi_term in vi_terms):
                        entity_matches += 1
                        
        if entity_detections > 0 and entity_matches == 0:
            # Câu gốc chứa từ khóa thời trang quan trọng nhưng dịch không giữ lại bất kì từ tương ứng nào -> Dịch hỏng
            return False
            
        return True
        
    heuristics_mask = df_clean.apply(check_heuristics, axis=1)
    df_clean = df_clean[heuristics_mask].copy()
    rows_after_heuristics = len(df_clean)
    dropped_heuristics = rows_after_len - rows_after_heuristics
    print(f"👉 Loại bỏ {dropped_heuristics:,} dòng dịch lệch số hoặc mất thực thể thời trang. Còn lại {rows_after_heuristics:,} dòng.")
    
    # --- Tổng kết và lưu kết quả ---
    # Dọn dẹp các cột bổ trợ không cần dùng cho việc training
    cols_to_keep = ['original_input', 'original_output', 'translated_input', 'translated_output']
    df_final = df_clean[cols_to_keep].copy()
    
    # Tạo thư mục đầu ra nếu chưa có
    os.makedirs(os.path.dirname(FILE_OUTPUT), exist_ok=True)
    df_final.to_csv(FILE_OUTPUT, index=False, encoding='utf-8')
    
    print("\n" + "="*60)
    print("🎉 QUY TRÌNH CHUẨN HÓA DỮ LIỆU ĐÃ HOÀN THÀNH XUẤT SẮC!")
    print("="*60)
    print(f"📊 Tổng số lượng dòng ban đầu:  {initial_rows:,} dòng")
    print(f"📉 Số dòng bị loại bỏ:           {initial_rows - rows_after_heuristics:,} dòng ({((initial_rows - rows_after_heuristics)/initial_rows * 100):.2f}%)")
    print(f"⭐ Số lượng dòng sạch đầu ra:    {rows_after_heuristics:,} dòng ({((rows_after_heuristics)/initial_rows * 100):.2f}%)")
    print(f"💾 File sạch lưu tại:           {FILE_OUTPUT}")
    print("="*60)

if __name__ == "__main__":
    main()
