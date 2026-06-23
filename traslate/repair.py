import google.generativeai as genai
import google.ai.generativelanguage as glm
import pandas as pd
import os
import sys
import re
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(override=True)

API_KEY_ENV = os.getenv("GEMINI_API_KEY")
API_KEYS = [k.strip() for k in API_KEY_ENV.split(",") if k.strip()]

if not API_KEYS:
    print("❌ LỖI: Không tìm thấy GEMINI_API_KEY hoặc GEMINI_API_KEYS trong file .env!")
    exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_INPUT = os.path.join(SCRIPT_DIR, "processed", "train-00000-of-00001-9b0ae8e510f95a07.parquet")
FILE_OUTPUT = os.path.join(SCRIPT_DIR, "translated", "train_translated.jsonl")
FILE_CHECKPOINT = os.path.join(SCRIPT_DIR, "translated", "train_checkpoint.parquet")
MODEL_NAME = "models/gemini-flash-lite-latest"

current_key_idx = 0
key_lock = threading.Lock()
thread_lock = threading.Lock()
save_lock = threading.Lock()

def get_next_api_key():
    global current_key_idx
    with key_lock:
        key = API_KEYS[current_key_idx]
        current_key_idx = (current_key_idx + 1) % len(API_KEYS)
        return key

def has_intro(text):
    if not text:
        return False
    lines = text.splitlines()
    for l in lines:
        stripped = l.strip()
        if not stripped:
            continue
            
        pattern_item = r'(?i)^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer|áo khoác|boots|dép)\b'
        if re.match(pattern_item, stripped):
            return False
            
        m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', stripped)
        if m_dig:
            return False
            
        pattern = r'\b(?:outfit|phối đồ|trang phục|combination|option|set|lựa chọn|bộ đồ|bộ trang phục|look|style)\b\s*(?:combination|recommendation|option|set|look|style)?\s*(?:#|số\s+|thứ\s+|number\s+|no\.\s+)?\d+\b'
        m_word = re.search(pattern, stripped, re.IGNORECASE)
        if m_word:
            return False
            
        return True
    return False

def has_outro(text):
    if not text:
        return False
    lines = text.splitlines()
    last_line = ""
    for l in reversed(lines):
        if l.strip():
            last_line = l.strip()
            break
    if not last_line:
        return False
    if last_line.startswith(('-', '*', '•')):
        return False
        
    pattern_item = r'(?i)^\s*(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer|áo khoác|boots|dép)\b'
    if re.match(pattern_item, last_line):
        return False
        
    m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', last_line)
    if m_dig:
        return False
        
    pattern = r'\b(?:outfit|phối đồ|trang phục|combination|option|set|lựa chọn|bộ đồ|bộ trang phục|look|style)\b\s*(?:combination|recommendation|option|set|look|style)?\s*(?:#|số\s+|thứ\s+|number\s+|no\.\s+)?\d+\b'
    m_word = re.search(pattern, last_line, re.IGNORECASE)
    if m_word:
        return False
        
    return True

def count_outfits_correct(text):
    if not text:
        return 0
    lines = text.splitlines()
    starts = 0
    for l in lines:
        stripped = l.strip()
        if not stripped:
            continue
        m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', stripped)
        m_word = re.search(r'\b(?:phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination|gợi ý|bộ)\b\s*(?:#|số\s+|thứ\s+)?\d+\b', stripped, re.IGNORECASE)
        
        if m_dig or m_word:
            pattern_list_item = r'(?i)^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer)\s*:'
            if re.match(pattern_list_item, stripped):
                continue
            starts += 1
    return starts if starts > 0 else 5

