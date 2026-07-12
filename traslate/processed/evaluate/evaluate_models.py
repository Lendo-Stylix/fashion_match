import os
import json
import re
import time
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
import anthropic

# Tự động tải API key từ file .env
load_dotenv()

# ==========================================
# CẤU HÌNH HỆ THỐNG ĐÁNH GIÁ (JUDGE CONFIG)
# ==========================================

# 1. Chọn nhà cung cấp dịch vụ cho Judge: "gemini", "anthropic", "openai", "groq"
# Bạn có thể đổi thành "gemini", "openai", "anthropic" hoặc "groq"
JUDGE_PROVIDER = "groq"

# 2. Chọn model muốn dùng làm Judge tương ứng với nhà cung cấp:
# - Gemini: "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"
# - Anthropic: "claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"
# - Groq: "llama-3.3-70b-versatile", "llama-3.1-8b-instant"
JUDGE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

LIMIT_SAMPLES = None

# 4. Thời gian nghỉ giữa các request (giây) để tránh bị dính Rate Limit (429)
# Với Groq Free Tier, giới hạn tối đa là 30 request/phút. Đặt 2.0 giây để đảm bảo luôn ở dưới giới hạn này.
# Nhờ cơ chế tự động xoay key, chúng ta có thể giảm thời gian chờ xuống 1.5 giây để chạy nhanh hơn
SLEEP_DELAY = 1.5

# 5. Chế độ mô phỏng (True để chạy thử không gọi API thực tế)
MOCK_MODE = False

# ==========================================
# KHỞI TẠO CÁC CLIENT
# ==========================================

# Khởi tạo Anthropic Client
anthropic_client = anthropic.Anthropic()

# Khởi tạo OpenAI Client
openai_client = OpenAI()

# Cấu hình xoay vòng Groq API key để tránh bị Rate Limit / Quá hạn mức ngày (TPD)
groq_keys = [
    os.environ.get("GROQ_API_KEY"),
    "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"
]
groq_keys = [k.strip() for k in groq_keys if k and k.strip()]

