# 🎨 Kế hoạch Xây dựng Hệ thống AI Stylist Cá nhân hóa
## Phong cách Châu Á - Thị trường Việt Nam

**Ngày lập kế hoạch:** 22/05/2026  
**Phiên bản:** 3.0  
**Mục tiêu:** Xây dựng trợ lý thời trang thông minh có khả năng tư vấn outfit cá nhân hóa dựa trên đặc điểm cơ thể, sở thích, dịp mặc và lịch sử tương tác của người dùng.

---

## 📋 Executive Summary

Hệ thống kết hợp **4 công nghệ AI tiên tiến** để tạo ra trải nghiệm stylist ảo chất lượng cao:

| Công nghệ | Vai trò | Mục đích |
|-----------|---------|----------|
| **OutfitTransformer** | Knowledge Base Builder | Tạo dataset 500K+ outfit chất lượng cao |
| **Qwen3-VL (Fine-tuned)** | Conversational Stylist | Hiểu yêu cầu, hỏi lại, giải thích, reason |
| **Vector DB + RAG** | Retrieval Engine | Tìm kiếm outfit phù hợp từ knowledge base |
| **GNN (Graph Neural Network)** | Personalization Layer | Cá nhân hóa dựa trên lịch sử người dùng |

**Điểm khác biệt cốt lõi:**
- ✅ Tập trung vào **phong cách châu Á** (K-fashion, Harajuku, C-beauty, Vietnamese minimalism)
- ✅ Hiểu **đặc điểm cơ thể người Việt** (chiều cao trung bình, tone da ấm, khí hậu nhiệt đới)
- ✅ **Hội thoại tự nhiên** - biết hỏi lại khi thiếu thông tin
- ✅ **Giải thích được lý do** recommend (không phải black-box)

---

