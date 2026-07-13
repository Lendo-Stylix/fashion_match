import os
import json
import re
import time
import argparse
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
import anthropic

# Tự động tải API key từ file .env
load_dotenv()

# Cấu hình API Keys dự phòng cho Groq
groq_keys = os.environ.get("GROQ_API_KEY", "").split(",")
groq_keys = [k.strip() for k in groq_keys if k.strip()]

class RotatingGroqClient:
    def __init__(self, keys):
        self.keys = keys
        self.current_idx = 0
        
    def create_chat_completion(self, model, messages, temperature=0.0, max_tokens=1024):
        if not self.keys:
            raise ValueError("Không tìm thấy GROQ_API_KEY trong file .env hoặc danh sách dự phòng")
            
        attempts = len(self.keys)
        
        # 1. Thử gọi model chính trước
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
                    print(f"\n[SWAP KEY] Groq Key #{client_idx + 1} bị giới hạn tần suất/hạn mức (429). Đang chuyển key...")
                    continue
                else:
                    raise e
                    
        # 2. Nếu model chính hết hạn ngạch trên toàn bộ key, chuyển sang model dự phòng 1: llama-3.3-70b-versatile
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
                    print(f"\n[SWAP KEY fallback 1] Groq Key #{client_idx + 1} bị giới hạn. Đang chuyển key...")
                    continue
                else:
                    raise e

        # 3. Model dự phòng 2: qwen/qwen3-32b
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
                    print(f"\n[SWAP KEY fallback 2] Groq Key #{client_idx + 1} bị giới hạn. Đang chuyển key...")
                    continue
                else:
                    raise e
                    
        # 4. Model dự phòng 3: llama-3.1-8b-instant
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
                    print(f"\n[SWAP KEY fallback 3] Groq Key #{client_idx + 1} bị giới hạn. Đang chuyển key...")
                    continue
                else:
                    raise e
                    
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

# Khởi tạo các API client xoay vòng
groq_client = RotatingGroqClient(groq_keys)
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
        for try_num in range(5):
            for _ in range(attempts):
                key = self.keys[self.current_idx]
                client_idx = self.current_idx
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(model=model, contents=contents, **kwargs)
                    return response
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower():
                        print(f"Gemini Key #{client_idx + 1} bị giới hạn (429). Đang chuyển key...")
                    else:
                        print(f"Lỗi với Gemini Key #{client_idx + 1}: {e}. Đang chuyển key...")
            
            sleep_time = (try_num + 1) * 5
            print(f"Tất cả các key đều bận/hết hạn mức. Chờ {sleep_time} giây trước khi thử lại...")
            time.sleep(sleep_time)
            
        raise RuntimeError("Tất cả các Gemini API key đều lỗi hoặc quá hạn mức.")

gemini_client = RotatingGeminiClient(gemini_keys)

def extract_json(text):
    """Trích xuất và parse JSON từ văn bản phản hồi của LLM."""
    if not text:
        return None
    if "<think>" in text:
        if "</think>" in text:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        else:
            text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
            
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
            
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

