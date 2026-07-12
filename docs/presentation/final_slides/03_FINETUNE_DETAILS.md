# 03 — Chi tiết Kỹ thuật Fine-tune (QLoRA SFT)

**Phạm vi:** Recipe fine-tune, Kaggle pipeline, kỹ thuật xử lý bug
**Mục tiêu slide:** Cho giám khảo DL thấy **hiểu biết thực hành** về QLoRA, Unsloth, Kaggle, và cách debug vấn đề training thực tế.

---

## 1. Tổng quan recipe fine-tune

### 1.1 Chọn phương pháp: QLoRA

**Vì sao QLoRA thay vì full fine-tune?**

| Phương pháp | VRAM cần | Quality | Tốc độ | Chọn? |
|---|---|---|---|---|
| Full fine-tune 8B bf16 | ~16GB weights + optimizer | Tốt nhất | Chậm | ❌ Vượt T4 free |
| LoRA bf16 | ~16GB weights + small adapter | Tốt | Trung bình | ❌ Vẫn 16GB |
| **QLoRA 4-bit + LoRA** | ~4–5GB + tiny adapter | Gần full FT | Nhanh | ✅ **Chọn** |
| Prompt tuning | <1GB | Yếu | Rất nhanh | ❌ Không đủ cho tool-call |

**QLoRA (paper Hu et al. 2023, NeurIPS):**
- **Quantize** base model 4-bit NF4 (Normal Float 4) + double quantization → giảm VRAM 4×
- **Freeze** base, chỉ train **LoRA adapter** (low-rank decomposition)
- Gradient qua 4-bit weights được dequantize ngược → compute dtype `float16`

### 1.2 Framework: Unsloth

**Vì sao Unsloth thay vì HF Trainer thuần?**
- **2× nhanh hơn** TRL native (kernel thủ công, Triton)
- **Tiết kiệm VRAM 30–60%** (fused kernel, manual gradient)
- **Hỗ trợ Kaggle T4** (free tier) — critical cho dự án sinh viên
- Support đầy đủ Qwen3-VL, Qwen3.5, Gemma 4
- Tự động `auto_find_linear_layers` → không cần chỉ định target modules thủ công

### 1.3 Hyperparameter recipe (final, cho cả 4 model)

Từ `configs/stylist_finetune_kaggle_final_merged.yaml`:

```yaml
training:
  framework: unsloth
  strategy: qlora_sft

  # Quantization
  load_in_4bit: true
  bnb_4bit_quant_type: nf4
  bnb_4bit_use_double_quant: true
  compute_dtype: float16          # T4 không có bf16 native

  # Sequence
  max_seq_length: 2048
  packing: true                   # pack short samples → throughput

  # Batch
  per_device_train_batch_size: 1
  per_device_eval_batch_size: 1
  gradient_accumulation_steps: 8  # effective batch = 1 × 2 GPU × 8 = 16

  # Optimizer
  learning_rate: 0.0002           # 2e-4 (QLoRA cần lr cao hơn full FT)
  lr_scheduler_type: cosine
  warmup_ratio: 0.03
  optim: adamw_8bit               # paged 8-bit AdamW → tiết kiệm VRAM
  weight_decay: 0.01
  num_train_epochs: 1

  # Logging
  logging_steps: 10
  report_to: [wandb]              # project: outfitmatch-v3.1

  # LoRA
  lora:
    r: 16                         # rank
    alpha: 32                     # scaling = alpha/r = 2
    dropout: 0.05
    bias: none
    target_modules:               # all linear
      - q_proj
      - k_proj
      - v_proj
      - o_proj
      - gate_proj
      - up_proj
      - down_proj
```