def standardize_completion(text):
    if not text or not isinstance(text, str):
        return text
    lines = text.splitlines()
    
    starts = []
    for idx, l in enumerate(lines):
        stripped = l.strip()
        if not stripped:
            continue
        m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', stripped)
        m_word = re.search(r'\b(phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination|gợi ý|bộ)\b\s*(?:#|số\s+|thứ\s+)?\d+\b', stripped, re.IGNORECASE)
        if m_dig or m_word:
            pattern_list_item = r'(?i)^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer)\s*:'
            if re.match(pattern_list_item, stripped):
                continue
            starts.append(idx)
            
    for seq_num, idx in enumerate(starts, 1):
        line = lines[idx]
        indent = line[:len(line) - len(line.lstrip())]
        lines[idx] = f"{indent}Phối đồ {seq_num}:"
        
    kw_mapping = {
        "áo": "Áo",
        "quần": "Quần",
        "giày": "Giày",
        "phụ kiện": "Phụ kiện",
        "váy": "Váy",
        "chân váy": "Chân váy",
        "đầm": "Đầm",
        "áo khoác": "Áo khoác",
        "phần dưới": "Phần dưới",
        "top": "Áo",
        "bottom": "Quần",
        "shoe": "Giày",
        "shoes": "Giày",
        "accessories": "Phụ kiện",
        "accessory": "Phụ kiện"
    }
    
    for idx in range(len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        
        m_item = re.match(r'^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(áo|quần|giày|phụ kiện|váy|chân váy|đầm|vest|blazer|sơ mi|top|bottom|shoe|shoes|accessories|accessory|phần dưới|áo khoác|boots|dép)\s*[:\-—–]\s*(.*)', stripped, re.IGNORECASE)
        if m_item:
            kw = m_item.group(1).lower()
            content = m_item.group(2).strip()
            mapped_kw = kw_mapping.get(kw, kw.capitalize())
            lines[idx] = f"- {mapped_kw}: {content}"
            
    return "\n".join(lines)

def translate_completion(completion_text, input_text, context_text, index=None):
    if pd.isna(completion_text) or str(completion_text).strip() == "": 
        return ""
    
    for attempt in range(15):
        api_key = get_next_api_key()
        try:
            client_options = {'api_key': api_key}
            client = glm.GenerativeServiceClient(client_options=client_options)
            
            system_instruction = (
                "You are an expert English to Vietnamese translator specializing in fashion and style guides.\n"
                "Translate the user's text to natural, fluent Vietnamese.\n"
                "Background context (use this only to understand the context, do not translate, do not output):\n"
                f"- User Persona/Input: {input_text}\n"
                f"- Context: {context_text}\n\n"
                "CRITICAL FORMAT RULES:\n"
                "1. Keep any introduction and concluding sentences (outro) present in the original text, translating them accurately into natural Vietnamese. Do not discard them.\n"
                "2. Each outfit combination must start with 'Phối đồ X:' on its own line (where X is the number, e.g. Phối đồ 1:, Phối đồ 2:). Do not translate or include any style titles (like 'Classic Elegance' or 'Modern Sophistication'). Just output 'Phối đồ X:'.\n"
                "3. Use bullet points starting with a hyphen and a space '- ' for all items inside the outfit. Specifically, translate 'Top' to '- Áo:', 'Bottom' to '- Quần:' (or '- Váy:' / '- Chân váy:' / '- Đầm:'), 'Shoe' or 'Shoes' to '- Giày:', 'Accessories' to '- Phụ kiện:'. Always start these lines with a hyphen and a space, e.g., '- Áo:'.\n"
                "4. Translate all explanation sentences and descriptions from the English source accurately. Do not invent any new facts or make anything up.\n"
                "5. Wrap the final Vietnamese translation inside <translation> and </translation> tags.\n"
                "6. Do not include any introductory or concluding remarks outside the <translation> tags."
            )
            
            with thread_lock:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(
                    MODEL_NAME,
                    system_instruction=system_instruction
                )
                model._client = client
            
            user_prompt = (
                "CRITICAL: Translate the text below to Vietnamese. Wrap the translation inside <translation> and </translation> tags.\n"
                f"Text to translate:\n{completion_text}"
            )
            
            response = model.generate_content(user_prompt, request_options={"timeout": 60})
            if not response.parts:
                time.sleep(2)
                continue
                
            output_text = response.text.strip()
            
            cleaned_text = ""
            if "<translation>" in output_text and "</translation>" in output_text:
                parts = output_text.split("<translation>")
                last_part = parts[-1]
                if "</translation>" in last_part:
                    inner = last_part.split("</translation>")[0].strip()
                    if inner:
                        cleaned_text = inner
                        
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
                    
            if cleaned_text:
                return cleaned_text
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "limit" in error_str:
                print(f"  [Row {index}] API Key {API_KEYS.index(api_key)} rate limited. Cooling down 30s...", flush=True)
                time.sleep(30)
            else:
                print(f"  [Row {index}] Error: {e}", flush=True)
                time.sleep(2)
                
    return ""

df_orig = None
translated_rows = []

def save_checkpoint_disk():
    with open(FILE_OUTPUT, 'w', encoding='utf-8') as f_out:
        for r_row in translated_rows:
            row_to_save = {k: v for k, v in r_row.items() if k != 'original_index'}
            f_out.write(json.dumps(row_to_save, ensure_ascii=False) + '\n')
    df_checkpoint = pd.DataFrame(translated_rows)
    df_checkpoint.to_parquet(FILE_CHECKPOINT, index=False)
    print("💾 Đã lưu checkpoint thành công.", flush=True)

def process_row(idx):
    orig_row = df_orig.iloc[idx]
    input_text = orig_row['input']
    context_text = orig_row['context']
    completion_text = orig_row['completion']
    
    orig_count = count_outfits_correct(completion_text)
    
    for attempt in range(5):
        translated = translate_completion(completion_text, input_text, context_text, idx)
        if not translated:
            time.sleep(2)
            continue
        
        standardized = standardize_completion(translated)
        new_count = count_outfits_correct(standardized)
        
        if new_count == orig_count:
            trans_intro = has_intro(standardized)
            trans_outro = has_outro(standardized)
            orig_intro = has_intro(completion_text)
            orig_outro = has_outro(completion_text)
            
            has_non_hyphen = False
            lines = standardized.splitlines()
            for l in lines:
                stripped = l.strip()
                if re.match(r'^(?:Áo|Quần|Váy|Chân váy|Đầm|Giày|Phụ kiện|Tops?|Bottoms?|Shoes?|Accessories?|Footwear)\s*:', stripped, re.IGNORECASE):
                    has_non_hyphen = True
                    break
            
            has_bad_header = False
            for l in lines:
                stripped = l.strip()
                if not stripped:
                    continue
                m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', stripped)
                m_word = re.search(r'\b(?:phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination|gợi ý|bộ)\b\s*(?:#|số\s+|thứ\s+)?\d+\b', stripped, re.IGNORECASE)
                if m_dig or m_word:
                    if re.match(r'(?i)^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer)\s*:', stripped):
                        continue
                    if not re.match(r'^Phối đồ \d+:', stripped):
                        has_bad_header = True
                        break
            
            if (orig_intro == trans_intro) and (orig_outro == trans_outro) and not has_non_hyphen and not has_bad_header:
                with save_lock:
                    translated_rows[idx]['completion'] = standardized
                    save_checkpoint_disk()
                print(f"✅ Vá thành công dòng {idx}! (Outfits: {new_count})", flush=True)
                return True
            else:
                print(f"  [Row {idx}] Mẫu dịch không khớp định dạng (Intro/Outro khớp: {orig_intro==trans_intro}/{orig_outro==trans_outro}, non-hyphen: {has_non_hyphen}, bad-header: {has_bad_header}). Đang thử lại...", flush=True)
                time.sleep(2)
        else:
            print(f"  [Row {idx}] Số bộ đồ không khớp (Original: {orig_count}, Translated: {new_count}). Đang thử lại...", flush=True)
            time.sleep(2)
            
    print(f"🔴 Thất bại hoàn toàn dòng {idx} sau 5 nỗ lực.", flush=True)
    return False

def main():
    global df_orig, translated_rows
    print("📦 Đang đọc dữ liệu gốc và dữ liệu đã dịch...", flush=True)
    df_orig = pd.read_parquet(FILE_INPUT)
    
    translated_rows = []
    with open(FILE_OUTPUT, 'r', encoding='utf-8') as f:
        for line in f:
            translated_rows.append(json.loads(line))
            
    print("🔍 Đang phát hiện các dòng lỗi cần dịch lại động...", flush=True)
    mismatch_indices = []
    for idx, trans_row in enumerate(translated_rows):
        orig_row = df_orig.iloc[idx]
        orig_comp = orig_row['completion']
        trans_comp = trans_row.get('completion', '')
        
        needs_fix = False
        if has_intro(orig_comp) and not has_intro(trans_comp):
            needs_fix = True
        elif has_outro(orig_comp) and not has_outro(trans_comp):
            needs_fix = True
        else:
            lines = trans_comp.splitlines()
            has_non_hyphen = False
            for l in lines:
                stripped = l.strip()
                if re.match(r'^(?:Áo|Quần|Váy|Chân váy|Đầm|Giày|Phụ kiện|Tops?|Bottoms?|Shoes?|Accessories?|Footwear)\s*:', stripped, re.IGNORECASE):
                    has_non_hyphen = True
                    break
            
            has_bad_header = False
            for l in lines:
                stripped = l.strip()
                if not stripped:
                    continue
                m_dig = re.match(r'^\s*[-*•#]?\s*(\d+)[\.\):]', stripped)
                m_word = re.search(r'\b(?:phối đồ|trang phục|lựa chọn|bộ đồ|bộ trang phục|outfit|option|look|style|set|combination|gợi ý|bộ)\b\s*(?:#|số\s+|thứ\s+)?\d+\b', stripped, re.IGNORECASE)
                if m_dig or m_word:
                    if re.match(r'(?i)^\s*[-*•#]?\s*(?:\d+[\.\)]\s*)?(?:áo|quần|giày|phụ kiện|top|bottom|shoe|shoes|accessories|accessory|footwear|phần dưới|chân váy|đầm|váy|sơ mi|blazer)\s*:', stripped):
                        continue
                    if not re.match(r'^Phối đồ \d+:', stripped):
                        has_bad_header = True
                        break
            
            if has_non_hyphen or has_bad_header:
                needs_fix = True
                
        if needs_fix:
            mismatch_indices.append(idx)
            
    total_to_fix = len(mismatch_indices)
    print(f"🚀 Tìm thấy {total_to_fix} dòng cần vá. Chạy đa luồng với ThreadPoolExecutor (max_workers=3)...", flush=True)
    
    if total_to_fix == 0:
        print("✅ Không còn dòng nào bị lỗi! Dữ liệu đã sạch 100%.", flush=True)
        return
        
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_row, idx): idx for idx in mismatch_indices}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"❌ Lỗi xử lý dòng {idx}: {e}", flush=True)
                
    print("🎉 Đã hoàn thành toàn bộ quá trình vá và lưu dữ liệu sạch!", flush=True)

if __name__ == '__main__':
    main()