def llm_as_a_judge(prompt, generated_text, reference_text, provider, model, mock_mode=False):
    """Dùng LLM làm giám khảo đánh giá câu trả lời trên 5 tiêu chí thời trang cốt lõi."""
    if mock_mode:
        import random
        random.seed(abs(hash(prompt)))
        return {
            'context_utilization': random.randint(3, 5),
            'trend_compliance': random.randint(3, 5),
            'fashion_knowledge_qa': random.randint(3, 5),
            'faithfulness': random.randint(3, 5),
            'hallucination': random.randint(3, 5),
            'reasoning': "Đây là kết quả đánh giá mô phỏng ở chế độ Mock Mode."
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
      \"context_utilization\": [số nguyên từ 1 đến 5],
      \"trend_compliance\": [số nguyên từ 1 đến 5],
      \"fashion_knowledge_qa\": [số nguyên từ 1 đến 5],
      \"faithfulness\": [số nguyên từ 1 đến 5],
      \"hallucination\": [số nguyên từ 1 đến 5],
      \"reasoning\": \"[Giải thích ngắn gọn lý do chấm điểm bằng tiếng Việt, khoảng 2-3 câu]\"
    }}

    Dữ liệu đánh giá:
    - Yêu cầu của khách hàng: {prompt}
    - Câu trả lời MẪU (Chuẩn): {reference_text}
    - Câu trả lời CỦA AI CẦN CHẤM: {generated_text}
    """
    
    safety_settings = [
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]
    
    try:
        if provider == "gemini":
            response = gemini_client.generate_content(
                model=model,
                contents=judge_prompt,
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=500, safety_settings=safety_settings)
            )
            response_text = response.text
        elif provider == "anthropic":
            client = anthropic.Anthropic()
            message = client.messages.create(
                model=model,
                max_tokens=500,
                temperature=0.0,
                system="Bạn là một Giám khảo thời trang khách quan, hãy trả về kết quả dưới dạng JSON theo đúng cấu trúc yêu cầu.",
                messages=[{"role": "user", "content": judge_prompt}]
            )
            response_text = message.content[0].text
        elif provider == "openai":
            client = OpenAI()
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=500
            )
            response_text = response.choices[0].message.content
        elif provider == "groq":
            response = groq_client.create_chat_completion(
                model=model,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=1024
            )
            response_text = response.choices[0].message.content
        else:
            raise ValueError(f"Không nhận diện được JUDGE_PROVIDER: {provider}")
            
        if response_text is None:
            print("Cảnh báo: Câu trả lời bị chặn bởi bộ lọc an toàn hoặc không có nội dung.")
            return None
            
        parsed_result = extract_json(response_text)
        if not parsed_result:
            return None
            
        for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']:
            if k not in parsed_result:
                parsed_result[k] = 3
            else:
                try:
                    parsed_result[k] = max(1, min(5, int(parsed_result[k])))
                except ValueError:
                    parsed_result[k] = 3
                    
        if 'reasoning' not in parsed_result:
            parsed_result['reasoning'] = "Không có lý do chi tiết."
            
        return parsed_result
    except Exception as e:
        print(f"❌ Lỗi gọi API ({provider}): {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Evaluate a Single Model Output File using LLM-as-a-judge")
    parser.add_argument("--input", type=str, required=True, help="Đường dẫn đến file JSON kết quả cần đánh giá (ví dụ: gemma4-12b-it-lora-p1-outputs.json)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mẫu chấm điểm để test nhanh")
    parser.add_argument("--provider", type=str, default="groq", choices=["groq", "gemini", "openai", "anthropic"], help="Nhà cung cấp API LLM làm giám khảo")
    parser.add_argument("--model", type=str, default="meta-llama/llama-4-scout-17b-16e-instruct", help="Model làm giám khảo")
    parser.add_argument("--delay", type=float, default=1.5, help="Thời gian nghỉ (giây) giữa các request để tránh rate limit")
    parser.add_argument("--mock", action="store_true", help="Chạy ở chế độ mô phỏng (Mock Mode) không gọi API")
    
    args = parser.parse_args()
    
    # Chuẩn hóa đường dẫn tuyệt đối
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = args.input
    
    # Danh sách các đường dẫn tìm kiếm khả thi
    possible_paths = []
    if os.path.isabs(input_path):
        possible_paths.append(input_path)
    else:
        filename = os.path.basename(input_path)
        possible_paths.append(os.path.abspath(os.path.join(base_dir, input_path)))
        possible_paths.append(os.path.abspath(os.path.join(base_dir, "tested", filename)))
        possible_paths.append(os.path.abspath(os.path.join(base_dir, "evaluated", filename)))
        # Quay lại thư mục cha (processed)
        possible_paths.append(os.path.abspath(os.path.join(base_dir, "..", filename)))
        
    # Tìm tệp thực sự tồn tại đầu tiên
    found_path = None
    for p in possible_paths:
        if os.path.exists(p):
            found_path = p
            break
            
    if found_path is not None:
        input_path = found_path
    else:
        print(f"❌ Lỗi: Không tìm thấy tệp đầu vào tại các đường dẫn: {[p for p in possible_paths]}")
        return
            
    eval_filepath = input_path.replace(".json", "_eval.json")
    if "tested" in eval_filepath:
        eval_filepath = eval_filepath.replace("tested", "evaluated")
    print(f"🚀 Khởi chạy quá trình đánh giá cho file: {os.path.basename(input_path)}")
    print(f"📝 Kết quả chấm điểm sẽ được lưu tại: {eval_filepath}")
    print(f"🤖 Giám khảo: Provider '{args.provider.upper()}' | Model '{args.model}'")
    if args.mock:
        print("⚠️ Chế độ: MOCK MODE (Mô phỏng chấm điểm ngẫu nhiên)")
        
    # 1. Đọc checkpoint cũ hoặc tải tệp mới
    data = []
    if os.path.exists(eval_filepath):
        try:
            with open(eval_filepath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            print(f"🔄 Phát hiện checkpoint cũ. Đã chấm được {len([r for r in loaded_data if 'evaluation' in r])}/{len(loaded_data)} mẫu.")
            
            # Chuẩn hóa nếu cấu trúc cũ
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
            print(f"Lỗi đọc checkpoint: {e}. Tiến hành tải lại file gốc...")
            
    if not data:
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            for i, row in enumerate(raw_data):
                data.append({
                    "id": row.get("id") or f"Q-{i+1:03d}",
                    "question": row.get("question") or row.get("prompt") or "",
                    "ground_truth": row.get("ground_truth") or row.get("reference_text") or "",
                    "contexts": row.get("contexts") or [],
                    "metadata": row.get("metadata") or {"category": row.get("category", "unknown")},
                    "retrieved_contexts": row.get("retrieved_contexts") or [],
                    "answer": row.get("answer") or row.get("generated_text") or ""
                })
        except Exception as e:
            print(f"❌ Lỗi khi đọc file đầu vào: {e}")
            return
            
    if args.limit is not None:
        data = data[:args.limit]
        
    total_samples = len(data)
    if total_samples == 0:
        print("❌ Không có dữ liệu để đánh giá.")
        return
        
    completed_samples = len([r for r in data if 'evaluation' in r])
    
    # 2. Vòng lặp chính chấm điểm từng câu
    print("\n✍️ Bắt đầu chấm điểm...")
    for idx, row in enumerate(data):
        has_eval = 'evaluation' in row and all(k in row['evaluation'] for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination'])
        if has_eval:
            continue
            
        prompt = row.get('question', '')
        gen_text = row.get('answer', '')
        ref_text = row.get('ground_truth', '')
        
        if not args.mock:
            time.sleep(args.delay)
            
        judge_res = llm_as_a_judge(prompt, gen_text, ref_text, args.provider, args.model, args.mock)
        if judge_res is None:
            print(f"\n❌ Dừng đột ngột tại mẫu thứ {completed_samples + 1} do lỗi API.")
            print("👉 Tiến độ đã được lưu an toàn. Vui lòng chạy lại lệnh để tiếp tục.")
            with open(eval_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
            
        row['evaluation'] = {
            'context_utilization': round(judge_res['context_utilization'] / 5.0, 2),
            'trend_compliance': round(judge_res['trend_compliance'] / 5.0, 2),
            'fashion_knowledge_qa': round(judge_res['fashion_knowledge_qa'] / 5.0, 2),
            'faithfulness': round(judge_res['faithfulness'] / 5.0, 2),
            'hallucination': round(judge_res['hallucination'] / 5.0, 2),
            'reasoning': judge_res['reasoning']
        }
        
        completed_samples += 1
        
        # Lưu checkpoint ngay lập tức
        with open(eval_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        if completed_samples % 5 == 0 or completed_samples == total_samples:
            print(f"  [TIẾN ĐỘ] Đã chấm xong {completed_samples}/{total_samples} mẫu...")
            
    # 3. Tính toán và hiển thị báo cáo tổng kết
    metrics = {
        "Context_Utilization": [],
        "Trend_Compliance": [],
        "Fashion_Knowledge_QA": [],
        "Faithfulness": [],
        "Hallucination": [],
        "Average_Total": []
    }
    
    for row in data:
        if 'evaluation' in row:
            eval_data = row['evaluation']
            metrics["Context_Utilization"].append(eval_data["context_utilization"])
            metrics["Trend_Compliance"].append(eval_data["trend_compliance"])
            metrics["Fashion_Knowledge_QA"].append(eval_data["fashion_knowledge_qa"])
            metrics["Faithfulness"].append(eval_data["faithfulness"])
            metrics["Hallucination"].append(eval_data["hallucination"])
            
            avg_score = sum(eval_data[k] for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']) / 5.0
            metrics["Average_Total"].append(avg_score)
            
    summary_report = {
        "Chỉ số đánh giá": [
            "Context Utilization (Khai thác ngữ cảnh)",
            "Trend Compliance (Tuân thủ phong cách & xu hướng)",
            "Fashion Knowledge QA (Hỏi đáp kiến thức)",
            "Faithfulness (Trung thực với ngữ cảnh)",
            "Hallucination (Chống ảo giác)",
            "Average Score (Điểm trung bình cộng)"
        ],
        "Điểm trung bình (Thang 0 - 1.0)": [
            round(sum(metrics["Context_Utilization"]) / len(metrics["Context_Utilization"]), 2) if metrics["Context_Utilization"] else 0,
            round(sum(metrics["Trend_Compliance"]) / len(metrics["Trend_Compliance"]), 2) if metrics["Trend_Compliance"] else 0,
            round(sum(metrics["Fashion_Knowledge_QA"]) / len(metrics["Fashion_Knowledge_QA"]), 2) if metrics["Fashion_Knowledge_QA"] else 0,
            round(sum(metrics["Faithfulness"]) / len(metrics["Faithfulness"]), 2) if metrics["Faithfulness"] else 0,
            round(sum(metrics["Hallucination"]) / len(metrics["Hallucination"]), 2) if metrics["Hallucination"] else 0,
            round(sum(metrics["Average_Total"]) / len(metrics["Average_Total"]), 2) if metrics["Average_Total"] else 0
        ]
    }
    
    report_df = pd.DataFrame(summary_report)
    print(f"\n==========================================")
    print(f"📊 KẾT QUẢ BENCHMARK: {os.path.basename(input_path)}")
    print(f"==========================================")
    print(report_df.to_markdown(index=False))
    print(f"==========================================")
    
if __name__ == "__main__":
    main()