## 🏛️ Phần 1: Kiến trúc Hệ thống 4 Tầng
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 1: OUTFIT KNOWLEDGE BASE (Offline - Build 1 lần)       │
│  OutfitTransformer (https://huggingface.co/fkuyumcu/OutfitTransformer-labse) + CLIP → Dataset 500K outfits chất lượng                                │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 2: CONVERSATIONAL AI STYLIST (Qwen3-VL fine-tuned)    │
│  Hiểu intent, hỏi lại, reason, giải thích                   │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 3: RETRIEVAL ENGINE (RAG)                              │
│  Vector Search outfits từ Knowledge Base                     │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  TẦNG 4: PERSONALIZATION (GNN)                               │
│  Re-rank theo lịch sử user                                   │
└──────────────────────────────────────────────────────────────┘


### Tại sao tách thành 4 tầng?

1. **Tầng 1 (Knowledge Base):** OutfitTransformer là mô hình discriminative, không thể sinh outfit mới. Nó chỉ chấm điểm và xếp hạng các candidate outfit đã được tạo sẵn.

2. **Tầng 2 (Qwen3-VL):** LLM/VLM không thể nhớ 500K outfit trong weights → cần "bộ nhớ ngoài" (Vector DB).

3. **Tầng 3 (RAG):** Tách biệt giữa "hiểu yêu cầu" và "tìm kiếm outfit" giúp hệ thống modular, dễ debug và scale.

4. **Tầng 4 (GNN):** Personalization cần lịch sử tương tác dài hạn → GNN học được pattern phức tạp mà simple embedding không làm được.

---

## 📦 Phần 2: Chi tiết Từng Module

### 🗄️ Tầng 1: Outfit Knowledge Base

#### Mục tiêu
Tạo dataset outfit **chất lượng cao, có gán nhãn metadata đầy đủ** để Qwen-VL retrieve khi cần.

#### Cấu trúc dữ liệu 1 outfit

```json
{
  "outfit_id": "OF_001234",
  "items": [
    {
      "item_id": "I_001",
      "category": "top",
      "image_url": "https://...",
      "embedding": [0.12, -0.34, ...],
      "metadata": {
        "brand": "Local Brand A",
        "price": 450000,
        "color": "beige",
        "material": "cotton",
        "size_range": ["S", "M", "L", "XL"]
      }
    },
    {
      "item_id": "I_002",
      "category": "bottom",
      "image_url": "https://...",
      "embedding": [...],
      "metadata": {...}
    },
    {
      "item_id": "I_003",
      "category": "shoes",
      ...
    },
    {
      "item_id": "I_004",
      "category": "accessory",
      ...
    }
  ],
  
  "outfit_embedding": [0.45, -0.12, ...],
  "compatibility_score": 0.92,
  
  "style_tags": ["minimalist", "korean", "office"],
  "occasions": ["công sở", "hẹn hò", "cafe"],
  "suitable_body_shapes": ["pear", "hourglass"],
  "suitable_skin_tones": ["warm", "neutral"],
  "suitable_height_range": {"min": 155, "max": 170},
  "suitable_weight_range": {"min": 45, "max": 65},
  "season": ["spring", "autumn"],
  "asian_style_reference": "Seoul street style 2025",
  
  "stylist_explanation": "Set đồ này phối blazer oversized màu be cùng quần ống rộng, tạo silhouette dài phù hợp với dáng người quả lê. Phong cách tối giản kiểu Hàn, phù hợp môi trường công sở."
}

Nguồn dữ liệu

Store VN (Shopee, Lazada, Tiki, Local brands)
	Items rời
	50K items
Musinsa (Hàn)
	Outfit hoàn chỉnh + items
	30K outfits
ZOZOTOWN (Nhật)
	Outfit + items
	20K outfits
Taobao Fashion
	Items + outfit inspiration
	40K itemsYesStyle
Outfit phong cách châu Á
	15K outfits
Pinterest/Instagram
	Outfit ảnh (cần crawl kỹ)
	100K ảnh
* Nguồn và số lượng có thể thay đổi và biến động theo quá trình collection 

Dùng 2 cách để tạo ra các combinations outfit:
1.  Dùng Iterative Fill-in-the-blank (Beam Search) để sinh ra 70% dataset. Đây sẽ là những bộ đồ "chuẩn mực", logic, dùng để dạy Qwen-VL cách phối đồ cơ bản, an toàn, phù hợp số đông.
Quy trình:
Bước 1: Chọn Anchor Item (Món đồ neo)
Random chọn 1 cái Áo (Top) từ database. Đây là điểm xuất phát.
Current_Outfit = [Top_A]
Bước 2: Tìm Quần (Bottom)

    Input vào model: [Top_A_Embedding] + [BLANK_Bottom_Token]
    Model output ra Query_Bottom_Vector.
    Search trong database Quần: Lấy ra Top 5 cái quần có độ tương đồng cao nhất với Query_Bottom_Vector.
    Kỹ thuật quan trọng: Đừng lấy Top 1! Hãy dùng Top-K Sampling (chọn ngẫu nhiên 1 trong 5 cái quần đó). Việc này giúp outfit đa dạng hơn, không bị rập khuôn.
    Giả sử chọn được Bottom_B.
    Current_Outfit = [Top_A, Bottom_B]

Bước 3: Tìm Giày (Shoes)

    Input vào model: [Top_A_Embedding] + [Bottom_B_Embedding] + [BLANK_Shoes_Token]
    Model output ra Query_Shoes_Vector (Lúc này model đã hiểu cả Áo VÀ Quần).
    Search trong database Giày: Lấy Top 5, chọn ngẫu nhiên 1 đôi Shoes_C.
    Current_Outfit = [Top_A, Bottom_B, Shoes_C]

Bước 4: Tìm Phụ kiện (Túi/Kính - Optional)

    Lặp lại quy trình với [BLANK_Accessory_Token].

👉 Kết quả: Bạn có một bộ outfit được build từ gốc, mọi mảnh ghép đều logic và hài hòa với nhau. Không cần bước "chấm điểm lại" (re-scoring) vì bản thân quá trình build đã là quá trình tối ưu hóa compatibility rồi.
* Kết hợp Beam Search để tăng tính phá cách
Cách hoạt động:

    Beam Size = 3 (Giữ lại 3 nhánh tốt nhất ở mỗi bước).
    Bước 1 (Áo): Chọn 1 áo.
    Bước 2 (Quần): Tìm Top 3 cái quần hợp nhất ➔ Tạo ra 3 nhánh: (Áo+Quần1), (Áo+Quần2), (Áo+Quần3).
    Bước 3 (Giày): 
        Từ (Áo+Quần1) ➔ Tìm Top 3 giày ➔ 3 bộ.
        Từ (Áo+Quần2) ➔ Tìm Top 3 giày ➔ 3 bộ.
        Từ (Áo+Quần3) ➔ Tìm Top 3 giày ➔ 3 bộ.
        Tổng cộng có 9 bộ.
    Chốt đơn: Chấm điểm nhanh 9 bộ này bằng OutfitTransformer (Compatibility Score), giữ lại Top 3 bộ có điểm cao nhất nhưng khác biệt nhau nhất (Diversity penalty).
2. Dùng Random Sampling + OutfitTransformer Scoring (lọc lấy những bộ có điểm số cao nhưng ngẫu nhiên) cho 30% còn lại. Nhóm này sẽ chứa những sự kết hợp "phá cách", "trendy" hoặc "high-fashion" mà cách lắp ráp tuần tự khó có thể nghĩ ra được.
Quy trình:
Bước 1: Data Ingestion & Preprocessing (Chuẩn hóa dữ liệu)
Dữ liệu cào từ store VN thường rất lộn xộn. Bạn cần chuẩn hóa về chuẩn mà model labse yêu cầu.
Xử lý Input cho Model:

    Image: Resize về kích thước chuẩn của Vision Encoder trong OutfitTransformer (thường là 224x224 hoặc 256x256), chuẩn hóa (normalize) theo mean/std của ImageNet.
    Text (LaBSE): Ghép title_vi + desc_vi. Dùng LaBSE Tokenizer để tokenize. Lưu ý: Giữ nguyên tiếng Việt, LaBSE xử lý tiếng Việt tốt hơn dịch sang tiếng Anh.
    Category: Map về ID (VD: top=0, bottom=1, shoes=2...).

Bước 2: Item Embedding Extraction (Trích xuất đặc trưng - Chạy Offline 1 lần)
Đây là bước bạn chạy items qua các Encoder của model để lấy vector đại diện.

Bước 3: Smart Candidate Generation (Phễu lọc ứng cử viên)
Nếu bạn random 1 áo + 1 quần + 1 giày từ 50k items, bạn sẽ tạo ra hàng tỷ combo "thảm họa" (VD: Áo khoác lông vũ + Quần đùi hoa + Giày lặn). OutfitTransformer sẽ chấm điểm thấp hết và bạn phí GPU.
👉 Giải pháp: Dùng CLIP làm "Vòng gửi xe" (Pre-filter).
Luật tạo Candidate (Funnel):

    Rule-based: Bắt buộc 1 Top + 1 Bottom + 1 Shoes. (Bag/Accessory optional).
    CLIP Pre-filter: Tính Cosine Similarity giữa ảnh của Top và Bottom bằng CLIP. Nếu độ tương đồng màu sắc/phong cách quá thấp (dưới ngưỡng 0.4) -> Loại bỏ.
    Output: Tạo ra khoảng 100,000 - 500,000 candidate outfits có "nhìn bằng mắt thường cũng thấy tạm ổn".

Bước 4: OutfitTransformer Scoring (Chấm điểm bằng labse)
Bây giờ, bạn đưa các candidate outfits (đã được tạo ở Giai đoạn 3) vào model labse để chấm điểm Compatibility (Độ tương thích).

Bước 5: LLM Metadata Enrichment (Gán nhãn ngữ nghĩa)
Model OutfitTransformer-labse chỉ cho bạn Điểm số (Score) và Vector (Embedding). Nó KHÔNG biết bộ này là "đi biển", "công sở" hay "hợp với dáng người quả lê".
👉 Bạn cần dùng Qwen2.5-VL-72B (hoặc GPT-4o) chạy qua 1 lần để gán nhãn (Tagging) cho các valid_outfits.
Prompt cho LLM:
```text
Tôi có 1 bộ trang phục gồm 4 ảnh: [Ảnh 1: Áo], [Ảnh 2: Quần], [Ảnh 3: Giày], [Ảnh 4: Túi].
Hãy đóng vai một Stylist chuyên nghiệp tại Việt Nam, phân tích và trả về JSON chính xác theo format sau:
{
  "style_tags": ["minimalist", "korean", ...],
  "occasions": ["đi làm", "cafe", ...],
  "suitable_body_shapes": ["dáng người quả lê", "cao gầy", ...],
  "suitable_skin_tones": ["da ngăm", "da trắng", ...],
  "season": ["mùa hè", "mùa thu"],
  "stylist_explanation": "Bộ đồ này sử dụng tông màu be_pastel..."
}
```
Lưu ý: Chỉ chạy LLM tagging cho những outfit đã được OutfitTransformer chấm điểm > 0.75 để tiết kiệm chi phí API.

Sau đó tất cả outfit sẽ được lưu vào cơ sở dữ liệu Knowledge Base để sử dụng trong các bước tiếp theo.
🤖 Tầng 2: Qwen3-VL Fine-tuning (Trái tim hệ thống)
4 vai trò của Qwen3-VL
Intent Parser: Trích xuất thông số từ text tự nhiên
	"Em cao 1m60 nặng 55kg" → {height: 160, weight: 55}

Body Analyzer: Phân tích ảnh body (nếu có)
	Ảnh → {body_shape: "pear", skin_tone: "warm"}

Conversational Agent: Hỏi lại khi thiếu thông tin
	"Bạn định mặc đi đâu ạ? Dạ tiệc hay dạo phố?"

Outfit Explainer: Giải thích lý do recommend
	"Chiếc váy này nhấn eo, giúp bạn trông cao hơn..."

Format dữ liệu training (Instruction Tuning)
Mục tiêu: Tạo 50K-100K mẫu hội thoại chất lượng cao.
Ví dụ mẫu training:
{
  "conversations": [
    {
      "role": "system",
      "content": "Bạn là stylist chuyên về phong cách châu Á, đặc biệt am hiểu thị trường Việt Nam. Hãy tư vấn dựa trên thông tin cơ thể, sở thích và dịp của khách. Nếu thiếu thông tin quan trọng (chiều cao, cân nặng, dịp mặc, ngân sách), hãy hỏi lại một cách tự nhiên và thân thiện."
    },
    {
      "role": "user",
      "content": "Mai em đi đám cưới bạn thân, em cao 1m58 nặng 62kg, da ngăm. Gợi ý cho em bộ đồ với"
    },
    {
      "role": "assistant",
      "content": "Để tư vấn chính xác nhất, chị hỏi thêm nhé:\n\n👗 Bạn thích mặc váy hay set áo-quần?\n🎨 Bạn có kiêng màu nào khi đi đám cưới không (vd: trắng, đỏ - tùy vùng)?\n💰 Ngân sách khoảng bao nhiêu ạ?\n\nVới dáng người 1m58/62kg và tone da ấm, chị đã có vài ý tưởng rất hợp rồi, chỉ cần thêm thông tin trên là chốt được!"
    },
    {
      "role": "user",
      "content": "Em thích váy, không mặc trắng với đỏ, dưới 2 triệu ạ"
    },
    {
      "role": "assistant",
      "content": "[TOOL_CALL: search_outfits(style='elegant', occasion='wedding', body_shape='petite', skin_tone='warm', price_max=2000000, exclude_colors=['white', 'red'])]\n\nChị gợi ý 3 set cho bạn:\n\n**1. Váy midi họa tiết hoa nhí nền navy** - 1.490.000đ\n[IMAGE: outfit_OF_001234]\n💡 *Lý do*: Dáng midi chữ A dài qua gối giúp cân đối tỷ lệ cho chiều cao 1m58, nền navy tôn da ngăm rất tốt. Họa tiết nhỏ tránh làm người trông to hơn.\n\n**2. Váy wrap dress màu xanh rêu** - 1.790.000đ\n[IMAGE: outfit_OF_005678]\n💡 *Lý do*: Dáng wrap dress nhấn eo tự nhiên, màu xanh rêu rất hợp với tone da ấm. Chất liệu lụa mát, phù hợp đám cưới mùa hè.\n\n**3. Set áo lụa champagne + chân váy xếp ly** - 1.950.000đ\n[IMAGE: outfit_OF_009012]\n💡 *Lý do*: Set đồ tạo cảm giác cao hơn nhờ đường eo cao của chân váy. Màu champagne sang trọng nhưng không lấn át cô dâu.\n\nBạn thích set nào nhất? Hay muốn chị gợi ý thêm phong cách khác?"
    }
  ]
}

Các loại mẫu training cần có:
Hỏi lại thông tin thiếu
	15K
	Dạy model biết khi nào cần hỏi
Phân tích ảnh body
	10K
	Dạy model extract đặc điểm từ ảnh
Recommend + giải thích
	30K
	Dạy model reason và explain
Từ chối lịch sự
	5K
	Khi yêu cầu không khả thi (vd: "em muốn mặc crop top nhưng bụng to")
Multi-turn conversation
	10K
	Hội thoại dài, refine yêu cầu
Edge cases
	5K
	Tình huống khó (dị ứng chất liệu, tôn giáo, văn hóa)
Tool calling
	10K
	Dạy model gọi hàm search_outfits

Kỹ thuật fine-tuning
Phương pháp: LoRA (Low-Rank Adaptation) để tiết kiệm chi phí và thời gian.
```python
from peft import LoraConfig, get_peft_model
from transformers import Qwen2VLForConditionalGeneration

# Load base model
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen3-VL-8B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# Cấu hình LoRA
lora_config = LoraConfig(
    r=64,  # Rank
    lora_alpha=128,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Output: trainable params: 41M || all params: 8B || trainable%: 0.51%

# Training
from trl import SFTTrainer
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="./qwen3-vl-stylist",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    fp16=False,
    bf16=True,
    logging_steps=10,
    save_strategy="epoch",
    evaluation_strategy="epoch",
    warmup_steps=100,
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
    tokenizer=tokenizer,
)

trainer.train()
```

Chi phí fine-tuning:
- Qwen3-VL-8B với LoRA trên dataset 100K mẫu ( có thể dùng 32B nếu để tăng quality, hạn chế nằm ở dataset, phần cứng không là vấn đề)
- GPU: 4x A100 80GB (hoặc 8x RTX 4090)
- Thời gian: ~24-48 giờ
- Chi phí: ~10-15M VND (thuê cloud GPU)

Quantization để deploy
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

# Quantize xuống 4-bit để giảm VRAM
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    "./qwen3-vl-stylist",
    quantization_config=bnb_config,
    device_map="auto"
)

# VRAM usage: ~6GB (thay vì 16GB)
# Inference speed: ~2x faster
* Phần này để 4-bit cho môn học, sau này khi deploy thật sẽ dùng full-16-bit

🔍 Tầng 3: Retrieval Engine (RAG)
Kiến trúc Vector DB
Lựa chọn: Qdrant (open-source, dễ deploy, hiệu năng cao) hoặc Milvus (nếu scale rất lớn).
```python
from qdrant_client import QdrantClient
from qdrant_client.http import models

qdrant = QdrantClient(host="localhost", port=6333)

# Tạo collection
qdrant.create_collection(
    collection_name="outfits",
    vectors_config=models.VectorParams(
        size=768,  # Dimension của outfit embedding
        distance=models.Distance.COSINE
    )
)

# Tạo payload indexes để filter nhanh
qdrant.create_payload_index(
    collection_name="outfits",
    field_name="occasions",
    field_schema=models.PayloadSchemaType.KEYWORD
)

qdrant.create_payload_index(
    collection_name="outfits",
    field_name="style_tags",
    field_schema=models.PayloadSchemaType.KEYWORD
)

qdrant.create_payload_index(
    collection_name="outfits",
    field_name="suitable_body_shapes",
    field_schema=models.PayloadSchemaType.KEYWORD
)
```

Tool-calling format cho Qwen-VL
Định nghĩa tool:
```python
search_outfits_tool = {
    "type": "function",
    "function": {
        "name": "search_outfits",
        "description": "Tìm kiếm outfit phù hợp từ database dựa trên các bộ lọc",
        "parameters": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "description": "Phong cách (vd: minimalist, korean, streetwear, elegant)"
                },
                "occasion": {
                    "type": "string",
                    "description": "Dịp mặc (vd: công sở, hẹn hò, đám cưới, dạo phố)"
                },
                "body_shape": {
                    "type": "string",
                    "description": "Dáng người (vd: pear, apple, hourglass, rectangle)"
                },
                "skin_tone": {
                    "type": "string",
                    "description": "Tone da (vd: warm, cool, neutral)"
                },
                "height_range": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "integer"},
                        "max": {"type": "integer"}
                    }
                },
                "weight_range": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "integer"},
                        "max": {"type": "integer"}
                    }
                },
                "price_max": {
                    "type": "integer",
                    "description": "Ngân sách tối đa (VND)"
                },
                "exclude_colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Các màu cần tránh"
                }
            },
            "required": ["occasion"]
        }
    }
}
```

Ví dụ Qwen-VL gọi tool:
User: "Em cao 1m65, nặng 58kg, mai đi phỏng vấn ngân hàng, thích phong cách thanh lịch"

Qwen-VL output:
{
  "tool_call": {
    "name": "search_outfits",
    "arguments": {
      "style": "elegant",
      "occasion": "interview",
      "body_shape": "hourglass",
      "height_range": {"min": 160, "max": 170},
      "weight_range": {"min": 55, "max": 62}
    }
  }
}

System thực hiện search:
results = qdrant.search(
    collection_name="outfits",
    query_vector=user_embedding,
    query_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="occasions",
                match=models.MatchValue(value="interview")
            ),
            models.FieldCondition(
                key="style_tags",
                match=models.MatchValue(value="elegant")
            )
        ]
    ),
    limit=50
)

Trả về top 50 outfits → GNN re-rank → Qwen-VL giải thích top 3-5

🔗 Tầng 4: GNN Personalization
Cấu trúc đồ thị
[User A] ──(liked)──▶ [Outfit X] ──(contains)──▶ [Item 1]
   │                      │                          │
   │                      └──(contains)──▶ [Item 2]  │
   │                                                 │
   └──(bought)──▶ [Item 3] ──(co-occurs)─────────────┘

Các loại node và edge
Nodes:

    User: Thông tin user (id, demographics, style preference)
    Outfit: Outfit trong knowledge base
    Item: Sản phẩm riêng lẻ

Edges:

    user → outfit: viewed, liked, bought, rejected, time_spent
    outfit → item: contains
    item → item: co-purchased, same-style, same-brand
    user → user: similar-taste (optional, cho collaborative filtering)

Lựa chọn GNN architecture
- LightGCN
- GraphSAGE
- GAT (Graph Attention Network)
- PinSage (GraphSAGE với attention mechanism)

LightGCN implementation
```python
import torch
import torch.nn as nn
from torch_geometric.nn import LightGCN

