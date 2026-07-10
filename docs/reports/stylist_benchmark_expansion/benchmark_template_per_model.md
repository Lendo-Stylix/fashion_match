# Benchmark Template per-Model (T1/T2/T3/T4)

**Ngày:** 2026-07-10 · Hướng dẫn cấu hình & chạy mỗi benchmark cho 4 adapters QLoRA.

## 1. JSON output schema (chuẩn cho mọi benchmark)

```json
{"run_id":"B-fs_T3_20260710T1400","model":{"id":"T3","base":"unsloth/Qwen3-VL-8B-Thinking-bnb-4bit","adapter":"Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora"},"benchmark":{"name":"FashionStylist-V1","task":"Task2-Completion","split":"Female","n_samples":500},"metrics":{"completion_acc":0.55,"grounding_f1":0.42},"decoding":{"temperature":0.0,"max_new_tokens":512,"do_sample":false},"commit":"532db50","timestamp":"2026-07-10T14:00:00+00:00"}
```

## 2. 4 models prefill

| ID | base | adapter |
|----|------|---------|


| T1 | unsloth/Qwen3-VL-8B-Instruct-bnb-4bit | Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-instruct-lora |


| T2 | techwithsergiu/Qwen3.5-text-9B-bnb-4bit | Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora |


| T3 | unsloth/Qwen3-VL-8B-Thinking-bnb-4bit | Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora |


| T4 | unsloth/gemma-4-12b-it | Nhat-Quang/outfitmatch-stylist-final-gemma4-12b-it-lora |

## 3. StylistModelAdapter wiring (pseudocode)

```python
from src.outfitmatch.stylist.model_adapter import StylistModelAdapter

adapter = StylistModelAdapter(
    base_id="unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",
    adapter_id="Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora",
    load_in_4bit=True,
    cache_dir="D:/Models/hf_hub",  # KHÔNG ổ C
)

text = adapter.generate_text(messages=[{"role":"user","content":"Dạo tiệc cưới chọn gì?"}])
# hoặc multimodal (T1/T3/T4):
text, _ = adapter.generate_with_images(messages, images=[img1])
```

## 4. Lệnh chạy mỗi benchmark

| # | Model | Lệnh |
|---|-------|-------|


| B-fs FashionStylist | T3 | `uv run python -m scripts.benchmarks.run_fashion_stylist --model T3 --tasks task1,task2 --split Female --out docs/experiments/FStylist_T3.json` |


| B-fa fashion-agent | T3 | `uv run python -m scripts.benchmarks.run_fashion_agent --model T3 --out docs/experiments/FAgent_T3.json` |


| B-bfcl | T3 | `uv run python -m scripts.benchmarks.run_bfcl --model T3 --adapter search_outfits --out docs/experiments/BFCL_T3.json` |


| B-po Polyvore | retrieval | `uv run python -m scripts.ablation_encoder --out docs/experiments/polyvore.csv` |


| B-ife IFEval | T3 | `lm-eval --model hf --model_args pretrained=unsloth/Qwen3-VL-8B-Thinking-bnb-4bit,peft=Nhat-Quang/...-thinking-lora --tasks ifeval --output_path docs/experiments/IFEval_T3.json --hf_cache_dir D:/Models/hf_hub` |



> Loop 4 models: `python -m scripts.benchmarks.run_all --benchmarks B-fs,B-fa,B-bfcl,B-ife --out_dir docs/experiments/`.
