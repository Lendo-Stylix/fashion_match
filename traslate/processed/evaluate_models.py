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
# - OpenAI: "gpt-4o-mini", "gpt-4o"
# - Groq: "llama-3.3-70b-versatile", "llama-3.1-8b-instant"
JUDGE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

LIMIT_SAMPLES = None

# 4. Thời gian nghỉ giữa các request (giây) để tránh bị dính Rate Limit (429)
# Với Groq Free Tier, giới hạn tối đa là 30 request/phút. Đặt 2.0 giây để đảm bảo luôn ở dưới giới hạn này.
SLEEP_DELAY = 2.0

# 5. Chế độ mô phỏng (True để chạy thử không gọi API thực tế)
MOCK_MODE = False

# ==========================================
# KHỞI TẠO CÁC CLIENT
# ==========================================

# Khởi tạo Anthropic Client
anthropic_client = anthropic.Anthropic()

# Khởi tạo OpenAI Client
openai_client = OpenAI()

# Khởi tạo Groq Client (Sử dụng OpenAI SDK tương thích)
groq_client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

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

def llm_as_a_judge(prompt, generated_text, reference_text):
    """
    Dùng Gemini-2.5-flash làm giám khảo để so sánh câu trả lời của AI 
    với câu trả lời chuẩn (Ground Truth).
    """
    if MOCK_MODE:
        # Chế độ mô phỏng điểm số (từ 3 đến 5) dựa trên hash nội dung để kiểm tra giao diện
        import random
        random.seed(abs(hash(prompt)))
        return random.randint(3, 5), "Đây là kết quả đánh giá mô phỏng ở chế độ MOCK_MODE."

    judge_prompt = f"""
    Bạn là một Giám khảo thời trang khách quan. Hãy chấm điểm câu trả lời của AI từ 1 đến 5 và giải thích lý do ngắn gọn bằng tiếng Việt.
    Hãy trả về kết quả theo định dạng chính xác như sau (thay thế phần nằm trong ngoặc vuông bằng kết quả của bạn):
    DIEM: [Một con số nguyên duy nhất từ 1 đến 5]
    LY_DO: [Giải thích ngắn gọn lý do chấm điểm bằng tiếng Việt, khoảng 1-2 câu]

    Yêu cầu của khách hàng: {prompt}
    
    Câu trả lời MẪU (Chuẩn): {reference_text}
    
    Câu trả lời CỦA AI CẦN CHẤM: {generated_text}
    
    Tiêu chí chấm (1-5):
    5 điểm: Hoàn hảo, bám sát các ý chính của câu trả lời mẫu, văn phong lịch sự, tư vấn chính xác. Chấp nhận và khuyến khích câu trả lời chi tiết, mở rộng hơn câu mẫu nếu đúng kiến thức thời trang.
    4 điểm: Trả lời đúng trọng tâm nhưng văn phong chưa được tinh tế hoặc thiếu một chút sự sâu sắc.
    3 điểm: Trả lời được nhưng thiếu ý quan trọng hoặc có một số sai sót nhỏ so với mẫu.
    2 điểm: Trả lời sai kiến thức thời trang cơ bản hoặc bị ảo giác (hallucination) một phần.
    1 điểm: Hoàn toàn lạc đề, sinh ra text rác, bịa đặt, hoặc từ chối trả lời sai cách.
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
                    max_output_tokens=300,
                    safety_settings=safety_settings
                )
            )
            response_text = response.text
        elif JUDGE_PROVIDER == "anthropic":
            message = anthropic_client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=300,
                temperature=0.0,
                system="Bạn là một Giám khảo thời trang khách quan, hãy chấm điểm và giải thích ngắn gọn.",
                messages=[{"role": "user", "content": judge_prompt}]
            )
            response_text = message.content[0].text
        elif JUDGE_PROVIDER == "openai":
            response = openai_client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=300
            )
            response_text = response.choices[0].message.content
        elif JUDGE_PROVIDER == "groq":
            response = groq_client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=300
            )
            response_text = response.choices[0].message.content
        else:
            raise ValueError(f"Không nhận diện được JUDGE_PROVIDER: {JUDGE_PROVIDER}")
            
        # Trích xuất số điểm từ câu trả lời của Judge
        if response_text is None:
            print("Cảnh báo: Câu trả lời bị chặn bởi bộ lọc an toàn (Safety Filter) hoặc không có nội dung.")
            return 1, "Bị chặn bởi bộ lọc an toàn."
            
        # Loại bỏ tag <think>...</think> nếu có (đặc biệt đối với các model suy nghĩ của Qwen/DeepSeek)
        clean_text = response_text
        if "<think>" in clean_text and "</think>" in clean_text:
            clean_text = re.sub(r'<think>.*?</think>', '', clean_text, flags=re.DOTALL)
            
        score_match = re.search(r'DIEM:\s*(\d+)', clean_text, re.IGNORECASE)
        reason_match = re.search(r'LY_DO:\s*(.*)', clean_text, re.DOTALL | re.IGNORECASE)
        
        if not score_match:
            # Fallback nếu không đúng format
            num_match = re.search(r'\d+', clean_text)
            score = int(num_match.group()) if num_match else 1
            reason = clean_text.strip()
        else:
            score = int(score_match.group(1))
            reason = reason_match.group(1).strip() if reason_match else ""
            
        # Đảm bảo điểm nằm trong khoảng 1-5
        return max(1, min(5, score)), reason
    except Exception as e:
        print(f"❌ Lỗi gọi API ({JUDGE_PROVIDER}): {e}")
        return None, None # Trả về None để báo hiệu lỗi API hệ thống (hết token, lỗi key, mất mạng)

def evaluate_model_file(filepath, limit=None):
    """Chạy đánh giá cho 1 file kết quả, hỗ trợ resume từ checkpoint."""
    # Xác định đường dẫn file checkpoint
    eval_filepath = filepath.replace(".json", "_eval.json")
    
    # Đọc dữ liệu từ checkpoint cũ nếu có, nếu không thì đọc file gốc
    data = []
    if os.path.exists(eval_filepath):
        try:
            with open(eval_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"Phát hiện checkpoint cũ tại: {eval_filepath}")
        except Exception as e:
            print(f"Lỗi đọc file checkpoint {eval_filepath}: {e}. Đang tải lại file gốc...")
            
    if not data:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Bỏ qua: Không tìm thấy file {filepath}")
            return None

    if limit is not None:
        data = data[:limit]
        
    total_samples = len(data)
    if total_samples == 0:
        return None

    total_judge_score = 0
    completed_samples = 0
    
    # Đếm số lượng mẫu đã được chấm điểm trước đó
    for row in data:
        if 'judge_score' in row:
            total_judge_score += row['judge_score']
            completed_samples += 1
            
    if completed_samples > 0:
        print(f"  -> Tiếp tục chạy: Đã chấm {completed_samples}/{total_samples} mẫu trước đó.")

    for i, row in enumerate(data):
        # Bỏ qua nếu đã được chấm điểm
        if 'judge_score' in row:
            continue
            
        prompt = row.get('prompt', '')
        gen_text = row.get('generated_text', '')
        ref_text = row.get('reference_text', '') 
        
        # Thêm khoảng nghỉ để tránh Spam API quá nhanh gây Rate Limit (bỏ qua nếu chạy Mock)
        if not MOCK_MODE:
            time.sleep(SLEEP_DELAY)
        
        judge_score, judge_reason = llm_as_a_judge(prompt, gen_text, ref_text)
        if judge_score is None:
            print(f"\n❌ Quá trình đánh giá bị dừng ở mẫu thứ {completed_samples + 1} do lỗi API hệ thống (hết token, lỗi key hoặc mất mạng).")
            print("Tiến trình đã được lưu an toàn đến mẫu trước đó. Điểm của mẫu lỗi hiện tại CHƯA bị lưu đè.")
            print("👉 Vui lòng kiểm tra lại API Key hoặc hạn mức, sau đó chạy lại lệnh để tiếp tục từ mẫu này.")
            import sys
            sys.exit(1)
            
        row['judge_score'] = judge_score
        row['judge_reasoning'] = judge_reason
        total_judge_score += judge_score
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
            
    metrics = {
        "Total_Samples_Evaluated": total_samples,
        "Average_Judge_Score_1_to_5": round(total_judge_score / total_samples, 2)
    }
    return metrics

# ==========================================
# GIAI ĐOẠN CHẠY GỘP CÁC MÔ HÌNH
# ==========================================
if __name__ == "__main__":
    # ĐIỀN ĐÚNG TÊN FILE MÀ BẠN ĐÃ LƯU TRONG QUÁ TRÌNH INFERENCE
    models_to_test = [
        "t1_qwen3_vl_8b_thinking_outputs_part1.json",
        "t2_qwen35_9b_outputs_part1.json",
        "t3_qwen3_vl_8b_instruct_outputs_part1.json", 
        "t4_gemma_outputs_part1.json"
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    final_report = {}
    for model_file in models_to_test:
        full_path = os.path.join(base_dir, model_file)
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