class RotatingGroqClient:
    def __init__(self, keys):
        self.keys = keys
        self.current_idx = 0
        
    def create_chat_completion(self, model, messages, temperature=0.0, max_tokens=1024):
        if not self.keys:
            raise ValueError("Không tìm thấy GROQ_API_KEY trong file .env hoặc danh sách dự phòng")
            
        attempts = len(self.keys)
        
        # 1. Thử gọi model chính trước (meta-llama/llama-4-scout-17b-16e-instruct)
        for _ in range(attempts):
            key = self.keys[self.current_idx]
            client_idx = self.current_idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            
            try:
                client = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    print(f"\n[SWAP KEY] Groq Key #{client_idx + 1} bị giới hạn tần suất/hạn mức (429) cho model {model}. Đang chuyển key...")
                    continue
                else:
                    raise e
                    
        # 2. Nếu model chính (Llama 4 Scout) hết hạn ngạch trên toàn bộ key,
        # chúng ta sẽ chuyển sang model dự phòng 1: llama-3.3-70b-versatile
        fallback_model_1 = "llama-3.3-70b-versatile"
        print(f"\n[FALLBACK 1] Chuyển sang model dự phòng 1: {fallback_model_1}...")
        for _ in range(attempts):
            key = self.keys[self.current_idx]
            client_idx = self.current_idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            
            try:
                client = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1"
                )
                response = client.chat.completions.create(
                    model=fallback_model_1,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    print(f"\n[SWAP KEY fallback 1] Groq Key #{client_idx + 1} bị giới hạn với model {fallback_model_1}. Đang chuyển key...")
                    continue
                else:
                    raise e

        # 3. Nếu cả Llama 4 Scout và Llama 3.3 70B đều hết hạn ngạch,
        # chúng ta sẽ chuyển sang model dự phòng 2: qwen/qwen3-32b (Qwen có quota hoàn toàn riêng biệt)
        fallback_model_2 = "qwen/qwen3-32b"
        print(f"\n[FALLBACK 2] Chuyển sang model dự phòng 2: {fallback_model_2}...")
        for _ in range(attempts):
            key = self.keys[self.current_idx]
            client_idx = self.current_idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            
            try:
                client = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1"
                )
                response = client.chat.completions.create(
                    model=fallback_model_2,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    print(f"\n[SWAP KEY fallback 2] Groq Key #{client_idx + 1} bị giới hạn với model {fallback_model_2}. Đang chuyển key...")
                    continue
                else:
                    raise e

        # 4. Nếu toàn bộ model trên đều hết hạn ngạch,
        # chúng ta sẽ chuyển sang model dự phòng 3: llama-3.1-8b-instant
        fallback_model_3 = "llama-3.1-8b-instant"
        print(f"\n[FALLBACK 3] Chuyển sang model dự phòng 3: {fallback_model_3}...")
        for _ in range(attempts):
            key = self.keys[self.current_idx]
            client_idx = self.current_idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            
            try:
                client = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1"
                )
                response = client.chat.completions.create(
                    model=fallback_model_3,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    print(f"\n[SWAP KEY fallback 3] Groq Key #{client_idx + 1} bị giới hạn với model {fallback_model_3}. Đang chuyển key...")
                    continue
                else:
                    raise e
                    
        # 5. Nếu toàn bộ model đều quá hạn mức, tạm thời nghỉ 25 giây và thử lại bằng Qwen
        print("\nTất cả các key và model đều quá hạn mức. Chờ 25 giây...")
        time.sleep(25)
        
        key = self.keys[0]
        client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        return client.chat.completions.create(
            model=fallback_model_2,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

groq_client = RotatingGroqClient(groq_keys)

# Cấu hình xoay vòng Gemini API key để tránh bị Rate Limit / Quá hạn mức
gemini_keys = os.environ.get("GEMINI_API_KEY", "").split(",")
gemini_keys = [k.strip() for k in gemini_keys if k.strip()]

class RotatingGeminiClient:
    def __init__(self, keys):
        self.keys = keys
        self.current_idx = 0
        
    def generate_content(self, model, contents, **kwargs):
        if not self.keys:
            raise ValueError("Không tìm thấy GEMINI_API_KEY trong file .env")
            
        attempts = len(self.keys)
        for try_num in range(5):  # Thử tối đa 5 lần quay vòng hết các key
            for _ in range(attempts):
                key = self.keys[self.current_idx]
                client_idx = self.current_idx
                # Chuyển sang key tiếp theo cho cuộc gọi sau (Round-robin)
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(model=model, contents=contents, **kwargs)
                    return response
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower():
                        print(f"Key {client_idx} bị giới hạn tần suất (429). Đang chuyển sang key tiếp theo...")
                    else:
                        print(f"Lỗi với Gemini Key {client_idx}: {e}. Đang chuyển sang key tiếp theo...")
            
            # Nếu tất cả các key đều bị lỗi trong vòng này, chờ rồi thử lại
            sleep_time = (try_num + 1) * 5
            print(f"Tất cả các key đều bận hoặc hết hạn mức. Chờ {sleep_time} giây trước khi thử lại...")
            time.sleep(sleep_time)
            
        raise RuntimeError("Tất cả các Gemini API key đều lỗi hoặc quá hạn mức.")

gemini_client = RotatingGeminiClient(gemini_keys)

def extract_json(text):
    """Trích xuất và parse JSON từ văn bản phản hồi của LLM."""
    if not text:
        return None
    # Loại bỏ think tag nếu có (đặc biệt đối với các model suy nghĩ của Qwen/DeepSeek)
    if "<think>" in text:
        if "</think>" in text:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        else:
            text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
            
    # Tìm khối JSON trong văn bản
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
            
    # Thử làm sạch trực tiếp đầu ra
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
        
    try:
        return json.loads(cleaned.strip())
    except Exception as e:
        print(f"Không thể parse JSON từ text. Lỗi: {e}")
        return None

def llm_as_a_judge(prompt, generated_text, reference_text):
    """
    Dùng LLM làm giám khảo đánh giá câu trả lời trên 5 tiêu chí thời trang cốt lõi.
    Trả về dictionary chứa điểm 5 tiêu chí và phần lập luận giải thích.
    """
    if MOCK_MODE:
        import random
        random.seed(abs(hash(prompt)))
        return {
            'context_utilization': random.randint(3, 5),
            'trend_compliance': random.randint(3, 5),
            'fashion_knowledge_qa': random.randint(3, 5),
            'faithfulness': random.randint(3, 5),
            'hallucination': random.randint(3, 5),
            'reasoning': "Đây là kết quả đánh giá mô phỏng ở chế độ MOCK_MODE."
        }

    judge_prompt = f"""
    Bạn là một Giám khảo thời trang khách quan. Hãy chấm điểm câu trả lời của AI dựa trên Câu trả lời MẪU (Chuẩn) và Yêu cầu của khách hàng.
    Hãy chấm điểm từ 1 đến 5 (số nguyên) cho 5 tiêu chí sau:
    1. context_utilization (Khai thác và Áp dụng Ngữ cảnh): Khả năng đọc hiểu, chắt lọc và tổng hợp thông tin từ ngữ cảnh để giải quyết trọn vẹn yêu cầu.
    2. trend_compliance (Nắm bắt Xu hướng & Tuân thủ Phong cách): Đề xuất key_items phù hợp và né tránh các outdated_trends_to_avoid trong đồ thị tri thức.
    3. fashion_knowledge_qa (Hỏi đáp Kiến thức Thời trang): Tư vấn thời trang chuẩn xác, logic chuyên nghiệp, không khuyên phản thẩm mỹ.
    4. faithfulness (Tính trung thực với ngữ cảnh): Tất cả thông tin tư vấn đều có căn cứ từ ngữ cảnh cung cấp, không suy diễn quá đà.
    5. hallucination (Chống ảo giác): Không bịa đặt sản phẩm, giá tiền, hoặc link không tồn tại.

    Hãy trả về một JSON object duy nhất có cấu trúc chính xác như dưới đây. Không kèm bất kỳ lời dẫn hay văn bản thừa nào ngoài JSON.
    {{
      "context_utilization": [số nguyên từ 1 đến 5],
      "trend_compliance": [số nguyên từ 1 đến 5],
      "fashion_knowledge_qa": [số nguyên từ 1 đến 5],
      "faithfulness": [số nguyên từ 1 đến 5],
      "hallucination": [số nguyên từ 1 đến 5],
      "reasoning": "[Giải thích ngắn gọn lý do chấm điểm bằng tiếng Việt, khoảng 2-3 câu]"
    }}

    Dữ liệu đánh giá:
    - Yêu cầu của khách hàng: {prompt}
    - Câu trả lời MẪU (Chuẩn): {reference_text}
    - Câu trả lời CỦA AI CẦN CHẤM: {generated_text}
    """
    
    # Thiết lập cấu hình bộ lọc an toàn tối thiểu (BLOCK_NONE) để tránh lỗi kiểm duyệt với các từ nhạy cảm trong ngành thời trang
    safety_settings = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]
    
    try:
        if JUDGE_PROVIDER == "gemini":
            response = gemini_client.generate_content(
                model=JUDGE_MODEL,
                contents=judge_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=500,
                    safety_settings=safety_settings
                )
            )
            response_text = response.text
        elif JUDGE_PROVIDER == "anthropic":
            message = anthropic_client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=500,
                temperature=0.0,
                system="Bạn là một Giám khảo thời trang khách quan, hãy trả về kết quả dưới dạng JSON theo đúng cấu trúc yêu cầu.",
                messages=[{"role": "user", "content": judge_prompt}]
            )
            response_text = message.content[0].text
        elif JUDGE_PROVIDER == "openai":
            response = openai_client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=500
            )
            response_text = response.choices[0].message.content
        elif JUDGE_PROVIDER == "groq":
            response = groq_client.create_chat_completion(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=1024
            )
            response_text = response.choices[0].message.content
        else:
            raise ValueError(f"Không nhận diện được JUDGE_PROVIDER: {JUDGE_PROVIDER}")
            
        if response_text is None:
            print("Cảnh báo: Câu trả lời bị chặn bởi bộ lọc an toàn hoặc không có nội dung.")
            return None
            
        parsed_result = extract_json(response_text)
        if not parsed_result:
            # Fallback nếu không parse được JSON
            print(f"Cảnh báo: Không thể phân tích cú pháp JSON của Judge. Phản hồi thô: {response_text}")
            return None
            
        # Đảm bảo các trường điểm số hợp lệ
        for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']:
            if k not in parsed_result:
                parsed_result[k] = 3 # Trị số mặc định trung bình
            else:
                try:
                    parsed_result[k] = max(1, min(5, int(parsed_result[k])))
                except ValueError:
                    parsed_result[k] = 3
                    
        if 'reasoning' not in parsed_result:
            parsed_result['reasoning'] = "Không có lý do chi tiết."
            
        return parsed_result
    except Exception as e:
        print(f"❌ Lỗi gọi API ({JUDGE_PROVIDER}): {e}")
        return None