class FashionGNN(nn.Module):
    def __init__(self, num_users, num_outfits, num_items, embedding_dim=64):
        super().__init__()
        
        # Embedding layers
        self.user_embedding = nn.Embedding(num_users, embedding_dim)
        self.outfit_embedding = nn.Embedding(num_outfits, embedding_dim)
        self.item_embedding = nn.Embedding(num_items, embedding_dim)
        
        # LightGCN layers
        self.lightgcn = LightGCN(
            num_nodes=num_users + num_outfits + num_items,
            embedding_dim=embedding_dim,
            num_layers=3
        )
        
    def forward(self, edge_index, user_ids, outfit_ids):
        # Concatenate all embeddings
        x = torch.cat([
            self.user_embedding.weight,
            self.outfit_embedding.weight,
            self.item_embedding.weight
        ], dim=0)
        
        # LightGCN propagation
        x = self.lightgcn(x, edge_index)
        
        # Extract user and outfit embeddings
        user_emb = x[user_ids]
        outfit_emb = x[outfit_ids]
        
        # Predict compatibility score
        scores = torch.sum(user_emb * outfit_emb, dim=1)
        return scores
    
    def get_user_embedding(self, user_id):
        return self.user_embedding(user_id)

# Training
model = FashionGNN(num_users=10000, num_outfits=500000, num_items=100000)
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Loss function (BPR loss)
def bpr_loss(pos_scores, neg_scores):
    return -torch.mean(torch.log(torch.sigmoid(pos_scores - neg_scores)))

