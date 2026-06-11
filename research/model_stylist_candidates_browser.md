# Model Stylist candidates for OutfitMatch (local production survey)

Date: 2026-06-11

## Task fit

OutfitMatch Stylist must: (1) converse naturally in Vietnamese, (2) optionally understand a user outfit/body/occasion image, (3) extract enum-safe intent and call `search_outfits`, (4) ask follow-up questions when required fields are missing, (5) generate Vietnamese explanations, and (6) be feasible for LoRA/SFT on ~3-5K synthetic conversations.

This document is intentionally broader than the MVP architecture default (`Qwen3-VL-8B + LoRA`): it includes heavier local-server candidates for real deployment. Hardware is not used as an exclusion criterion, but serving complexity is called out.

## Recommendation tiers

### Tier A — strongest local-server candidates to benchmark first

| Rank | Candidate | Why it fits OutfitMatch | Main risk / watch item |
|---:|---|---|---|
| 1 | **Qwen/Qwen3.5-27B** | Best balance of quality vs deployment: native multimodal Qwen3.5, Apache-2.0, 201 languages/dialects, 262K context, explicit vLLM/SGLang OpenAI-compatible serving and `qwen3_coder` tool-call parser. Card benchmarks show strong multilingual, instruction-following, VL, visual-agent, and tool-calling scores. | New stack; disable/control thinking mode for strict JSON/tool calls. Needs real Vietnamese stylist benchmark. |
| 2 | **Qwen/Qwen3.5-35B-A3B** | MoE alternative with low active parameter count; same Qwen3.5 multimodal/tool-call stack and Apache-2.0 license. Good candidate if throughput matters more than dense-model simplicity. | MoE serving may require newer vLLM/SGLang and careful batching; benchmark JSON stability vs 27B. |
| 3 | **Qwen/Qwen3.5-122B-A10B** | Highest Qwen3.5 local quality tier checked: 122B/10B active, Apache-2.0, 201 languages/dialects, 262K native context, strong card scores across language, multilingual, visual understanding, and agent/tool benchmarks. | Heavy multi-GPU deployment; overkill unless production demands top local quality. |
| 4 | **OpenGVLab/InternVL3_5-38B** | Strong open VLM family, Apache-2.0, multilingual tag, image/multi-image/video support, vLLM/SGLang/LMDeploy, explicit fine-tuning paths via InternVL/SWIFT/XTuner. Card says 38B needs two A100-class GPUs and supports OpenAI-style serving via LMDeploy. | Tool/function calling not as first-class as Qwen; `trust_remote_code`/custom chat path. Validate enum JSON reliability. |
| 5 | **OpenGVLab/InternVL3_5-241B-A28B** | Candidate for maximum open-source multimodal quality: InternVL3.5 card says largest model reaches SOTA among open-source MLLMs across general multimodal, reasoning, text, and agentic tasks. Apache-2.0 and full training stages are released. | Extremely heavy; use as upper-bound local benchmark rather than default deployment. |
| 6 | **Qwen/Qwen3-VL-235B-A22B-Instruct** | Very strong pre-Qwen3.5 large Qwen VLM, Apache-2.0, local deployable via HF/vLLM/SGLang style stack, good fit as a Qwen-family upper bound. | Qwen3.5 cards claim newer Qwen3.5 models outperform Qwen3-VL on many VL/tool/agent benchmarks; compare empirically. |
| 7 | **zai-org/GLM-4.5V** | MIT MoE VLM, Chinese/English, `glm4v_moe`, vLLM/SGLang tool-call parser and LLaMA-Factory fine-tuning. Good large local comparison for tool/agent behavior. | Chinese/English focus; Vietnamese quality uncertain. |
| 8 | **moonshotai/Kimi-VL-A3B-Instruct** | Efficient MoE VLM: 16B total / ~3B active, MIT, 128K context, strong OCR/long-document/video/agent claims and benchmarks. Useful if production needs efficient server throughput. | Less direct evidence for Vietnamese and tool-calling schema reliability than Qwen; vLLM support may depend on specific branches/versions. |

### Tier B — practical MVP / ablation candidates

