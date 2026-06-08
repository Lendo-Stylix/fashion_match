# Gemma4 12B TurboQuant tagging review (2026-06-08)

## Scope

Compare `unsloth/gemma-4-12b-it-GGUF` against the current local Gemma4 E4B/TurboQuant tagging setup for OutfitMatch item semantic tagging (`body_shapes_fit`, `season`, `stylist_notes_vi`). Outfit tags are derived deterministically from item tags in `src/outfitmatch/kb/assemble_record.py`, so no separate LLM outfit-tagging path was benchmarked.

## External verification

Hugging Face model card checked for `unsloth/gemma-4-12b-it-GGUF`:

- Task: Image-Text-to-Text, GGUF, `gemma4`, Apache-2.0.
- Recommended llama.cpp invocation: `llama-server -hf unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL`.
- Model card states Gemma 4 12B Unified supports text/image/audio input and documents `chat_template_kwargs: {"enable_thinking": False}` for usable final content.
- Model card says a recent stock llama.cpp can auto-download/use the multimodal projector.

## Runtime findings

Local runtime: `data/cache/turboquant/tqp-v0.1.1/llama-server.exe` (Windows CUDA fork).

### 12B multimodal preflight

Command attempted:

```bash
./data/cache/turboquant/tqp-v0.1.1/llama-server.exe \
  -hf unsloth/gemma-4-12b-it-GGUF:UD-Q4_K_XL \
  --host 127.0.0.1 --port 8087 \
  -ngl auto -c 4096 -fa on \
  --cache-type-k q8_0 --cache-type-v turbo3 \
  --image-max-tokens 140 --reasoning off --jinja --cache-ram 0
```

Result: model weights loaded, but multimodal projector failed:

```text
clip_init: failed to load .../mmproj-BF16.gguf: load_hparams: unknown projector type: gemma4uv
srv load_model: failed to load multimodal model
```

Interpretation: this forked runtime lacks projector support for Gemma4 12B Unified (`gemma4uv`), despite the HF model card indicating recent stock llama.cpp support.

### 12B text-only diagnostic

Reran with `--no-mmproj` to test JSON discipline and semantic behavior without image input. This is not a fair multimodal replacement test.

Artifacts:

- JSONL: `data/cache/tagging_model_eval_gemma4_12b_20260608/gemma4_12b_udq4xl_turboquant_text_only.jsonl`
- Summary: `data/cache/tagging_model_eval_gemma4_12b_20260608/summary_text_only.json`

Sample: 35 current-tagged catalog items, 5 evenly spaced items per category: `top`, `bottom`, `dress`, `outerwear`, `shoes`, `bag`, `accessory`.

Results:

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma4 12B UD-Q4_K_XL TurboQuant, text-only | 35 | 100% | 22/35 = 62.9% | 6.155s | 6.020s | 0.461 | 0.679 |

Notes:

- All responses were parseable JSON.
- Most incompleteness came from empty `body_shapes_fit`, especially for `bag` and `accessory`.
- Because image input was disabled, quality numbers are diagnostic only.

### Current E4B multimodal comparison on same sample

Startup needed `--image-min-tokens 64 --image-max-tokens 140`; otherwise the runtime errored with `image_max_pixels ... is less than image_min_pixels`.

Artifacts:

- JSONL: `data/cache/tagging_model_eval_gemma4_e4b_same35_20260608/gemma4_e4b_udq4xl_turboquant_same35.jsonl`
- Summary: `data/cache/tagging_model_eval_gemma4_e4b_same35_20260608/summary.json`

Results:

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma4 E4B UD-Q4_K_XL TurboQuant, vision | 35 | 100% | 22/35 = 62.9% | 1.733s | 1.674s | 0.653 | 0.821 |

### Latest TurboQuant fork retest

Per follow-up request, the old local `tqp-v0.1.1` runtime was removed and the latest `TheTom/llama-cpp-turboquant` branch `feature/turboquant-kv-cache` was pulled and built locally.

Runtime:

- Source commit: `7d9715f1f071fa07c7b2ad3dbfd320b314139e65` (`server: fix router child process lifecycle deadlock...`).
- Local binary: `data/cache/turboquant/llama-cpp-turboquant/build-cuda-ninja/bin/llama-server.exe`.
- Source inspection/build confirmed `tools/mtmd` includes `gemma4uv.cpp` and `gemma4ua.cpp` projector support.

Startup command used local HF cache files to avoid re-download:

```bash
./data/cache/turboquant/llama-cpp-turboquant/build-cuda-ninja/bin/llama-server.exe \
  -m ~/.cache/huggingface/hub/models--unsloth--gemma-4-12b-it-GGUF/.../gemma-4-12b-it-UD-Q4_K_XL.gguf \
  --mmproj ~/.cache/huggingface/hub/models--unsloth--gemma-4-12b-it-GGUF/.../mmproj-BF16.gguf \
  --host 127.0.0.1 --port 8087 \
  -ngl 99 -c 4096 -fa on \
  --cache-type-k q8_0 --cache-type-v turbo3 \
  --image-min-tokens 64 --image-max-tokens 140 \
  --reasoning off --jinja --cache-ram 0
```

Preflight result: `/v1/models` reported `capabilities:["completion","multimodal"]`, and a real image request returned valid JSON. The previous `unknown projector type: gemma4uv` error did not recur.

Artifacts:

- JSONL: `data/cache/tagging_model_eval_gemma4_12b_latest_turboquant_20260608/gemma4_12b_udq4xl_latest_turboquant_vision_same35.jsonl`
- Summary: `data/cache/tagging_model_eval_gemma4_12b_latest_turboquant_20260608/summary.json`

Same 35-item benchmark results:

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma4 E4B UD-Q4_K_XL TurboQuant, vision | 35 | 100% | 22/35 = 62.9% | 1.733s | 1.674s | 0.653 | 0.821 |
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 35 | 100% | 25/35 = 71.4% | 29.398s | 30.733s | 0.447 | 0.693 |

### Large same-sample retest: 500 items + 150 outfits

Per the accuracy follow-up, a larger deterministic same-sample benchmark was added and run.
The sample uses 150 generated outfits from `data/custom/outfits/generated_outfits.parquet`,
then fills to 500 unique catalog items with category-balanced tagged items. Outfit-level body
and season metrics are derived from the item predictions using the same conservative rules as
`src/outfitmatch/kb/assemble_record.py`.

Benchmark helper and tests:

- Script: `scripts/data/kb/eval_turboquant_tagging_large.py`
- Tests: `tests/kb/test_eval_turboquant_tagging_large.py`
- Test command: `uv run pytest tests/kb/test_eval_turboquant_tagging_large.py -q`

Artifacts:

- E4B JSONL: `data/cache/tagging_model_eval_large_500_150_20260608/e4b/e4b_latest_turboquant_vision_500x150.jsonl`
- E4B summary: `data/cache/tagging_model_eval_large_500_150_20260608/e4b/e4b_latest_turboquant_vision_500x150_summary.json`
- 12B JSONL: `data/cache/tagging_model_eval_large_500_150_20260608/12b/12b_latest_turboquant_vision_500x150.jsonl`
- 12B summary: `data/cache/tagging_model_eval_large_500_150_20260608/12b/12b_latest_turboquant_vision_500x150_summary.json`

Verification: both runs used identical 500 `item_id`s and identical 150 `outfit_id`s. E4B had
one no-text response on an accessory item; outfit-derived metrics still evaluate all 150 outfits
because accessory/bag tags are ignored by the conservative outfit body/season derivation rules.

Item-level results:

| Model/mode | n | valid JSON | complete payload | avg latency | median latency | p95 latency | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemma4 E4B UD-Q4_K_XL latest TurboQuant, vision | 500 | 499/500 = 99.8% | 358/500 = 71.6% | 1.700s | 1.699s | 2.008s | 0.599 | 0.769 |
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 500 | 500/500 = 100.0% | 351/500 = 70.2% | 29.938s | 29.521s | 35.162s | 0.537 | 0.663 |

Outfit-derived results:

| Model/mode | outfits evaluated | complete derived outfit tags | avg body Jaccard vs current tags | avg season Jaccard vs current tags |
|---|---:|---:|---:|---:|
| Gemma4 E4B UD-Q4_K_XL latest TurboQuant, vision | 150 | 150/150 = 100.0% | 0.669 | 0.845 |
| Gemma4 12B UD-Q4_K_XL latest TurboQuant, vision | 150 | 150/150 = 100.0% | 0.600 | 0.803 |

## Recommendation

Do not migrate item tagging to `unsloth/gemma-4-12b-it-GGUF`.

Updated conclusion after the larger benchmark:

1. Latest TurboQuant fixes the hard blocker: Gemma4 12B multimodal loads with `gemma4uv`
   and accepts image requests.
2. On the larger 500-item / 150-outfit same-sample test, 12B no longer improves complete
   payload rate; E4B is slightly better on item completeness (`71.6%` vs `70.2%`).
3. E4B matches the current catalog pseudo-reference better at both item level and derived
   outfit level.
4. 12B is still ~17.6x slower on this machine (`29.938s` vs `1.700s` avg/item), making it
   impractical for production-scale retagging unless a much faster runtime/hardware path is used.

Caveat: current catalog tags are pseudo-reference, not human gold labels. If 12B is still
suspected to be semantically better, the next useful step is a human-reviewed 50-100 item
body-fit audit. For automated large-scale tagging, keep E4B.
