# Gemma4 12B TurboQuant vs Qwen3.5 9B TurboQuant stylist review (2026-06-08)

## Scope

Evaluate whether `unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL` + latest local TurboQuant is a better **conversational stylist** model than `unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL` + TurboQuant for OutfitMatch.

This is separate from KB item tagging. The stylist workload is mostly:

- Vietnamese intent parsing.
- Ask clarification when the request is too vague.
- Call `search_outfits` with enum-safe arguments from `src/outfitmatch/stylist/tools.py`.
- Avoid deriving body shape / skin tone from insufficient selfie input.
- Avoid hallucinated outfit IDs in final responses.

## External verification

Hugging Face model cards were checked with browser tools.

`unsloth/Qwen3.5-9B-GGUF`:

- Task: Image-Text-to-Text; library tags include Transformers and GGUF; license Apache-2.0.
- Architecture shown as `qwen35`; model size 9B.
- Recommended llama.cpp command: `llama-server -hf unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL`.
- Model card highlights native multimodal agent/tool-use direction, 262K context, and documents tool-call serving with `--tool-call-parser qwen3_coder` for vLLM/SGLang.
- Repository files verified through `huggingface_hub`: `Qwen3.5-9B-UD-Q4_K_XL.gguf`, `mmproj-BF16.gguf`, `mmproj-F16.gguf`, `mmproj-F32.gguf`.

`unsloth/gemma-4-12b-it-GGUF`:

- Task: Image-Text-to-Text; architecture tag `gemma4`; license Apache-2.0.
- Recommended llama.cpp command: `llama-server -hf unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL`.
- Previous local verification showed the latest TheTom TurboQuant fork loads its `gemma4uv` projector successfully.

## Local runtime

Shared binary:

- `data/cache/turboquant/llama-cpp-turboquant/build-cuda-ninja/bin/llama-server.exe`
- Latest local TheTom TurboQuant fork build already used for the Gemma4 12B tagging tests.

Qwen3.5 9B files:

- `C:\Users\Admin\.cache\huggingface\hub\models--unsloth--Qwen3.5-9B-GGUF\snapshots\3885219b6810b007914f3a7950a8d1b469d598a5\Qwen3.5-9B-UD-Q4_K_XL.gguf`
- `...\mmproj-F16.gguf`

Gemma4 12B files:

- `C:\Users\Admin\.cache\huggingface\hub\models--unsloth--gemma-4-12b-it-GGUF\snapshots\5161202e34057160dac9e7907010144f8ef4e4f6\gemma-4-12b-it-UD-Q4_K_XL.gguf`
- `...\mmproj-BF16.gguf`

## Benchmark design

Two lightweight stylist probes were run.

### A. Strict JSON prompt probe

The model was instructed to return JSON directly with:

```json
{"action":"ask_clarification|search_outfits|final_response","tool_args":{},"message_vi":"...","outfit_ids":[]}
```

This tests raw JSON discipline and prompt following without OpenAI tool-call support.

Test set: 6 Vietnamese prompts covering vague request, three `search_outfits` parses, final explanation with allowed outfit IDs, and selfie/body-shape safety.

### B. OpenAI tools API probe

The same local `SEARCH_OUTFITS_TOOL` schema from `src/outfitmatch/stylist/tools.py` was passed through the OpenAI-compatible `tools` API. This is closer to the intended production path because schema names (`price_max`, enum values) are enforced by the server/model tool-call template.

Test set: 5 prompts covering vague clarification, three tool calls, and selfie/body-shape safety.

Artifacts:

- Qwen JSON prompt: `data/cache/stylist_model_eval_qwen35_9b_vs_gemma4_12b_20260608/qwen35_9b/qwen35_9b_stylist_probe.json`
- Gemma JSON prompt: `data/cache/stylist_model_eval_qwen35_9b_vs_gemma4_12b_20260608/gemma4_12b/gemma4_12b_stylist_probe.json`
- Qwen tool API v2: `data/cache/stylist_model_eval_qwen35_9b_vs_gemma4_12b_20260608/qwen35_9b/qwen35_9b_stylist_toolapi_v2_probe.json`
- Gemma tool API v2: `data/cache/stylist_model_eval_qwen35_9b_vs_gemma4_12b_20260608/gemma4_12b/gemma4_12b_stylist_toolapi_v2_probe.json`

