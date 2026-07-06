import os
import json
import argparse
from dotenv import load_dotenv
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

# Load environment variables from .env
load_dotenv()

class ConfigParser:
    @staticmethod
    def load_categories(filepath: str) -> dict:
        """
        Đọc file sourcelink.txt và trích xuất thành danh mục phẳng:
        { "tên_danh_mục": ["url1", "url2"] }
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Không tìm thấy file cấu hình: {filepath}")
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Sửa lỗi URL không bọc trong dấu ngoặc kép và thiếu dấu phẩy trong file sourcelink.txt
            import re
            content = re.sub(r'(https?://[^\s,\}\]]+)', r'"\1",', content)
            content = re.sub(r',\s*([\]\}])', r'\1', content)
            
            config = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Lỗi cú pháp JSON trong file {filepath}: {e}")
            
        category_map = {}
        for group_key, group_val in config.items():
            if isinstance(group_val, dict):
                for cat_key, cat_val in group_val.items():
                    if isinstance(cat_val, dict) and "urls" in cat_val:
                        category_map[cat_key] = cat_val["urls"]
                        
        return category_map


class ConversationLoader:
    @staticmethod
    def load_conversations(filepath: str) -> list:
        """
        Đọc và chuẩn hóa dữ liệu hội thoại từ file JSON.
        Hỗ trợ hai định dạng:
        1. Mảng các object chứa {"prompt", "generated_text"}
        2. Mảng các object chứa {"messages": [{"role": "user", "content": "..."}, {"role": "model", "content": "..."}]}
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Không tìm thấy file hội thoại: {filepath}")
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Lỗi cú pháp JSON trong file {filepath}: {e}")
            
        if not isinstance(data, list):
            raise ValueError("Dữ liệu hội thoại phải là một JSON array (dạng list).")
            
        normalized_data = []
        for idx, item in enumerate(data):
            prompt = ""
            gen_text = ""
            
            # Định dạng 1: trực tiếp prompt và generated_text
            if "prompt" in item and "generated_text" in item:
                prompt = item["prompt"]
                gen_text = item["generated_text"]
            # Định dạng 2: messages list
            elif "messages" in item and isinstance(item["messages"], list):
                for msg in item["messages"]:
                    if msg.get("role") == "user":
                        prompt = msg.get("content", "")
                    elif msg.get("role") in ["model", "assistant"]:
                        gen_text = msg.get("content", "")
                        
            if not prompt:
                continue
                
            normalized_data.append({
                "original_item": item,
                "prompt": prompt,
                "generated_text": gen_text
            })
            
        return normalized_data


class LangChainClassifier:
    def __init__(self, provider: str = "groq", model_name: str = None, api_key: str = None, base_url: str = None):
        """
        Khởi tạo LLM Classifier tương thích với cấu hình người dùng.
        """
        self.provider = provider.lower()
        
        # Thiết lập mặc định dựa trên nhà cung cấp
        if self.provider == "groq":
            self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
            self.base_url = base_url or "https://api.groq.com/openai/v1"
            self.model_name = model_name or "llama-3.3-70b-versatile"
        elif self.provider == "ollama":
            self.api_key = api_key or "ollama"
            self.base_url = base_url or "http://localhost:11434/v1"
            self.model_name = model_name or "llama3"
        elif self.provider == "openai":
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            self.base_url = base_url or "https://api.openai.com/v1"
            self.model_name = model_name or "gpt-4o-mini"
        else:
            raise ValueError(f"Không hỗ trợ provider: {provider}. Chọn một trong các loại: groq, ollama, openai")
            
        if not self.api_key and self.provider != "ollama":
            raise ValueError(f"Không tìm thấy API Key cho nhà cung cấp {provider}. Vui lòng kiểm tra lại cấu hình hoặc file .env")
            
        # Khởi tạo OpenAI client
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        
    def _call_llm(self, prompt_value) -> str:
        """Hàm callback để LangChain Runnable gọi LLM."""
        messages = prompt_value.to_messages()
        formatted_messages = []
        for msg in messages:
            role = "user"
            if msg.type == "ai":
                role = "assistant"
            elif msg.type == "system":
                role = "system"
            formatted_messages.append({"role": role, "content": msg.content})
            
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
                temperature=0.0
            )
            return completion.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"Lỗi gọi API {self.provider.upper()}: {e}")

    def build_chain(self, categories: list):
        """Xây dựng LangChain LCEL Chain cho phân loại."""
        categories_str = ", ".join(categories)
        
        # Prompt template phân loại
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Bạn là một RAG Router phân tích câu hỏi thời trang của người dùng."),
            ("user", f"""Nhiệm vụ của bạn là đọc câu hỏi của người dùng dưới đây và phân loại nó vào đúng một trong các danh mục hợp lệ sau:
[{categories_str}]

Nếu câu hỏi không khớp rõ ràng với bất kỳ danh mục nào ở trên, hãy trả về "unknown".

QUY TẮC BẮT BUỘC:
1. CHỈ trả về duy nhất tên danh mục dưới dạng chữ thường (ví dụ: "office_wear") hoặc "unknown".
2. TUYỆT ĐỐI KHÔNG thêm bất kỳ giải thích, lập luận, hoặc từ ngữ nào khác.

Câu hỏi của người dùng:
"{{user_question}}"

Danh mục phù hợp nhất:""")
        ])
        
        # LCEL Chain sử dụng RunnableLambda làm model wrapper
        model_runnable = RunnableLambda(self._call_llm)
        
        # Parser đơn giản để làm sạch kết quả
        def clean_output(text: str) -> str:
            val = text.strip().strip('"').strip("'").lower()
            return val if val in categories else "unknown"
            
        parser_runnable = RunnableLambda(clean_output)
        
        self.chain = prompt | model_runnable | parser_runnable
        return self.chain

    def classify(self, user_question: str) -> str:
        """Thực thi chain để phân loại câu hỏi."""
        if not hasattr(self, 'chain'):
            raise RuntimeError("Vui lòng gọi build_chain trước khi thực hiện classify.")
        try:
            return self.chain.invoke({"user_question": user_question})
        except Exception as e:
            print(f"⚠️ Cảnh báo: Lỗi khi chạy chain phân loại cho câu hỏi: '{user_question[:30]}...'. Chi tiết: {e}")
            return "unknown"


