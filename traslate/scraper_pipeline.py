import os
import re
import json
import time
import requests
import argparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
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


class WebScraper:
    @staticmethod
    def scrape_url(url: str, timeout: int = 15) -> str:
        """Tải HTML và làm sạch văn bản từ một URL."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Tự động nhận diện bảng mã phù hợp
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
                
            return WebScraper.clean_html(response.text)
        except Exception as e:
            print(f"⚠️ Lỗi cào URL: {url}. Chi tiết: {e}")
            return ""

    @staticmethod
    def clean_html(html_content: str) -> str:
        """Làm sạch HTML: loại bỏ thẻ thừa, giữ lại nội dung chính."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Danh sách thẻ thừa cần loại bỏ
        extraneous = ["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]
        for element in soup(extraneous):
            element.decompose()
            
        # Thử tìm thẻ bài viết chính để tăng độ chính xác
        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n")
        else:
            main_content = (
                soup.find(id=re.compile(r"main|content|body", re.I)) or 
                soup.find(class_=re.compile(r"main|content|body", re.I))
            )
            if main_content:
                text = main_content.get_text(separator="\n")
            else:
                text = soup.get_text(separator="\n")
                
        # Làm sạch khoảng trắng và các dòng trống
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        return clean_text


class LLMSynthesizer:
    def __init__(self, provider: str = "groq", model_name: str = None, api_key: str = None, base_url: str = None):
        self.provider = provider.lower()
        self.sleep_delay = 1.5  # Khoảng cách nghỉ để tránh Rate Limit (429)
        
        if self.provider == "groq":
            self.keys = [
                api_key or os.environ.get("GROQ_API_KEY", ""),
                "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"
            ]
            self.keys = [k.strip() for k in self.keys if k and k.strip()]
            self.current_idx = 0
            self.model_name = model_name or "llama-3.3-70b-versatile"
            self.base_url = base_url or "https://api.groq.com/openai/v1"
        elif self.provider == "ollama":
            self.api_key = api_key or "ollama"
            self.base_url = base_url or "http://localhost:11434/v1"
            self.model_name = model_name or "llama3"
        elif self.provider == "openai":
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            self.base_url = base_url or "https://api.openai.com/v1"
            self.model_name = model_name or "gpt-4o-mini"
        else:
            raise ValueError(f"Không hỗ trợ provider: {provider}")

    def _call_llm(self, prompt_value) -> str:
        messages = prompt_value.to_messages()
        formatted_messages = []
        for msg in messages:
            role = "user"
            if msg.type == "ai":
                role = "assistant"
            elif msg.type == "system":
                role = "system"
            formatted_messages.append({"role": role, "content": msg.content})
            
        if self.provider == "groq":
            # Đa mô hình dự phòng nâng cao cho Groq
            models_to_try = [self.model_name, "qwen/qwen3-32b", "llama-3.1-8b-instant"]
            models_to_try = list(dict.fromkeys([m for m in models_to_try if m]))
            
            for model in models_to_try:
                attempts = len(self.keys)
                for _ in range(attempts):
                    key = self.keys[self.current_idx]
                    client_idx = self.current_idx
                    self.current_idx = (self.current_idx + 1) % len(self.keys)
                    
                    try:
                        time.sleep(self.sleep_delay)
                        client = OpenAI(api_key=key, base_url=self.base_url)
                        completion = client.chat.completions.create(
                            model=model,
                            messages=formatted_messages,
                            temperature=0.0
                        )
                        return completion.choices[0].message.content
                    except Exception as e:
                        err_msg = str(e)
                        if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                            print(f"\n[SWAP KEY] Groq Key #{client_idx + 1} bị giới hạn (429) cho model {model}. Đang chuyển key...")
                            continue
                        else:
                            raise e
            raise RuntimeError("Toàn bộ API keys và mô hình dự phòng đều bị giới hạn hạn mức (429) trên Groq.")
        else:
            time.sleep(self.sleep_delay)
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
                temperature=0.0
            )
            return completion.choices[0].message.content

    def summarize_text(self, text: str, url: str) -> str:
        """Tóm tắt ý chính của từng URL riêng biệt (Map Step)."""
        if not text:
            return ""
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Bạn là một trợ lý phân tích nội dung thời trang chuyên nghiệp."),
            ("user", """Hãy đọc bài viết thời trang sau từ nguồn URL: {url}
Hãy tóm tắt ngắn gọn các ý chính cốt lõi về:
1. Các quy tắc chọn trang phục/phối đồ.
2. Các món đồ thời trang chủ đạo được khuyên dùng.
3. Các xu hướng lỗi thời hoặc lỗi phối đồ cần tránh.
4. Mọi điểm mâu thuẫn hay khác biệt góc nhìn (nếu có).

Bài viết:
{article_text}

Tóm tắt ý chính bằng Tiếng Việt:""")
        ])
        
        chain = prompt | RunnableLambda(self._call_llm)
        
        # Cắt ngắn văn bản thô tránh tràn ngữ cảnh của mô hình
        truncated_text = text[:15000]
        
        try:
            return chain.invoke({"url": url, "article_text": truncated_text})
        except Exception as e:
            print(f"⚠️ Cảnh báo: Lỗi khi tóm tắt URL {url}: {e}")
            return f"[Lỗi tóm tắt nguồn {url}]"

    def synthesize_graph(self, context_text: str, category_name: str) -> dict:
        """Tổng hợp toàn bộ ngữ cảnh thành Đồ thị Tri thức cấu trúc JSON (Reduce Step)."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Bạn là một Chuyên gia phân tích dữ liệu và AI Architect thời trang."),
            ("user", """Dưới đây là nội dung thông tin được tổng hợp từ các bài viết thời trang về danh mục: "{category_name}"