| Candidate | Why keep it | Main risk |
|---|---|---|
| **Qwen/Qwen3.5-9B** | Best small Qwen3.5 entry: Apache-2.0, native multimodal, 201 languages/dialects, same tool-call serving recipes, much easier to LoRA/serve than 27B+. | May lose nuanced Vietnamese stylist quality vs 27B/122B. |
| **Qwen/Qwen3-VL-8B-Instruct** | Current architecture baseline; Apache-2.0, long context, OCR/product recognition, many adapters/quantizations, `Qwen3VLForConditionalGeneration`. | Qwen3.5 appears stronger on card benchmarks; local llama.cpp vision can be fragile. |
| **OpenGVLab/InternVL3_5-8B / 14B** | Strong Apache-2.0 VLM family with fine-tuning/deployment ecosystem. Good non-Qwen control. | Tool calling less native than Qwen. |
| **openbmb/MiniCPM-V-4_5** | Apache-2.0, efficient image/video/OCR, >30 languages, GGUF/Ollama/llama.cpp/vLLM/SGLang/LLaMA-Factory support. | Need direct Vietnamese tone + JSON/tool reliability benchmark. |
| **google/gemma-3-12b-it** | Multilingual (>140 languages), image-text-to-text, 128K context, broad ecosystem. | Gemma license; tool/function calling less first-class. |
| **microsoft/Phi-4-multimodal-instruct** | MIT, 5.6B, text/image/audio, 128K context, explicit function/tool-calling prompt format. | Official language support suggests weak Vietnamese; vision language support is English-oriented. |
| **meta-llama/Llama-3.2-11B-Vision-Instruct** | Mature Llama ecosystem and 128K context. | Official image+text support is English-only; license/gating/EU restrictions. |

### Tier C — useful but not primary

| Candidate | Verdict |
|---|---|
| **allenai/Molmo-72B-0924** | Apache-2.0 and very strong 2024 vision benchmark/human-preference claims; good perception upper bound. But English-only tag, older Qwen2 base, weaker explicit tool/function-calling evidence for OutfitMatch. |
| **deepseek-ai/deepseek-vl2** | MoE VLM built on DeepSeekMoE-27B, 4.5B activated params, competitive OCR/document/chart/grounding claims, commercial use under DeepSeek license. Keep as image-understanding ablation; less direct Vietnamese/tool evidence. |
| **mistralai/Pixtral-12B-2409** | Apache-2.0, 12B decoder + 400M vision encoder, 128K, variable image sizes. Good Mistral-stack baseline, but older and less explicit Vietnamese/tool evidence. |
| **llava-hf/llava-onevision-qwen2-7b-ov-hf** | Apache-2.0, simple 7-8B baseline for single/multi-image/video. Older English/Chinese model; not a production favorite. |
| **Viet-Mistral/Vistral-7B-Chat** | Vietnamese text-only baseline for stylist tone/explanations or fallback with separate image encoder. No image; AFL-3.0 license. |

## Suggested evaluation waves

1. **Production-first local wave:** Qwen3.5-27B, Qwen3.5-35B-A3B, Qwen3.5-122B-A10B, InternVL3.5-38B, GLM-4.5V.
2. **MVP/practical wave:** Qwen3.5-9B, Qwen3-VL-8B-Instruct, InternVL3.5-8B/14B, MiniCPM-V-4.5.
3. **Upper-bound/local-heavy wave:** Qwen3-VL-235B-A22B-Instruct, InternVL3.5-241B-A28B, Molmo-72B.
4. **Ablation/fallback wave:** Kimi-VL-A3B-Instruct, DeepSeek-VL2, Gemma-3-12B-it, Phi-4-multimodal, Vistral text-only.

## Pre-fine-tune benchmark plan

Use the same prompt pack for all models before SFT/LoRA:

1. **Intent/tool extraction:** 100 Vietnamese user prompts; measure valid JSON/tool call, required `occasion`, enum validity against `vocab.py`, over-clarification rate, and whether optional fields are hallucinated.
2. **Vietnamese stylist quality:** 50 multi-turn conversations; judge helpfulness, tone, follow-up quality, no hallucinated outfit IDs.
3. **Image fashion perception:** 50 catalog/user images; extract garment category, dominant color, pattern/material, formality, style; compare to KB tags/human spot-check.
4. **Retrieval loop:** E2E `search_outfits` calls using stub catalog; invalid tool calls or invalid enum values are hard failures.
5. **Latency/VRAM/throughput:** quantized and BF16 local serving; record first-token latency, total latency, GPU memory, and image vs text-only throughput.
6. **Fine-tune smoke test:** small LoRA/SFT run on 200-500 synthetic conversations; re-run tool/JSON benchmark to ensure training improves schema adherence without hurting Vietnamese tone.

## Implementation guidance for OutfitMatch

- Keep the code path model-agnostic: expose a local OpenAI-compatible endpoint (`/v1/chat/completions`) and normalize tool/JSON outputs before calling `SEARCH_OUTFITS_TOOL`.
- For Qwen3.5, prefer vLLM/SGLang with `--enable-auto-tool-choice --tool-call-parser qwen3_coder` when supported; pass `chat_template_kwargs: {enable_thinking: false}` for deterministic JSON extraction.
- Keep `Qwen3-VL-8B-Instruct` as the baseline until benchmark results justify switching the architecture default.
- If Vietnamese conversational quality is weak in the best VLM, use a two-stage design: VLM extracts visual attributes; Vietnamese text LLM (e.g. Vistral or a Qwen text model) handles stylist conversation and explanation.

## Source notes verified in browser