**Giải thích các choice:**
| Hyper | Giá trị | Lý do |
|---|---|---|
| `nf4` quant | NF4 | Paper gốc: NF4 tối ưu cho weight phân phối chuẩn |
| `double_quant` | true | Quantize cả quant constant → tiết kiệm thêm ~0.4 bits/param |
| `compute_dtype` | float16 | T4 (sm_75) không có bf16 native; bf16 cần Ampere+ |
| `packing` | true | Pack sample ngắn → tận dụng GPU, tăng throughput |
| `lr=2e-4` | cao | LoRA update chỉ vào adapter → cần lr cao hơn full FT (5e-5) |
| `r=16, α=32` | cân bằng | α/r=2 là heuristic tốt; r=16 đủ expressive cho 8B model |
| `target_modules` | all-linear | Query/Key/Value/Output + FFN gate/up/down → phủ hết attention + FFN |
| `epoch=1` | ít | Dataset 11.6K đủ lớn; >1 epoch dễ overfit trên synth data |

---

## 2. Kaggle Pipeline — Đóng gói & chạy

### 2.1 Sơ đồ pipeline

```
LOCAL (dev machine)
┌─────────────────────────────────────────────────────────┐
│ 1. prepare_stylist_qlora_kaggle.py                       │
│    - Đọc config YAML                                     │
│    - collect_examples() → train.jsonl / eval.jsonl       │
│    - Tạo Kaggle dataset bundle (dataset-metadata.json)   │
│    - Tạo 4 kernel folders (1/model) với kernel script    │
│    - manifest.json ghi metadata                          │
└─────────────────────┬───────────────────────────────────┘
                      │ kaggle CLI push
                      ▼
KAGGLE (GPU cloud)
┌─────────────────────────────────────────────────────────┐
│ 2. Kaggle dataset (private):                            │
│    nhatquangvominh/om-stylist-qlora-final-merged-data   │
│    → train.jsonl (11,252) + eval.jsonl (348)            │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│ 3. Kaggle kernel (T4 GPU, internet on):                 │
│    - Bootstrap wheelhouse (torch 2.4 + CUDA stack)      │
│    - pip install unsloth, bitsandbytes (no-deps)        │
│    - Load base model 4-bit (Unsloth FastModel)          │
│    - Attach LoRA adapter (r=16, α=32)                    │
│    - SFTTrainer.train() 704 steps = 1 epoch             │
│    - Save adapter + push HF Hub                          │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
HUGGING FACE (public)
┌─────────────────────────────────────────────────────────┐
│ 4. Nhat-Quang/outfitmatch-stylist-final-{model}-lora    │
│    - adapter_model.safetensors                           │
│    - adapter_config.json                                 │
│    - tokenizer + chat template + processor               │
│    - training_summary.json + trainer_state.json          │
│    - README benchmark summary                            │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Config multi-account Kaggle (token rotation)

```yaml
secrets:
  allowed_hf_token_env_vars: [HF_API_TOKEN_2, HF_API_TOKEN_3]
  forbidden_hf_token_env_vars: [HF_API_TOKEN_1, HF_TOKEN, HUGGINGFACE_TOKEN]

models:
  - run_id: qwen3vl8b_instruct
    hf_token_env: HF_API_TOKEN_2     # account A
  - run_id: qwen3vl8b_thinking
    hf_token_env: HF_API_TOKEN_2     # account A
  - run_id: qwen35_9b
    hf_token_env: HF_API_TOKEN_3     # account B (repo techwithsergiu cần token khác)
