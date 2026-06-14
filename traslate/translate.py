import google.generativeai as genai
import pandas as pd
import threading
import time
import os
import sys
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Ép terminal Windows hỗ trợ in Emoji (UTF-8)
sys.stdout.reconfigure(encoding='utf-8')

# ================= CẤU HÌNH =================
# Nạp API Key bảo mật từ file .env (override=True để ép nhận Key mới nếu bạn vừa đổi)
load_dotenv(override=True)
API_KEY_ENV = os.getenv("GEMINI_API_KEY")
API_KEYS_STR = os.getenv("GEMINI_API_KEYS")

raw_keys_str = API_KEYS_STR if API_KEYS_STR else (API_KEY_ENV if API_KEY_ENV else "")
API_KEYS = [k.strip() for k in raw_keys_str.split(",") if k.strip()]

if not API_KEYS:
    print("❌ LỖI: Không tìm thấy GEMINI_API_KEY hoặc GEMINI_API_KEYS trong file .env!")
    exit()

# Tên file dữ liệu gốc
FILE_INPUT = "train-00000-of-00001-9b0ae8e510f95a07.parquet"
FILE_CHECKPOINT = "train_checkpoint.parquet"
FILE_OUTPUT = "train_translated.jsonl" # Đổi thành file JSONL cho mục đích finetune

# Số luồng chạy song song (Nếu dùng nhiều keys, mỗi key sẽ gánh khoảng 3 luồng song song để tối ưu và an toàn)
MAX_WORKERS = len(API_KEYS) * 3 if len(API_KEYS) > 1 else 4

# Danh sách các mô hình Gemma 4 theo yêu cầu của người dùng
MODELS = [
    "models/gemma-4-31b-it",
    "models/gemma-4-26b-a4b-it"
]
# ============================================

genai.configure(api_key=API_KEYS[0])
lock = threading.Lock()

# Xoay tua API Key để vượt qua giới hạn rate limit (nếu có nhiều keys)
import itertools
api_key_cycle = itertools.cycle(API_KEYS)
key_lock = threading.Lock()

def get_next_api_key():
    with key_lock:
        return next(api_key_cycle)

# Từ điển lưu trữ thời gian "hồi chiêu" của từng model (nếu bị Google chặn 429)
exhausted_until = {m: 0 for m in MODELS}
model_counter = 0

def get_available_model():
    """Tìm model rảnh theo kiểu vòng tròn (Round-Robin) để tránh spam trùng model gây 429"""
    global model_counter
    with lock:
        now = time.time()
        for _ in range(len(MODELS)):
            m = MODELS[model_counter % len(MODELS)]
            model_counter += 1
            if now >= exhausted_until[m]:
                return m
        return None # Nếu tất cả đều đang bị phạt

def mark_model_exhausted(model_name, delay_seconds):
    """Đánh dấu model bị phạt và cần chờ n giây"""
    with lock:
        exhausted_until[model_name] = time.time() + delay_seconds