class MappingEngine:
    @staticmethod
    def attach_sources(item: dict, category: str, category_map: dict) -> dict:
        """
        Gắn link nguồn tham khảo tương ứng vào generated_text của item.
        """
        urls = category_map.get(category, [])
        
        # Nếu có danh mục hợp lệ và danh sách link không rỗng
        if category != "unknown" and urls:
            source_lines = [f"- {url}" for url in urls]
            source_text = "\n\nNguồn tham khảo:\n" + "\n".join(source_lines)
        else:
            source_text = "\n\nNguồn tham khảo:\n- Kiến thức thời trang tổng hợp (Nguồn Internet)"
            
        # Nối nguồn vào cuối câu trả lời
        original_text = item["generated_text"]
        item["generated_text"] = f"{original_text}{source_text}"
        item["assigned_category"] = category
        return item


def main():
    parser = argparse.ArgumentParser(description="RAG Categorization and URL Mapping Pipeline")
    parser.add_argument("--sourcelink", type=str, default="processed/sourcelink.txt", help="Đường dẫn đến file sourcelink.txt")
    parser.add_argument("--input", type=str, required=True, help="Đường dẫn đến file JSON đầu vào (ví dụ: test_part1_200.json)")
    parser.add_argument("--output", type=str, default="processed/pipeline_output.json", help="Đường dẫn đến file JSON đầu ra")
    parser.add_argument("--provider", type=str, default="groq", choices=["groq", "ollama", "openai"], help="Nhà cung cấp API LLM")
    parser.add_argument("--model", type=str, default=None, help="Tên model sử dụng để phân loại")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mẫu xử lý để test nhanh")
    
    args = parser.parse_args()
    
    print("🚀 Khởi chạy RAG URL Mapping Pipeline...")
    
    # Bước 1: Parse Data
    try:
        category_map = ConfigParser.load_categories(args.sourcelink)
        categories = list(category_map.keys())
        print(f"✅ Đã tải file cấu hình danh mục. Tìm thấy {len(categories)} danh mục hợp lệ.")
    except Exception as e:
        print(f"❌ Lỗi khi đọc file cấu hình: {e}")
        return
        
    try:
        conversations = ConversationLoader.load_conversations(args.input)
        if args.limit:
            conversations = conversations[:args.limit]
        print(f"✅ Đã tải và chuẩn hóa {len(conversations)} mẫu hội thoại từ file đầu vào.")
    except Exception as e:
        print(f"❌ Lỗi khi đọc file hội thoại đầu vào: {e}")
        return
        
    # Bước 2: Khởi tạo LLM Router / Classifier
    try:
        classifier = LangChainClassifier(provider=args.provider, model_name=args.model)
        classifier.build_chain(categories)
        print(f"✅ Đã khởi tạo LangChain Classifier sử dụng provider '{args.provider}' và model '{classifier.model_name}'.")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo LLM: {e}")
        return
        
    # Bước 3: Phân loại và Mapping nguồn tham khảo
    updated_results = []
    print("\n--- Bắt đầu xử lý hội thoại ---")
    for idx, conv in enumerate(conversations):
        prompt = conv["prompt"]
        print(f"[{idx+1}/{len(conversations)}] Phân loại câu hỏi: '{prompt[:60]}...'")
        
        # Gọi LLM để phân loại
        assigned_category = classifier.classify(prompt)
        print(f"  -> Danh mục được gán: {assigned_category}")
        
        # Gán nguồn vào generated_text
        mapped_conv = MappingEngine.attach_sources(conv, assigned_category, category_map)
        
        # Giữ lại cấu trúc nguyên bản của object đầu vào nhưng cập nhật generated_text
        original_item = mapped_conv["original_item"]
        
        # Cập nhật generated_text trong cấu trúc gốc
        if "generated_text" in original_item:
            original_item["generated_text"] = mapped_conv["generated_text"]
        elif "messages" in original_item and isinstance(original_item["messages"], list):
            for msg in original_item["messages"]:
                if msg.get("role") in ["model", "assistant"]:
                    msg["content"] = mapped_conv["generated_text"]
                    
        # Thêm meta thông tin phân loại để người dùng dễ tra cứu
        original_item["assigned_category"] = assigned_category
        
        updated_results.append(original_item)
        
    # Bước 4: Xuất dữ liệu đầu ra
    try:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(updated_results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Đã lưu kết quả thành công vào: {args.output}")
    except Exception as e:
        print(f"❌ Lỗi khi ghi kết quả đầu ra: {e}")

if __name__ == "__main__":
    main()
