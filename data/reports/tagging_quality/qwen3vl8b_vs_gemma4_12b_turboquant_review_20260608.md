# Qwen3-VL 8B TurboQuant vs Gemma4 12B TurboQuant tagging review (2026-06-08)

## Scope

Compare `unsloth/Qwen3-VL-8B-Instruct-GGUF:UD-Q4_K_XL` against `unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL` for OutfitMatch catalog item semantic tagging (`body_shapes_fit`, `season`, `stylist_notes_vi`). Outfit metrics are derived deterministically from item predictions using the same conservative rules as `src/outfitmatch/kb/assemble_record.py`; no separate outfit-level LLM call is benchmarked.

Naming note: the user request said "Qwen3.5-VL" and "Qwen3-VL:8B". I evaluated the currently browsed/public GGUF model `unsloth/Qwen3-VL-8B-Instruct-GGUF`; I did not find/use a separate `Qwen3.5-VL 8B` GGUF artifact in the local cache.

## External/browser verification

Hugging Face model cards checked with browser tools:

- `unsloth/Qwen3-VL-8B-Instruct-GGUF`
  - Task: Image-Text-to-Text; format: GGUF; architecture tag: `qwen3vl`; license: Apache-2.0.
  - Model card recommends `llama-server -hf unsloth/Qwen3-VL-8B-Instruct-GGUF:UD-Q4_K_XL` for llama.cpp.
  - UD-Q4_K_XL listed size: ~5.15 GB; model size: 8B params.
  - Card highlights Qwen3-VL improvements: Interleaved-MRoPE, DeepStack, 256K native context expandable to 1M, stronger OCR/spatial/video reasoning.
- `unsloth/gemma-4-12b-it-GGUF`
  - Task: Image-Text-to-Text; format: GGUF; architecture tag: `gemma4`; license: Apache-2.0.
  - Model card recommends `llama-server -hf unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL`.
  - UD-Q4_K_XL listed size: ~7.37 GB; model size: 12B params.
  - Card documents Gemma4 12B Unified text/image/audio support and disabling thinking for usable final content.

## Runtime setup

Shared runtime:

- Binary: `data/cache/turboquant/llama-cpp-turboquant/build-cuda-ninja/bin/llama-server.exe`
- Fork/build: latest local TheTom TurboQuant fork previously built at commit `7d9715f1f071fa07c7b2ad3dbfd320b314139e65`.
- Machine log: RTX 5060 Laptop GPU, 8 GB VRAM.

Qwen3-VL local files downloaded through `huggingface_hub`:

- Model: `C:\Users\Admin\.cache\huggingface\hub\models--unsloth--Qwen3-VL-8B-Instruct-GGUF\snapshots\b93a7ee713758252c555be4210c00540df954dc2\Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf`
- Projector: `...\mmproj-F16.gguf`

Gemma4 12B comparison source:

- Existing completed 500-item / 150-outfit benchmark from `data/cache/tagging_model_eval_large_500_150_20260608/12b/`.

## Qwen3-VL runtime findings

### First attempt: auto slots crashed on second image

Initial command used auto server slots (`n_parallel = 4`) with local model/projector paths:

```bash
llama-server.exe \
  -m Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  --mmproj mmproj-F16.gguf \
  --host 127.0.0.1 --port 8087 \
  -ngl 99 -c 4096 -fa on \
  --cache-type-k q8_0 --cache-type-v turbo3 \
  --reasoning off --jinja --cache-ram 0
```

Result: `/v1/models` reported `capabilities:["completion","multimodal"]`, and item 1 returned valid JSON. Item 2 failed image processing and the server died/connection was refused for later requests. Log excerpt:

```text
load_hparams: Qwen-VL models require at minimum 1024 image tokens to function correctly...
failed to find a memory slot for batch of size 2048
failed to decode image
slot update_slots: ... failed to process image
```

### Stable config for benchmark

Qwen3-VL became stable with one slot and explicit image token budget:

```bash
llama-server.exe \
  -m Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  --mmproj mmproj-F16.gguf \
  --host 127.0.0.1 --port 8087 \
  -ngl 99 -c 4096 -np 1 -b 4096 -ub 2048 \
  -fa on --cache-type-k q8_0 --cache-type-v turbo3 \
  --reasoning off --jinja --cache-ram 0 \
  --image-min-tokens 1024 --image-max-tokens 1024
```

This avoided the image-processing crash, but latency rose to roughly Gemma4-12B-class speed.

## Same-sample prefix benchmark

Because Qwen3-VL required ~25s/item under the stable settings, I did not run a full 500-item Qwen pass. Instead, I evaluated Qwen3-VL on the first 60 item IDs from the already established deterministic 500-item / 150-outfit sample, then summarized Gemma4 12B on the exact same 60 item IDs from its completed 500-item JSONL. Those first 60 item IDs cover 32 fully evaluable generated outfits.

Artifacts:

- Qwen JSONL: `data/cache/tagging_model_eval_qwen3vl8b_vs_gemma4_12b_20260608/qwen3vl8b_same500_prefix60/qwen3vl8b_latest_turboquant_vision_same500_prefix60_np1_img1024.jsonl`
- Qwen summary: `data/cache/tagging_model_eval_qwen3vl8b_vs_gemma4_12b_20260608/qwen3vl8b_same500_prefix60/qwen3vl8b_latest_turboquant_vision_same500_prefix60_np1_img1024_summary.json`
- Gemma4 12B prefix summary: `data/cache/tagging_model_eval_qwen3vl8b_vs_gemma4_12b_20260608/gemma4_12b_same500_prefix60/gemma4_12b_latest_turboquant_vision_same500_prefix60_summary.json`
- Full Gemma4 12B reference: `data/cache/tagging_model_eval_large_500_150_20260608/12b/12b_latest_turboquant_vision_500x150_summary.json`

Category mix for the exact 60-item prefix: 18 top, 15 bottom, 16 shoes, 3 bag, 4 accessory, 2 outerwear, 2 dress.

### Item-level results on exact same 60 items

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | p95 latency | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-VL 8B UD-Q4_K_XL latest TurboQuant, vision (`np1`, image 1024) | 60 | 60/60 = 100.0% | 39/60 = 65.0% | 25.385s | 24.398s | 31.328s | 0.452 | 0.658 |
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 60 | 60/60 = 100.0% | 45/60 = 75.0% | 32.780s | 31.961s | 43.648s | 0.537 | 0.706 |

### Outfit-derived results on exact same 32 evaluable outfits

| Model/mode | outfits evaluated | complete derived outfit tags | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|
| Qwen3-VL 8B UD-Q4_K_XL latest TurboQuant, vision (`np1`, image 1024) | 32 | 32/32 = 100.0% | 0.407 | 0.802 |
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 32 | 32/32 = 100.0% | 0.605 | 0.870 |

### Tag distribution / qualitative behavior

Qwen3-VL output was valid JSON, but semantically collapsed toward a narrow tag set:

| Model | body tag counts on 60 items | season tag counts on 60 items |
|---|---|---|
| Qwen3-VL 8B | `pear`: 37, `rectangle`: 4 | `summer`: 57, `transitional`: 2 |
| Gemma4 12B | `rectangle`: 38, `pear`: 16, `hourglass`: 2 | `summer`: 51, `transitional`: 11, `winter`: 5 |

The Qwen run tends to over-predict `pear` and `summer`. This explains the lower body Jaccard, especially for `top` items where Qwen body Jaccard was only `0.161` versus Gemma4 12B `0.467` on the same 18 tops.

## Full Gemma4 12B reference from previous completed benchmark

The full 500-item / 150-outfit Gemma4 12B result remains:

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | p95 latency | avg body Jaccard | avg season Jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 500 | 500/500 = 100.0% | 351/500 = 70.2% | 29.938s | 29.521s | 35.162s | 0.537 | 0.663 |

Outfit-derived full result: 150/150 outfits evaluated, 100.0% complete, body Jaccard `0.600`, season Jaccard `0.803`.

## Assessment for OutfitMatch

1. **Qwen3-VL 8B is not ready as a local TurboQuant tagger in this setup.** It needs `-np 1` plus 1024 image tokens to avoid image-processing crashes, which removes much of the expected speed advantage.
2. **Qwen3-VL is faster than Gemma4 12B only under the stable config, and only modestly so** on this sample (`25.385s` vs `32.780s` avg/item). It is still far too slow for large catalog retagging compared with the existing Gemma4 E4B setup (~1.7s/item from the previous large benchmark).
3. **Gemma4 12B is better than Qwen3-VL 8B on this tagging task** across same-sample item completeness, item body/season Jaccard, and derived outfit body/season Jaccard.
4. **Qwen3-VL has a suspicious tag-collapse pattern** (`pear`/`summer`) under the current strict JSON tagging prompt. This is risky for `body_shapes_fit`, where vocabulary diversity matters.
5. **For the upcoming main-project fine-tune, Qwen3-VL remains architecturally aligned with the project stylist model plan**, but this local GGUF/TurboQuant zero-shot result does not justify replacing Gemma-based KB tagging.

## Recommendation

- **Do not migrate KB item tagging from Gemma4 E4B/Gemma4 12B to Qwen3-VL 8B TurboQuant based on this run.**
- **Do not use Qwen3-VL 8B TurboQuant as the quality baseline for catalog retagging** until the image-processing crash and tag-collapse behavior are fixed.
- **For fine-tuning the project stylist model**, evaluate Qwen3-VL/Qwen3.5-VL in its intended Transformers/LoRA stack, not only as GGUF/TurboQuant. The fine-tune should be judged on conversational stylist tasks: intent parsing, tool-call JSON, clarification questions, grounded outfit references, and Vietnamese explanations.
- If Qwen3-VL tagging is still desired, next experiment should be a prompt/settings ablation: lower image token budget if supported without crash, different `temperature/top_p`, shorter prompt, and a 50-item human-gold audit instead of relying only on current catalog pseudo-reference tags.

Caveat: all automated quality numbers use current catalog tags as pseudo-reference labels, not human gold labels.