def translate_completion(completion_text, input_text, context_text, index=None):
    if pd.isna(completion_text) or str(completion_text).strip() == "": 
        return ""
    
    for attempt in range(100):
        model_name = get_available_model()
        if not model_name:
            time.sleep(5)
            continue
            
        try:
            # Gemma 4 31B/26B là reasoning model. Ta dùng system_instruction để cung cấp ngữ cảnh,
            # và bắt buộc nó bọc kết quả dịch trong thẻ <translation> để ta trích xuất chính xác, sạch sẽ.
            system_instruction = (
                "You are an expert English to Vietnamese translator specializing in fashion and style guides.\n"
                "Translate the user's text to natural, fluent Vietnamese.\n"
                "Background context (use this only to understand the context, do not translate, do not output):\n"
                f"- User Persona/Input: {input_text}\n"
                f"- Context: {context_text}\n\n"
                "FEW-SHOT EXAMPLE (Strictly follow this translation style and format):\n"
                "--- START EXAMPLE ---\n"
                "Original Text:\n"
                "Outfit Combination 1: - Top: Fitted white linen shirt - Bottom: Slim-fit beige chinos - Shoe: Brown leather loafers - Accessories: Brown woven belt, aviator sunglasses\n"
                "Translation:\n"
                "<translation>\n"
                "Phối đồ 1:\n"
                "- Áo: Sơ mi linen màu trắng dáng ôm\n"
                "- Quần: Quần chinos màu be dáng slim-fit\n"
                "- Giày: Giày lười da màu nâu\n"
                "- Phụ kiện: Thắt lưng da đan màu nâu, kính phi công\n"
                "</translation>\n"
                "--- END EXAMPLE ---\n\n"
                "CRITICAL INSTRUCTION:\n"
                "Wrap your final Vietnamese translation inside <translation> and </translation> tags.\n"
                "Translate ONLY the text provided by the user. Do not explain, do not add notes, do not output anything outside the <translation> tags."
            )

            import google.ai.generativelanguage as glm
            current_key = get_next_api_key()
            client_options = {'api_key': current_key}
            client = glm.GenerativeServiceClient(client_options=client_options)

            model = genai.GenerativeModel(
                model_name,
                system_instruction=system_instruction
            )
            model._client = client

            user_prompt = (
                "CRITICAL: Translate the text below to Vietnamese. Wrap the translation inside <translation> and </translation> tags.\n"
                f"Text to translate:\n{completion_text}"
            )
            response = model.generate_content(user_prompt)
            
            if not response.parts:
                return completion_text 
            
            output_text = response.text.strip()
            
            # Trích xuất nội dung giữa các thẻ <translation> và </translation>
            cleaned_text = ""
            if "<translation>" in output_text and "</translation>" in output_text:
                parts = output_text.split("<translation>")
                last_part = parts[-1]
                if "</translation>" in last_part:
                    inner = last_part.split("</translation>")[0].strip()
                    if inner:
                        cleaned_text = inner
            
            # Dự phòng: nếu không tìm thấy thẻ chuẩn
            if not cleaned_text:
                if "<translation>" in output_text:
                    temp = output_text.split("<translation>")[-1]
                    if "</translation>" in temp:
                        temp = temp.split("</translation>")[0]
                    cleaned_text = temp.strip()
                elif "</translation>" in output_text:
                    cleaned_text = output_text.split("</translation>")[0].strip()
                else:
                    cleaned_text = output_text
                
            # Loại bỏ phần giới thiệu mở đầu hoặc kết luận dư thừa
            cleaned_text = clean_completion(cleaned_text)
                
            # Đảm bảo bản dịch sạch hoàn toàn không chứa vết suy luận
            if not is_translation_dirty(cleaned_text):
                return cleaned_text
            else:
                print(f"⚠️ Bản dịch dòng {index} bị dính lỗi/suy luận thừa ({model_name}). Đang thử dịch lại...", flush=True)
        except Exception as e:
            error_str = str(e).lower()
            
            if "429" in error_str or "exhausted" in error_str:
                import re
                match = re.search(r"retry in (\d+\.?\d*)s", error_str)
                delay = float(match.group(1)) + 2 if match else 60
                
                print(f"\n⚠️ {model_name} vừa cạn kiệt (phạt {delay:.0f}s). Hệ thống tự động kích hoạt Fallback đổi sang model khác...")
                mark_model_exhausted(model_name, delay)
            elif "400" in error_str:
                return completion_text
            else:
                print(f"\n⚠️ Lỗi mạng với {model_name}: {e}. Chờ 5s...")
                time.sleep(5)
                
    return completion_text
# Các mẫu để tìm kiếm dòng bắt đầu của outfit đầu tiên
outfit_start_patterns = [
    r'^\s*[-*#\d\s\.)]*\b(Phối đồ|Trang phục|Bộ|Gợi ý|Set đồ|Outfit|Cách phối đồ|Lựa chọn|Bộ trang phục|Trang phục phối hợp|Option)\b.*(?:1|#1|số 1)\b',
    r'^\s*(?:1\.|1\)|[-*]\s*1\.|[-*]\s*1\))\s*.*',
    r'^\s*[-*#]*\s*(Phối đồ|Outfit|Trang phục)\s*#?1\b',
]

def find_start_line_idx(lines):
    import re
    for idx, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        for p in outfit_start_patterns:
            if re.match(p, text, re.IGNORECASE):
                return idx
    return -1