- `Qwen/Qwen3.5-9B` HF card: Apache-2.0; image-text-to-text; `qwen3_5`; native 262K context, extensible to ~1M; 201 languages/dialects; vLLM/SGLang tool-call parser (`qwen3_coder`); direct image input examples.
- `Qwen/Qwen3.5-27B` HF card: Apache-2.0; image-text-to-text; 27B/28B; 262K native context; 201 languages/dialects; OpenAI-compatible vLLM/SGLang serving; tool-call parser; card reports strong multilingual, VL, visual-agent, and tool-calling benchmark scores.
- `Qwen/Qwen3.5-35B-A3B` HF card: Apache-2.0; image-text-to-text; `qwen3_5_moe`; conversational; Transformers/Safetensors; same Qwen3.5 model-card family and serving stack.
- `Qwen/Qwen3.5-122B-A10B` HF card: Apache-2.0; image-text-to-text; 122B total / 10B activated; 262K context, extensible to ~1M; 201 languages/dialects; vLLM/SGLang/KTransformers/Transformers serving; tool-call parser (`qwen3_coder`); card says use tensor parallel on 8 GPUs for full 262K context.
- `Qwen/Qwen3-VL-8B-Instruct` HF card: Apache-2.0; image-text-to-text; Qwen3VLForConditionalGeneration; long context 256K/1M; OCR/product/landmark recognition claims; strong spatial/video/visual-agent claims.
- `Qwen/Qwen3-VL-30B-A3B-Instruct` HF card: Apache-2.0; image-text-to-text; `qwen3_vl_moe`; conversational; Transformers/Safetensors.
- `Qwen/Qwen3-VL-235B-A22B-Instruct` HF card: Apache-2.0; image-text-to-text; `qwen3_vl_moe`; conversational; Transformers/Safetensors.
- `OpenGVLab/InternVL3_5-8B` HF card: Apache-2.0; multilingual; image/multi-image/video; vLLM/SGLang/LMDeploy; fine-tuning via InternVL/SWIFT/XTuner.
- `OpenGVLab/InternVL3_5-38B` HF card: Apache-2.0; image-text-to-text; multilingual; `custom_code`; 38.4B total; vLLM/SGLang/LMDeploy; card says 38B needs two A100 GPUs and 241B-A28B needs eight A100 GPUs.
- `OpenGVLab/InternVL3_5-241B-A28B` is listed in the InternVL3.5 card family table as 240.7B total / A28B; card says largest model reaches SOTA among open-source MLLMs across general multimodal, reasoning, text, and agentic tasks.
- `zai-org/GLM-4.5V` HF card: MIT; 106B/108B total with 12B active; Chinese/English; `glm4v_moe`; vLLM/SGLang tool-call parser; LLaMA-Factory fine-tuning.
- `moonshotai/Kimi-VL-A3B-Instruct` HF card: MIT; image-text-to-text; 16B total / 3B activated; 128K context; native-resolution MoonViT; OCR/long-document/video/agent benchmark claims; Transformers with `trust_remote_code`; vLLM support noted via pending/specific branch.
- `openbmb/MiniCPM-V-4_5` HF card: Apache-2.0; 8.7-9B; Qwen3-8B + SigLIP2-400M; >30 languages; efficient OCR/video; vLLM/SGLang/llama.cpp/Ollama/GGUF/AWQ; fine-tuning via Transformers and LLaMA-Factory.
- `google/gemma-3-12b-it` HF card: Gemma license; image-text-to-text; 12B; 128K context; multilingual support over 140 languages; image tokens at 896x896.
- `microsoft/Phi-4-multimodal-instruct` HF card: MIT; 5.6B; text/image/audio; 128K context; primary use cases include function/tool calling; official text language list excludes Vietnamese and vision is English-oriented.
- `meta-llama/Llama-3.2-11B-Vision-Instruct` HF card: Llama 3.2 license; 11B; 128K; official text languages list excludes Vietnamese and image+text applications support English only.
- `allenai/Molmo-72B-0924` HF card: Apache-2.0; English; Qwen2-72B base; CLIP vision backbone; card reports average academic benchmark score 81.2 and human-preference Elo 1077; vLLM note says use <=0.7.2 until a preprocessing bug is fixed.
- `deepseek-ai/deepseek-vl2` HF card: DeepSeek license; Image-Text-to-Text; built on DeepSeekMoE-27B; variants with 1.0B/2.8B/4.5B activated params; claims improved VQA/OCR/document/table/chart/grounding; commercial use supported under DeepSeek model license.
- `mistralai/Pixtral-12B-2409` HF card: Apache-2.0; 12B decoder + 400M vision encoder; 128K; variable image sizes; 2024 multimodal benchmark claims.
- `llava-hf/llava-onevision-qwen2-7b-ov-hf` HF card: Apache-2.0; SO400M + Qwen2; single/multi-image/video; English/Chinese; 8B.
- `Viet-Mistral/Vistral-7B-Chat` HF card: Vietnamese text-generation model; continual pretraining and instruction tuning for Vietnamese; text-only.