Ngữ cảnh:
{context_text}

Nhiệm vụ của bạn là đúc kết ngữ cảnh trên thành một Đồ thị Tri thức có cấu trúc dưới định dạng JSON duy nhất.
JSON của bạn phải chứa chính xác các trường sau:
1. "consensus_rules": Danh sách (mảng các chuỗi) các quy tắc phong cách chung, cốt lõi mà các nguồn đều đồng thuận.
2. "conflicts_to_note": Danh sách (mảng các chuỗi) các điểm mâu thuẫn, khác biệt hoặc ranh giới góc nhìn giữa các nguồn (ví dụ: nguồn này cho phép quần jeans đi làm, nguồn kia cấm). Nếu không có, ghi mảng rỗng.
3. "key_items": Danh sách (mảng các chuỗi) các món đồ chủ đạo và kinh điển được nhắc tới cho phong cách này.
4. "outdated_trends_to_avoid": Danh sách (mảng các chuỗi) các xu hướng lỗi thời hoặc lỗi phối đồ cần tránh.

QUY TẮC BẮT BUỘC:
1. Chỉ trả về duy nhất chuỗi JSON hợp lệ khớp với cấu trúc được yêu cầu. Không thêm bất kỳ văn bản giải thích ngoài lề.
2. Không bọc JSON trong tag markdown ```json ... ```, hãy trả về trực tiếp chuỗi JSON text bắt đầu bằng {{ và kết thúc bằng }}.
3. Tất cả các giá trị chuỗi và giải thích phải bằng Tiếng Việt.