def evaluate_model_file(filepath, limit=None):
    """Chạy đánh giá cho 1 file kết quả, hỗ trợ resume và tự động chuẩn hóa sang định dạng mới."""
    # Xác định đường dẫn file checkpoint
    eval_filepath = filepath.replace(".json", "_eval.json")
    if "tested" in eval_filepath:
        eval_filepath = eval_filepath.replace("tested", "evaluated")
    
    # Đọc dữ liệu từ checkpoint cũ nếu có, nếu không thì đọc file gốc
    data = []
    if os.path.exists(eval_filepath):
        try:
            with open(eval_filepath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            print(f"Phát hiện checkpoint cũ tại: {eval_filepath}")
            
            # Chuẩn hóa dữ liệu cũ sang cấu trúc mới
            data = []
            for i, row in enumerate(loaded_data):
                if "question" in row:
                    data.append(row)
                else:
                    item = {
                        "id": row.get("id") or f"Q-{i+1:03d}",
                        "question": row.get("prompt") or "",
                        "ground_truth": row.get("reference_text") or "",
                        "contexts": row.get("contexts") or [],
                        "metadata": row.get("metadata") or {"category": row.get("category", "unknown")},
                        "retrieved_contexts": row.get("retrieved_contexts") or [],
                        "answer": row.get("generated_text") or ""
                    }
                    # Nếu đã có đánh giá
                    if "judge_score" in row or "context_utilization" in row or "knowledge_retrieval" in row:
                        item["evaluation"] = {
                            "context_utilization": round(row.get("context_utilization", row.get("knowledge_retrieval", row.get("judge_score", 3.0))) / 5.0, 2),
                            "trend_compliance": round(row.get("trend_compliance", row.get("citation_accuracy", row.get("judge_score", 3.0))) / 5.0, 2),
                            "fashion_knowledge_qa": round(row.get("fashion_knowledge_qa", row.get("judge_score", 3.0)) / 5.0, 2),
                            "faithfulness": round(row.get("faithfulness", row.get("judge_score", 3.0)) / 5.0, 2),
                            "hallucination": round(row.get("hallucination", row.get("judge_score", 3.0)) / 5.0, 2),
                            "reasoning": row.get("judge_reasoning", row.get("reasoning", ""))
                        }
                    data.append(item)
        except Exception as e:
            print(f"Lỗi đọc file checkpoint {eval_filepath}: {e}. Đang tải lại file gốc...")
            
    if not data:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            data = []
            for i, row in enumerate(raw_data):
                data.append({
                    "id": f"Q-{i+1:03d}",
                    "question": row.get("prompt") or row.get("question") or "",
                    "ground_truth": row.get("reference_text") or row.get("ground_truth") or "",
                    "contexts": row.get("contexts") or [],
                    "metadata": row.get("metadata") or {"category": row.get("category", "unknown")},
                    "retrieved_contexts": row.get("retrieved_contexts") or [],
                    "answer": row.get("generated_text") or row.get("answer") or ""
                })
        except FileNotFoundError:
            print(f"⚠️ Bỏ qua: Không tìm thấy file {filepath}")
            return None

    if limit is not None:
        data = data[:limit]
        
    total_samples = len(data)
    if total_samples == 0:
        return None

    completed_samples = 0
    for row in data:
        has_eval = 'evaluation' in row and all(k in row['evaluation'] for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination'])
        if has_eval:
            completed_samples += 1
            
    if completed_samples > 0:
        print(f"  -> Tiếp tục chạy: Đã chấm {completed_samples}/{total_samples} mẫu trước đó.")

    for i, row in enumerate(data):
        # Bỏ qua nếu đã được chấm điểm đủ các tiêu chí mới
        has_eval = 'evaluation' in row and all(k in row['evaluation'] for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination'])
        if has_eval:
            continue
            
        prompt = row.get('question', '')
        gen_text = row.get('answer', '')
        ref_text = row.get('ground_truth', '') 
        
        # Thêm khoảng nghỉ để tránh Spam API quá nhanh gây Rate Limit (bỏ qua nếu chạy Mock)
        if not MOCK_MODE:
            time.sleep(SLEEP_DELAY)
        
        # Thử gọi API tối đa 3 lần nếu bị lỗi kết nối hoặc parse JSON
        judge_res = None
        for attempt in range(3):
            judge_res = llm_as_a_judge(prompt, gen_text, ref_text)
            if judge_res is not None:
                break
            print(f"  [RETRY] Lỗi nhận diện câu trả lời ở mẫu thứ {completed_samples + 1}. Đang thử lại lần {attempt + 1}/3...")
            time.sleep(2.0)
            
        if judge_res is None:
            print(f"  ⚠️ Cảnh báo: Không thể nhận kết quả từ Judge cho mẫu thứ {completed_samples + 1} sau 3 lần thử.")
            print("  -> Tự động gán điểm mặc định (3/5) để tiếp tục tiến trình.")
            judge_res = {
                'context_utilization': 3,
                'trend_compliance': 3,
                'fashion_knowledge_qa': 3,
                'faithfulness': 3,
                'hallucination': 3,
                'reasoning': "Lỗi gọi API hoặc parse JSON từ Judge sau 3 lần thử."
            }
            
        # Lưu các điểm số riêng lẻ và chuẩn hóa về thang 0.0 - 1.0
        row['evaluation'] = {
            'context_utilization': round(judge_res['context_utilization'] / 5.0, 2),
            'trend_compliance': round(judge_res['trend_compliance'] / 5.0, 2),
            'fashion_knowledge_qa': round(judge_res['fashion_knowledge_qa'] / 5.0, 2),
            'faithfulness': round(judge_res['faithfulness'] / 5.0, 2),
            'hallucination': round(judge_res['hallucination'] / 5.0, 2),
            'reasoning': judge_res['reasoning']
        }
        
        completed_samples += 1
        
        # Lưu checkpoint ngay sau mỗi lần chấm điểm để đề phòng mất mạng/sập nguồn
        try:
            with open(eval_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Lỗi ghi checkpoint: {e}")
            
        # Print tiến độ (cứ 10 câu in 1 lần hoặc khi hoàn thành)
        if completed_samples % 10 == 0 or completed_samples == total_samples:
            print(f"  Đã chấm {completed_samples}/{total_samples} mẫu...")
            
    # Tính điểm trung bình của từng tiêu chí để in báo cáo so sánh chi tiết
    num_samples = len(data)
    if num_samples == 0:
        return None
        
    k_ret = sum(row['evaluation']['context_utilization'] for row in data if 'evaluation' in row) / num_samples
    c_acc = sum(row['evaluation']['trend_compliance'] for row in data if 'evaluation' in row) / num_samples
    f_qa = sum(row['evaluation']['fashion_knowledge_qa'] for row in data if 'evaluation' in row) / num_samples
    faith = sum(row['evaluation']['faithfulness'] for row in data if 'evaluation' in row) / num_samples
    hall = sum(row['evaluation']['hallucination'] for row in data if 'evaluation' in row) / num_samples
    avg_tot = (k_ret + c_acc + f_qa + faith + hall) / 5.0
    
    metrics = {
        "Size": num_samples,
        "Context Util": round(k_ret, 2),
        "Trend Comp": round(c_acc, 2),
        "Fashion QA": round(f_qa, 2),
        "Faithfulness": round(faith, 2),
        "Hallucination": round(hall, 2),
        "Average Total": round(avg_tot, 2)
    }
    return metrics

# ==========================================
# GIAI ĐOẠN CHẠY GỘP CÁC MÔ HÌNH
# ==========================================
if __name__ == "__main__":
    # Danh sách 4 mô hình đã được bạn test và lưu trong thư mục tested/
    models_to_test = [
        "qwen3vl8b-thinking-lora-p1.json",
        "qwen35-9b-bnb4-lora-p1.json",
        "qwen3vl8b-instruct-lora-p1.json", 
        "gemma4-12b-it-lora-p1.json"
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    final_report = {}
    for model_file in models_to_test:
        full_path = os.path.join(base_dir, "tested", model_file)
        results = evaluate_model_file(full_path, limit=LIMIT_SAMPLES)
        if results:
            final_report[model_file] = results
            
    # Hiển thị bảng report
    if final_report:
        report_df = pd.DataFrame(final_report).T
        print("\n=== KẾT QUẢ BENCHMARK CUỐI CÙNG ===")
        print(report_df.to_markdown())
    else:
        print("\n❌ Không có dữ liệu để đánh giá.")