```

**Lý do multi-account:** Kaggle GPU quota free tier giới hạn 30h/tuần/account. Dùng 2 HF account + 2 Kaggle account để chạy song song 4 model trong cùng tuần.

### 2.3 Tối ưu Kaggle GPU (NvidiaTeslaT4)

| Tối ưu | Giá trị | Lý do |
|---|---|---|
| `machine_shape` | `NvidiaTeslaT4` | T4 16GB free tier; A100/V100 cần premium |
| QLoRA 4-bit | true | Giảm weights từ ~16GB → ~5GB |
| `float16` (không bf16) | true | T4 sm_75 không có bf16 native |
| `packing: true` | true | Pack samples ngắn → tăng GPU utilization |
| `adamw_8bit` | true | Paged 8-bit optimizer → tiết kiệm VRAM optimizer state |
| `gradient_checkpointing` | true (via Unsloth) | Trade compute cho VRAM |
| `gradient_accumulation=8` | true | Effective batch 16 mà không OOM |

### 2.4 Kết quả training (4 model cùng config)

| Model | Run ID | Final step | Epoch | **Eval loss** | Eval runtime |
|---|---|---:|---:|---:|---:|
| T1 Instruct | `qwen3vl8b_instruct` | 704 | 1.0 | 0.602685 | 83.3s |
| T2 Qwen3.5 | `qwen35_9b_bnb4bit` | 704 | 1.0 | 0.687953 | 99.9s |
| **T3 Thinking** ✅ | `qwen3vl8b_thinking` | 704 | 1.0 | **0.594302** | 85.6s |
| T4 Gemma | `gemma4_12b_it` | 704 | 1.0 | 0.625529 | 136.5s |

Tất cả hoàn thành **704/704 steps = 1 epoch**, không OOM, không crash.

---

## 3. Bug kỹ thuật đã xử lý (Debug Diary)

> **Điểm nhấn DL:** Phần này cho thấy khả năng **debug thực tế** — xử lý conflict giữa transformers/unsloth/torch versions, hardware-specific issues, và HF token rotation. Đây là kinh nghiệm quan trọng khi deploy LLM.

### 3.1 Bảng tổng quan bug

| # | Bug | Root cause | Fix |
|---|---|---|---|
| **B1** | Qwen-VL text-only bị `Incorrect image source` | Gọi `processor(prompt, ...)` positional → prompt bị hiểu là image | Gọi `processor(text=[prompt], images=None, ...)` |
| **B2** | Resume checkpoint sai model | Kaggle dataset có checkpoint cũ/stale | Chỉ restore khi explicit `local_path`; ưu tiên checkpoint đúng model |
| **B3** | Torch 2.4 resume bị Transformers 5.x chặn | CVE-2025-32434 guard + `rng_state_*.pth` weights-only | Patch `check_torch_load_is_safe` no-op + xoá rng_state |
| **B4** | Gemma không load với Transformers pinned | `transformers==5.2.0` chưa hỗ trợ Gemma 4 | Dùng Transformers GitHub main + nâng `huggingface_hub>=1.5` |
| **B5** | Benchmark P100 fail với Torch mới | Torch 2.10 CUDA không support `sm_60` (P100) | Pin Torch 2.4 stack |
| **B6** | Torch downgrade làm torchaudio crash | `torchaudio 2.10` còn lại không khớp Torch 2.4 | Uninstall + align `torchaudio==0.19.0` |
| **B7** | Unsloth inductor shim lỗi | `SimpleNamespace` không có source cho `inspect.getsource` | Gán module thật `torch._inductor.config` |
| **B8** | Pip resolver conflict | Unsloth-Zoo và Transformers main mâu thuẫn deps | Tách install + `--no-deps` cho Unsloth/Transformers main |
| **B9** | bnb 4-bit ValueError `Some modules dispatched on the CPU` | `device_map="auto"` + accelerate infer spill module ra CPU | Dùng `device_map={"":0}` (skip `infer_auto_device_map`) |
| **B10** | trl 0.14 GRPOTrainer import vllm crash | `is_vllm_available()` trả tuple `(False, None)` truthy, Windows không vllm wheel | Tạo vllm stub `__init__.py` raising RuntimeError |
| **B11** | GRPOConfig params removed in 0.14 | `scale_rewards`, `loss_type`, `reward_weights`, `quantization_config` removed | Drop các param deprecated |

### 3.2 Chi tiết bug B9 (device_map) — lesson quan trọng nhất

**Vấn đề:** Load Qwen3-VL-8B bnb-4bit trên RTX 5060 8GB:
```python
# SAI — raise ValueError
model = AutoModelForImageTextToText.from_pretrained(
    "...",
    device_map="auto",                                    # ← виновник
    quantization_config=BitsAndBytesConfig(load_in_4bit=True)
)
# ValueError: Some modules are dispatched on the CPU or the disk
```

**Root cause:**
- `device_map="auto"` gọi `infer_auto_device_map` → quyết định một số module (vision tower, embed_tokens, lm_head) phải spill ra CPU
- Validator `bnb_4bit.validate_environment` check `if "cpu" in device_map.values()` → raise
- Config.json override `llm_int8_enable_fp32_cpu_offload: False` override BitsAndBytesConfig fresh

**Fix:**
```python
# ĐÚNG — skip infer_auto_device_map
model = AutoModelForImageTextToText.from_pretrained(
    "...",
    device_map={"": 0},                                   # ← literal dict, GPU 0 only
    quantization_config=BitsAndBytesConfig(load_in_4bit=True)
)
```

→ Dict value chỉ chứa `0` (GPU) → validator skip → load thành công. Verified: VRAM peak 6.83GB trên RTX 5060 8GB.

### 3.3 Chi tiết bug B1 (Qwen-VL processor)

**Vấn đề:** Đánh giá Qwen3-VL text-only prompt:
```python
# SAI — raise Incorrect image source / base64 error
inputs = processor(prompt, return_tensors="pt")
```

**Root cause:** Processor positional arg bị hiểu là image source khi không có image.

**Fix:**
```python
# ĐÚNG — explicit text= kwarg
inputs = processor(text=[prompt], images=None, return_tensors="pt")
# fallback:
inputs = processor(text=[prompt], return_tensors="pt")
```

### 3.4 Chi tiết bug B10+B11 (trl GRPOTrainer Windows)

**Vấn đề:** Chạy GRPO cho T3 trên Windows + 8GB GPU:
- `from vllm import LLM, SamplingParams` import top-level → Windows không có vllm wheel
- `is_vllm_available()` trả tuple `(False, None)` truthy → vẫn cố import

**Fix (6 patch):**
1. Tạo `.venv/Lib/site-packages/vllm/__init__.py` stub raising RuntimeError
2. Pass `GRPOConfig(use_vllm=False)`
3. Drop `scale_rewards`, `loss_type` (removed in trl 0.14)
4. Drop `reward_weights`, `quantization_config` (removed in GRPOTrainer 0.14)
5. Pre-load model bằng `AutoModelForImageTextToText` (KHÔNG phải `AutoModelForCausalLM`) + `device_map={"":0}`
6. Shim `model.warnings_issued = {}` trước construct trainer (Qwen3VL thiếu attr)

**Verified:** 1 GRPO step (G=2, batch=1, seq=64) trên RTX 5060 8GB exit 0 trong 1m47s.

---

## 4. Inference — Load adapter cho benchmark/production

### 4.1 Code pattern load (từ `run_gpu_benchmark.py`)

```python
from unsloth import FastModel
from peft import PeftModel