## Results

### Strict JSON prompt probe

| Model | valid JSON | score | avg latency | Notes |
|---|---:|---:|---:|---|
| Qwen3.5 9B UD-Q4_K_XL TurboQuant | 6/6 | 16/20 = 80% by the raw scorer | 3.384s | Correct actions; mapped budget to `budget`/`budget_max` instead of required `price_max`; one premature fake outfit-id list in a search response. |
| Gemma4 12B UD-Q4_K_XL TurboQuant | 6/6 | 13/20 = 65% by the raw scorer | 10.730s | More verbose; one prompt returned empty `tool_args` and fake `outfit_...` IDs before retrieval. |

Manual note: both models correctly refused to infer body/skin from selfie, but the first raw scorer missed the phrase `không thể`, so safety behavior is better than the raw score indicates. The relative ranking is unchanged: Qwen3.5 is faster and more instruction-consistent.

### OpenAI tools API probe, production-like schema path

| Model | score | avg latency | Main behavior |
|---|---:|---:|---|
| Qwen3.5 9B UD-Q4_K_XL TurboQuant | 18/18 = 100% | 3.015s | Called `search_outfits` correctly, used exact schema names (`price_max`), asked clarification when vague, refused selfie inference. |
| Gemma4 12B UD-Q4_K_XL TurboQuant | 18/18 = 100% | 10.223s | Also correct under a clear tool-use system prompt, but ~3.4x slower. |

Representative Qwen3.5 tool call:

```json
{
  "occasion": "interview",
  "body_shape": "pear",
  "style": "minimalist",
  "price_max": 800000,
  "exclude_colors": ["đỏ"]
}
```

Representative Gemma4 12B tool call:

```json
{
  "body_shape": "pear",
  "exclude_colors": ["đỏ"],
  "occasion": "interview",
  "price_max": 800000,
  "style": "minimalist"
}
```

## Interpretation for OutfitMatch stylist layer

1. **With the OpenAI `tools` API, both models can satisfy the minimal `search_outfits` contract.** The schema path matters: it fixes the `price_max` naming problem seen in direct JSON prompting.
2. **Qwen3.5 9B is the better local stylist candidate under TurboQuant** for this workload because it matches Gemma4 12B accuracy on the production-like tool API probe while being much faster (`3.015s` vs `10.223s` avg response).
3. **Gemma4 12B does not justify the extra latency as a stylist model** in this local setup. Its main advantage is not visible on intent parsing/tool-call tasks, and previous KB tagging tests already showed it is slow for vision-heavy tagging.
4. **Direct JSON prompting is weaker than tool API for both models.** If the app bypasses OpenAI tools and asks for raw JSON, add a strict response validator/repair loop; otherwise budget fields may drift to `budget`/`budget_max`, and models may emit fake IDs before retrieval.
5. **Qwen3.5 is more aligned with the project roadmap** than Gemma4 12B: the architecture already names a Qwen VL stylist, and the Qwen3.5 model card explicitly emphasizes multimodal agent/tool-use workflows.

## Recommendation

For the OutfitMatch **stylist** layer:

- Prefer **Qwen3.5 9B + TurboQuant** over **Gemma4 12B + TurboQuant** for local inference.
- Use the OpenAI-compatible `tools` API with `SEARCH_OUTFITS_TOOL`; do not rely on raw JSON prompting as the primary integration path.
- Keep the validation layer from `src/outfitmatch/stylist/validation.py` mandatory to block any hallucinated `outfit_id`.
- Treat Gemma4 12B as a backup/ablation model, not the default stylist: it is correct when well-prompted but materially slower with no observed stylist-quality gain.

Caveat: this is a small functional probe, not a full human-rated conversation benchmark. Before final migration, run a larger scripted suite with 50-100 synthetic conversations and score: tool-call accuracy, clarification appropriateness, Vietnamese tone, latency, and hallucinated outfit IDs.