def is_outfit_line(line):
    import re
    stripped = line.strip()
    if not stripped:
        return True
    # 1. Bắt đầu bằng dấu gạch đầu dòng hoặc khoảng trắng thụt lề
    if stripped.startswith(('-', '*', '•')) or line.startswith((' ', '\t')):
        return True
    # 2. Bắt đầu bằng số thứ tự (ví dụ: 2., 2), 10.)
    if re.match(r'^\s*\d+[\.\)]', stripped):
        return True
    # 3. Chứa từ khóa trang phục ở đầu
    keywords = ["phối đồ", "trang phục", "bộ", "set đồ", "outfit", "lựa chọn", "cách", "gợi ý", "option"]
    if any(k in stripped.lower()[:30] for k in keywords):
        # Tránh các câu chào dẫn nhập chứa từ khóa
        if "dưới đây là" in stripped.lower() or "tôi xin gợi ý" in stripped.lower() or "tất nhiên rồi" in stripped.lower() or "chắc chắn rồi" in stripped.lower():
            return False
        return True
    return False

def get_header_num_from_part(text):
    import re
    stripped = text.strip()
    if not stripped:
        return None
        
    m1 = re.match(r'^\s*(\d+)[\.\)]\s*(?:Gợi ý\s+|Sự kết hợp\s+)?(?:phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination)\b', stripped, re.IGNORECASE)
    if m1:
        return int(m1.group(1))
        
    m2 = re.match(r'^\s*(?:Gợi ý\s+|Sự kết hợp\s+)?(?:phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination)\s*(?:#|số\s+|thứ\s+)?(\d+)\b', stripped, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
        
    m3 = re.match(r'^\s*(\d+)[\.\)]\s*$', stripped)
    if m3:
        return int(m3.group(1))
        
    return None

def standardize_line(line):
    import re
    stripped = line.strip()
    if not stripped:
        return line
        
    if stripped.startswith(('-', '*', '•')) or any(stripped.startswith(k) for k in ["- Áo:", "- Quần:", "- Giày:", "- Phụ kiện:", "Áo:", "Quần:", "Giày:", "Phụ kiện:", "Váy:", "Đầm:", "Áo khoác:"]):
        return line
        
    parts = re.split(r'[:\-—–]', stripped, maxsplit=1)
    left_part = parts[0]
    right_part = parts[1] if len(parts) > 1 else ""
    
    num = get_header_num_from_part(left_part)
    if num is not None:
        indent = line[:len(line) - len(line.lstrip())]
        if right_part.strip():
            return f"{indent}Phối đồ {num}: {right_part.strip()}"
        else:
            return f"{indent}Phối đồ {num}:"
            
    num = get_header_num_from_part(stripped)
    if num is not None:
        indent = line[:len(line) - len(line.lstrip())]
        return f"{indent}Phối đồ {num}:"
        
    return line

def clean_completion(text):
    if not text or not isinstance(text, str):
        return text
    lines = text.splitlines()
    start_idx = find_start_line_idx(lines)
    if start_idx == -1:
        standardized_lines = [standardize_line(l) for l in lines]
        return "\n".join(standardized_lines)
        
    cleaned_lines = lines[start_idx:]
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
        
    standardized_lines = [standardize_line(l) for l in cleaned_lines]
    return "\n".join(standardized_lines)

def is_translation_dirty(text):
    if not text or not isinstance(text, str): 
        return True
    
    # Check for tags/codeblock artifacts
    if any(tag in text for tag in ["<translation>", "</translation>", "<think>", "</think>"]):
        return True
        
    # Check for reasoning arrows or indicators
    if "->" in text or "→" in text or "\\rightarrow" in text:
        return True
        
    # Check for markdown code blocks or backticks
    if "`" in text:
        return True
        
    # Check for untranslated headers or keywords using word boundaries
    import re
    keywords = [r"\boutfits?\b", r"\bcombinations?\b", r"\baccessor(y|ies)\b", r"\btags?\b", r"\bbackticks?\b"]
    for pattern in keywords:
        if re.search(pattern, text.lower()):
            return True
        
    # Check for common English sentences/words indicating reasoning blocks using regex with word boundaries
    import re
    common_english_words = ["the", "to", "with", "is", "this", "for", "and", "of", "or", "in"]
    english_word_count = 0
    for word in common_english_words:
        if re.search(r'\b' + re.escape(word) + r'\b', text.lower()):
            english_word_count += 1
            
    if english_word_count >= 3:
        return True
        
    return False

if not os.path.exists(FILE_INPUT):
    print(f"❌ Không tìm thấy file {FILE_INPUT}!")
else:
    print(f"📦 Đang đọc dữ liệu từ {FILE_INPUT}...")
    df = pd.read_parquet(FILE_INPUT)
    total_rows = len(df)
    completed_results = {}
    
    if os.path.exists(FILE_CHECKPOINT):
        df_checkpoint = pd.read_parquet(FILE_CHECKPOINT)
        if 'original_index' not in df_checkpoint.columns:
            df_checkpoint['original_index'] = range(len(df_checkpoint))
        
        raw_checkpoint_data = {int(row['original_index']): row for row in df_checkpoint.to_dict('records')}
        clean_count = 0
        dirty_count = 0
        
        for idx, row in raw_checkpoint_data.items():
            comp_val = row.get('completion', '')
            if is_translation_dirty(comp_val):
                dirty_count += 1
            else:
                clean_count += 1
                completed_results[idx] = row
                
        print(f"🔄 Đã nạp checkpoint: {len(raw_checkpoint_data)} dòng từ file checkpoint.")
        print(f"   - Giữ lại {clean_count} dòng dịch chuẩn.")
        print(f"   - Loại bỏ {dirty_count} dòng bị lỗi/suy luận để dịch lại.")
        
        # Ghi đè file checkpoint ngay lập tức với các dòng sạch để đồng bộ hóa đĩa cứng
        if clean_count > 0:
            temp_list = [completed_results[i] for i in sorted(completed_results.keys())]
            pd.DataFrame(temp_list).to_parquet(FILE_CHECKPOINT, index=False)
        else:
            # Nếu toàn bộ checkpoint bị lỗi hoặc trống, xóa file checkpoint cũ để bắt đầu sạch
            if os.path.exists(FILE_CHECKPOINT):
                try:
                    os.remove(FILE_CHECKPOINT)
                except Exception:
                    pass
        
    indices_to_translate = [i for i in range(total_rows) if i not in completed_results]
    
    def process_row(index, row):
        # Giãn cách ngẫu nhiên ngắn để so le gửi request đa luồng
        time.sleep(random.uniform(0.1, 0.5))
        
        # Lấy dữ liệu gốc
        input_text = str(row.get('input', ''))
        context_text = str(row.get('context', ''))
        completion_text = str(row.get('completion', ''))
        
        # => CHIẾN LƯỢC MỚI: Truyền cả 3 cột vào để AI hiểu ngữ cảnh, nhưng chỉ yêu cầu trả về bản dịch của cột completion <=
        translated_completion = translate_completion(completion_text, input_text, context_text, index)
            
        # Tạo dòng mới: input và context giữ nguyên tiếng Anh, completion đã dịch (hoặc giữ nguyên tiếng Anh nếu lỗi siêu nặng)
        row_translated = {
            "original_index": index,
            "input": input_text,
            "completion": translated_completion,
            "context": context_text
        }
        
        with lock:
            completed_results[index] = row_translated
            c = len(completed_results)
            print(f"⏳ Tiến độ: {c}/{total_rows} dòng... (Dòng {index} vừa dịch xong)", flush=True)
            
            # Lưu checkpoint mỗi 5 dòng
            if c % 5 == 0:
                temp_list = [completed_results[i] for i in sorted(completed_results.keys())]
                pd.DataFrame(temp_list).to_parquet(FILE_CHECKPOINT, index=False)

    if indices_to_translate:
        print(f"🚀 Bắt đầu gọi Gemini API dịch {len(indices_to_translate)} dòng với {MAX_WORKERS} luồng...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(process_row, idx, df.iloc[idx]) for idx in indices_to_translate]
            for future in as_completed(futures):
                pass
                
    # Lưu file hoàn chỉnh
    final_list = [completed_results[i] for i in sorted(completed_results.keys())]
    df_final = pd.DataFrame(final_list)
    if "original_index" in df_final.columns: 
        df_final = df_final.drop(columns=["original_index"])
        
    # Xuất ra định dạng JSON Lines (.jsonl) siêu chuẩn để đem đi fine-tune cho các mô hình AI khác
    df_final.to_json(FILE_OUTPUT, orient="records", lines=True, force_ascii=False)
    print(f"\n✅ CHÚC MỪNG! Đã dịch xong toàn bộ {total_rows} dòng.")
    print(f"Kết quả đã được xuất ra định dạng JSON tại:\n{FILE_OUTPUT}")