# 1. Load base 4-bit
base, processor = FastModel.from_pretrained(
    model_name="unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",
    load_in_4bit=True,
    device_map={"": 0},                    # ← fix bug B9
    max_seq_length=2048,
)

# 2. Attach LoRA adapter
model = PeftModel.from_pretrained(
    base,
    "D:/Models/adapters/Nhat-Quang--outfitmatch-stylist-final-qwen3vl8b-thinking-lora",
)

# 3. Generate
inputs = processor(text=[chat_prompt], images=None, return_tensors="pt")  # ← fix bug B1
output = model.generate(**inputs, max_new_tokens=512, temperature=0.0)
```

### 4.2 Memory footprint (RTX 5060 Laptop 8GB)

| Stage | VRAM |
|---|---|
| Base 4-bit loaded | 5.2 GB |
| + LoRA adapter | +0.2 GB |
| + KV cache (seq 512) | +1.5 GB |
| **Peak (generate)** | **~6.9 GB** |

→ Dư ~1GB headroom trên 8GB card. Có thể chạy T3 local cho demo.

---

## 5. Validation Layer — Guardrail chống hallucination

### 5.1 Tool-call validation (`tools.py` + `validation.py`)

```python
def validate_tool_call_payload(payload):
    errors = []
    if payload.get("name") != "search_outfits":
        errors.append("tool name must be search_outfits")
    arguments = payload.get("arguments", {})
    # Check required
    if "occasion" not in arguments:
        errors.append("occasion is required")
    # Check enum
    for field, allowed in _ENUM_FIELDS.items():
        if field in arguments and arguments[field] not in allowed:
            errors.append(f"{field} not in vocab.py enum")
    # Check extra keys
    extra = set(arguments) - set(ALLOWED_SEARCH_OUTFITS_ARGS)
    if extra:
        errors.append(f"unsupported arguments: {extra}")
    # Check types
    if "price_max" in arguments and not isinstance(arguments["price_max"], int):
        errors.append("price_max must be integer VND")
    return len(errors) == 0, errors