for epoch in range(100):
    model.train()
    optimizer.zero_grad()
    
    # Sample positive and negative outfits for each user
    pos_scores = model(edge_index, user_ids, pos_outfit_ids)
    neg_scores = model(edge_index, user_ids, neg_outfit_ids)
    
    loss = bpr_loss(pos_scores, neg_scores)
    loss.backward()
    optimizer.step()
```
Re-ranking pipeline
```python
def gnn_rerank(user_id, candidate_outfits, model, top_k=5):
    """
    Re-rank candidate outfits dựa trên user preference
    """
    user_emb = model.get_user_embedding(user_id)
    
    scores = []
    for outfit_id in candidate_outfits:
        outfit_emb = model.outfit_embedding(outfit_id)
        score = torch.dot(user_emb, outfit_emb).item()
        scores.append((outfit_id, score))
    
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    
    return [outfit_id for outfit_id, _ in scores[:top_k]]

# Sử dụng trong inference
candidate_outfits = search_outfits(filters)  # Top 50 từ Vector DB
reranked_outfits = gnn_rerank(user_id, candidate_outfits, model, top_k=5)
explanations = qwen_vl_explain(user_id, reranked_outfits)
```

Cold-start solution
Vấn đề: User mới không có lịch sử → GNN không hoạt động tốt.
Giải pháp:

    1. Onboarding quiz (5 câu hỏi):
        Phong cách yêu thích? (Minimalist, Streetwear, Elegant, Casual, Bohemian)
        Dịp mặc thường xuyên? (Công sở, Đi học, Dạo phố, Tiệc, Ở nhà)
        Màu ưa thích? (Chọn 3 màu)
        Ngân sách trung bình? (<500K, 500K-1M, 1M-2M, >2M)
        Chiều cao & cân nặng?
    2. Initial user embedding:
    ```python
    def create_initial_user_embedding(quiz_answers):
        # Map quiz answers to embedding space
        style_emb = style_embedding[quiz_answers['style']]
        occasion_emb = occasion_embedding[quiz_answers['occasion']]
        color_emb = color_embedding[quiz_answers['colors']]
        
        # Average để tạo initial embedding
        user_emb = (style_emb + occasion_emb + color_emb) / 3
        return user_emb
    ```
    3. Fallback strategy:
    
        10 interactions đầu: Dùng popularity-based + quiz-based recommendation
        Sau 10 interactions: Chuyển sang GNN personalizatio
        

🔄 Phần 3: Pipeline Inference Hoàn chỉnh
Step 1: User nhập text + (optional) ảnh body
              ↓
Step 2: Qwen3-VL phân tích → Extract structured info
        Input: "Mai em đi đám cưới, cao 1m60 nặng 55kg, da trắng"
        Output: {
          height: 160,
          weight: 55,
          skin_tone: "cool",
          occasion: "wedding",
          missing_info: ["style_preference", "budget"]
        }
              ↓
Step 3: [Check đủ info?] ──No──▶ Hỏi lại (quay lại Step 1)
        Qwen-VL: "Bạn thích phong cách nào? Thanh lịch hay cá tính? 
                 Ngân sách khoảng bao nhiêu ạ?"
              │ Yes
              ↓
Step 4: Gọi Tool: search_outfits(filters)
        → Vector DB trả 50 outfits
              ↓
Step 5: GNN re-rank với user history → Top 10
        (Nếu user mới: dùng quiz-based ranking)
              ↓
Step 6: Qwen3-VL chọn Top 3-5 + sinh giải thích cá nhân hóa
        Output: 
        "Chị gợi ý 3 set cho bạn:
        
        1. Váy midi hoa nhí navy - 1.490.000đ
        [Hình ảnh]
        💡 Lý do: Dáng midi phù hợp chiều cao 1m60, navy tôn da trắng..."
              ↓
Step 7: Hiển thị + ghi nhận feedback
        User click "like" outfit 1 → Update GNN
        User mua outfit 2 → Update GNN + track conversion

🎯 Phần 4: Roadmap Triển khai:
Phần này hiện tại chưa có kế hoạch cho Scum XP 

⚠️ Phần 5: Rủi ro và Giải pháp
Rủi ro 1: Qwen-VL "bịa" outfit không có trong DB
Nguyên nhân: LLM có xu hướng hallucinate, đặc biệt khi không có đủ context.
Hậu quả: Recommend outfit không tồn tại → user thất vọng.
Giải pháp:

    Bắt buộc dùng structured tool-calling: Qwen-VL chỉ được output outfit_id, không được mô tả item mà không retrieve.
    Validation layer: Sau khi Qwen-VL generate response, check xem tất cả outfit_id có trong DB không.
    Fallback mechanism: Nếu hallucination detected, trả về message: "Xin lỗi, để chị kiểm tra lại và gợi ý bộ khác nhé."
    '''python
    def validate_response(response, valid_outfit_ids):
        outfit_ids = extract_outfit_ids(response)
        invalid_ids = [id for id in outfit_ids if id not in valid_outfit_ids]
        
        if invalid_ids:
            return False, "Hallucination detected"
        return True, "Valid"
    '''

Rủi ro 2: Data outfit VN chất lượng thấp
Nguyên nhân: 
    Store VN ít "shop the look", chủ yếu bán items rời
    Mô tả sản phẩm nghèo nàn ("Áo thun nam form rộng")
    Ảnh không đồng nhất (background lộn xộn, watermark)
Hậu quả: Outfit generated chất lượng kém → user không tin tưởng.
Giải pháp:

    Auto-caption bằng BLIP-2: Tự động sinh mô tả chi tiết cho từng item.
    Synthetic outfit generation: Dùng LLM (GPT-4o, Qwen-VL) tạo outfit từ items.
    Human-in-the-loop: Thuê 2-3 stylist VN verify 5K outfits làm gold standard.
    Data augmentation: Mix-and-match items từ nhiều nguồn (VN + Hàn + Nhật).
    ```python
    # Auto-caption example
    from transformers import Blip2ForConditionalGeneration
    
    blip2 = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b")
    
    def generate_caption(image):
        prompt = "Describe this clothing item in detail, including color, style, material, and suitable occasions."
        caption = blip2.generate(image, prompt)
        return caption
    
    # Example output:
    # "A beige oversized blazer made of cotton blend, featuring a relaxed fit 
    # with padded shoulders. Suitable for office wear or casual outings in 
    # spring and autumn."
    ```

Rủi ro 3: Cold-start problem cho GNN
Nguyên nhân: User mới không có lịch sử tương tác → GNN không có data để learn preference.
Hậu quả: Recommend không cá nhân hóa → user bỏ đi.
Giải pháp:

    Onboarding quiz 5 câu: Thu thập style, occasion, màu ưa thích, ngân sách, chiều cao/cân nặng.
    Initial user embedding: Map quiz answers → embedding space.
    Fallback strategy: 
        10 interactions đầu: Popularity-based + quiz-based recommendation
        Sau 10 interactions: Chuyển sang GNN personalization
    Progressive profiling: Dần dần thu thập thêm thông tin qua hội thoại.

Rủi ro 4: Inference latency cao
Nguyên nhân: 

    Qwen3-VL-8B inference chậm (~2-3 giây/response)
    Vector search + GNN re-rank thêm ~1 giây
    Tổng latency ~4-5 giây → user experience kém

Hậu quả: User bỏ đi vì chờ lâu.
Giải pháp:

    Quantization (Q4/Q5): Giảm VRAM 50%, tăng speed 2x.
    Caching: Cache popular queries và responses.
    Async processing: Search và GNN re-rank chạy song song.
    Streaming response: Qwen-VL generate text theo streaming (như ChatGPT).
    Model distillation: Train Qwen3-VL-4B (nhỏ hơn) từ Qwen3-VL-8B.
    ```python
    # Streaming response example
    from transformers import TextStreamer
    
    streamer = TextStreamer(tokenizer, skip_prompt=True)
    
    output = model.generate(
        input_ids,
        max_new_tokens=512,
        streamer=streamer,  # Stream tokens as they're generated
        do_sample=True,
        temperature=0.7
    )
    ```

Rủi ro 5: Bias trong recommendation
Nguyên nhân:

    Data chủ yếu từ người mẫu gầy, cao → model bias toward body type đó
    Ít data cho size lớn (plus-size) hoặc chiều cao thấp

Hậu quả: Recommend không phù hợp cho diverse body types → user cảm thấy bị exclude.
Giải pháp:

    Diverse data collection: Chủ động crawl data từ plus-size fashion brands, petite fashion.
    Bias audit: Regular check recommendation distribution theo body type.
    Inclusive training data: Thêm samples cho mọi body shape, height, weight.
    User feedback loop: Cho phép user report "outfit này không phù hợp với dáng người tôi".

Câu hỏi cần trả lời trước khi bắt đầu
Target users là ai? Tất cả người dùng Việt Nam, nhưng core sẽ là các bạn trẻ từ 16-30 tuổi - độ tuổi phân vân nhiều về việc ăn mặc

Business model? Dự định freemium ban đầu, và hỗ trợ recommendation cho các brand. Sau đó nếu mở rộng thêm sẽ làm subscription cho các brand lớn.

Có integration với e-commerce không? Chỉ suggest, nhưng sẽ trích suất thông tin về brand và giá tiền của item cho user

Team hiện có những ai? 3 devs chính 

Timeline mong muốn? MVP trong 3 tháng phục vụ đề án môn học. 6 tháng cho ra sản phẩm hoàn chỉnh deploy lên internet.