JSON Kết quả:""")
        ])
        
        chain = prompt | RunnableLambda(self._call_llm)
        
        try:
            raw_output = chain.invoke({"category_name": category_name, "context_text": context_text})
            return self._clean_and_parse_json(raw_output)
        except Exception as e:
            print(f"⚠️ Cảnh báo: Lỗi khi đúc kết tri thức cho danh mục {category_name}: {e}")
            return self._get_fallback_graph()

    def _clean_and_parse_json(self, text: str) -> dict:
        """Làm sạch và chuyển đổi kết quả LLM về JSON dict."""
        cleaned = text.strip()
        match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        json_str = match.group(1) if match else cleaned
        
        try:
            data = json.loads(json_str)
            required_fields = ["consensus_rules", "conflicts_to_note", "key_items", "outdated_trends_to_avoid"]
            for field in required_fields:
                if field not in data or not isinstance(data[field], list):
                    data[field] = []
            return data
        except Exception as e:
            print(f"⚠️ Lỗi parse JSON từ LLM output: {e}. Output gốc: {text[:200]}...")
            return self._get_fallback_graph()

    def _get_fallback_graph(self) -> dict:
        return {
            "consensus_rules": ["Tìm hiểu kỹ quy chuẩn ăn mặc của từng dịp cụ thể."],
            "conflicts_to_note": [],
            "key_items": ["Trang phục cơ bản lịch sự."],
            "outdated_trends_to_avoid": ["Tránh phối đồ quá lòe loẹt hoặc không phù hợp thời tiết."]
        }


class PipelineManager:
    def __init__(self, sourcelink_path: str, output_path: str, provider: str, model_name: str):
        self.sourcelink_path = sourcelink_path
        self.output_path = output_path
        self.provider = provider
        self.model_name = model_name

    def run(self, limit: int = None):
        print("🚀 Bắt đầu Web Scraping & Knowledge Graph Synthesis Pipeline...")
        
        # 1. Load Categories
        try:
            category_map = ConfigParser.load_categories(self.sourcelink_path)
            print(f"✅ Đã tải cấu hình danh mục. Tìm thấy {len(category_map)} danh mục.")
        except Exception as e:
            print(f"❌ Lỗi đọc cấu hình: {e}")
            return
            
        # 2. Khởi tạo LLM Synthesizer
        try:
            synthesizer = LLMSynthesizer(provider=self.provider, model_name=self.model_name)
            print(f"✅ Khởi tạo LLM thành công (Provider: {self.provider}, Model: {synthesizer.model_name}).")
        except Exception as e:
            print(f"❌ Lỗi khởi tạo LLM: {e}")
            return
            
        scraper = WebScraper()
        knowledge_graph = {}
        
        # Đọc dữ liệu từ checkpoint cũ nếu có
        if os.path.exists(self.output_path):
            try:
                with open(self.output_path, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                    if "category_knowledge_graph" in checkpoint_data:
                        knowledge_graph = checkpoint_data["category_knowledge_graph"]
                        print(f"🔄 Phát hiện checkpoint cũ. Đã tải {len(knowledge_graph)} danh mục đã hoàn thành.")
            except Exception as e:
                print(f"⚠️ Lỗi đọc file checkpoint cũ: {e}. Đang chạy lại từ đầu...")
        
        # Lọc giới hạn nếu có
        categories_to_process = list(category_map.items())
        if limit:
            categories_to_process = categories_to_process[:limit]
            
        # Vòng lặp chính xử lý từng danh mục
        for cat_name, urls in tqdm(categories_to_process, desc="Phân tích danh mục"):
            # Bỏ qua danh mục nếu đã được xử lý thành công (không phải fallback mặc định)
            if cat_name in knowledge_graph:
                existing_rules = knowledge_graph[cat_name].get("consensus_rules", [])
                if existing_rules != ["Tìm hiểu kỹ quy chuẩn ăn mặc của từng dịp cụ thể."] or not urls:
                    print(f"\n⏭️ Bỏ qua danh mục '{cat_name}' (Đã có trong checkpoint).")
                    continue
            
            print(f"\n📁 Đang xử lý danh mục: '{cat_name}'")
            
            scraped_texts = []
            for i, url in enumerate(urls):
                print(f"  [{i+1}/{len(urls)}] Đang tải & làm sạch URL: {url}")
                cleaned_text = scraper.scrape_url(url)
                if cleaned_text:
                    scraped_texts.append((url, cleaned_text))
                    print(f"    -> Thành công! Kích thước: {len(cleaned_text)} ký tự.")
                else:
                    print(f"    -> Thất bại hoặc URL không có nội dung.")
                    
            if not scraped_texts:
                print(f"  ⚠️ Danh mục '{cat_name}' không có dữ liệu web nào cào được. Sử dụng dữ liệu fallback.")
                fallback_data = synthesizer._get_fallback_graph()
                fallback_data["urls"] = urls
                knowledge_graph[cat_name] = fallback_data
                continue
                
            # Đánh giá kích thước để quyết định dùng Map-Reduce hay Direct Synthesis
            total_len = sum(len(text) for _, text in scraped_texts)
            print(f"  📊 Tổng dung lượng text thu được: {total_len} ký tự.")
            
            # Giới hạn dung lượng trực tiếp (~12000 ký tự)
            if total_len > 12000:
                print(f"  🗺️ Áp dụng cơ chế Map-Reduce (Tóm tắt từng bài viết trước)...")
                summaries = []
                for url, text in scraped_texts:
                    summary = synthesizer.summarize_text(text, url)
                    if summary:
                        summaries.append(f"--- Nguồn {url} ---\n{summary}")
                combined_context = "\n\n".join(summaries)
            else:
                print(f"  📊 Áp dụng cơ chế Direct Synthesis (Đúc kết trực tiếp từ text gốc)...")
                combined_context = "\n\n".join(f"--- Nguồn {url} ---\n{text}" for url, text in scraped_texts)
                
            # Đúc kết Đồ thị Tri thức cuối cùng
            print(f"  🧠 LLM đang tiến hành đúc kết tri thức...")
            graph_data = synthesizer.synthesize_graph(combined_context, cat_name)
            graph_data["urls"] = urls
            
            knowledge_graph[cat_name] = graph_data
            
            # Ghi checkpoint tức thời sau mỗi danh mục đề phòng mất điện
            self._save_checkpoint(knowledge_graph)
            
        # 3. Xuất kết quả cuối cùng
        self._save_final(knowledge_graph)

    def _save_checkpoint(self, data: dict):
        try:
            checkpoint_data = {"category_knowledge_graph": data}
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Lỗi ghi file checkpoint: {e}")

    def _save_final(self, data: dict):
        try:
            final_data = {"category_knowledge_graph": data}
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"\n🎉 QUÁ TRÌNH HOÀN TẤT! Đã lưu Đồ thị Tri thức vào: {self.output_path}")
        except Exception as e:
            print(f"❌ Lỗi khi ghi tệp kết quả cuối cùng: {e}")


def main():
    parser = argparse.ArgumentParser(description="Web Scraping & Knowledge Graph Synthesis Pipeline")
    parser.add_argument("--sourcelink", type=str, default="processed/sourcelink.txt", help="Đường dẫn đến file sourcelink.txt")
    parser.add_argument("--output", type=str, default="processed/structured_knowledge_graph.json", help="Đường dẫn file JSON đồ thị tri thức")
    parser.add_argument("--provider", type=str, default="groq", choices=["groq", "ollama", "openai"], help="Nhà cung cấp API LLM")
    parser.add_argument("--model", type=str, default=None, help="Tên model sử dụng")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng danh mục để test nhanh")
    
    args = parser.parse_args()
    
    manager = PipelineManager(
        sourcelink_path=args.sourcelink,
        output_path=args.output,
        provider=args.provider,
        model_name=args.model
    )
    manager.run(limit=args.limit)

if __name__ == "__main__":
    main()