```

### 5.2 Outfit ID hallucination check

```python
_OUTFIT_ID_RE = re.compile(r"\bOF_\d{5,}\b")

def validate_response(response, valid_ids):
    """Block hallucinated outfit IDs."""
    found = _OUTFIT_ID_RE.findall(response)
    invalid = [i for i in found if i not in valid_ids]
    return len(invalid) == 0, invalid
```

### 5.3 Size hallucination check

```python
# Chỉ match "size X" / "cỡ X" explicit → false positive thấp
_SIZE_MENTION_RE = re.compile(r"\b(?:size|cỡ)\s+([A-Za-z]{1,3}|\d{1,3})\b", re.IGNORECASE)

def validate_sizes(text, sizes_in_stock):
    mentioned = extract_size_mentions(text)
    invalid = [s for s in mentioned if s not in sizes_in_stock]
    return len(invalid) == 0, invalid
```

→ **3 lớp guardrail** (outfit_id + tool_call + size) đảm bảo model không bịa thông tin critical cho user.

---

## 6. Kết quả training — Artifact

### 6.1 Files output mỗi adapter

```
Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora/
  ├── adapter_model.safetensors     # ~200MB LoRA weights
  ├── adapter_config.json           # r=16, α=32, target_modules
  ├── tokenizer.json + tokenizer_config.json
  ├── chat_template.jinja           # Qwen3-VL chat format
  ├── processor_config.json         # image preprocessor
  ├── training_summary.json         # eval_loss, steps, runtime
  ├── trainer_state.json            # full training log
  └── README.md                     # benchmark summary
```

### 6.2 Reproducibility

- **Config tracked:** `configs/stylist_finetune_kaggle_final_merged.yaml` (git)
- **Dataset version:** `data/stylist/fine_tune/runs/stylist_grounded_v2/merged_source_gptoss_2800_core8800`
- **Seed:** 42 (config + sampling)
- **Commit SHA:** lưu trong `training_summary.json`
- **Pinned versions:** unsloth==2025.8.5, transformers==5.2.0, peft==0.19.1, torch==2.4.0, bitsandbytes==0.49.2, trl==0.24.0

→ Chạy lại cùng config + cùng dataset + cùng seed → adapter có reproduce cùng eval_loss (đến sai số hardware non-determinism).

---

## 7. Slide gợi ý

1. **Slide QLoRA là gì** (§1.1) — so sánh 4 phương pháp fine-tune.
2. **Slide recipe hyperparameter** (§1.3) — bảng + giải thích choice.
3. **Slide Kaggle pipeline** (§2.1) — sơ đồ local → Kaggle → HF.
4. **Slide tối ưu VRAM** (§2.3 + §4.2) — "T4 16GB → QLoRA 4-bit chỉ 6.9GB peak".
5. **Slide bug đã fix** (§3) — pick 2-3 bug hot nhất (B9 device_map, B1 processor, B10 trl/vllm) → thể hiện kỹ năng debug.
6. **Slide guardrail** (§5) — 3 lớp chống hallucination.
7. **Slide artifact + reproducibility** (§6) — HF repo public, config tracked.

---

*Hết báo cáo fine-tune details. Đọc tiếp `04_EVALUATION.md`.*
