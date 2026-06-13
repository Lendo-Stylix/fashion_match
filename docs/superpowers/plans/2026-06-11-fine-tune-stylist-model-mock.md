# Fine-Tune Stylist Model — QLoRA Mock Plan

Date: 2026-06-11

## Goal

Prepare a reproducible dry-run scaffold for the next task: compare and **QLoRA fine-tune**
three local Stylist candidates for OutfitMatch using the same data, Kaggle GPU execution,
and Llama Turbo Quant / llama.cpp GGUF inference driver.

Target candidates:

1. `unsloth/Qwen3-VL-8B-Instruct-GGUF`
2. `unsloth/Qwen3.5-9B-GGUF`
3. `unsloth/gemma-4-12b-it-GGUF`

## Important training assumption

GGUF is the deployment/inference artifact, not the normal fine-tuning source. The mock
therefore separates:

- **Inference/eval target:** Unsloth GGUF repo served by Llama Turbo Quant / llama.cpp via
  OpenAI-compatible `/v1/chat/completions`.
- **QLoRA trainable base:** corresponding HF/Unsloth trainable weights loaded in 4-bit:
  - `Qwen/Qwen3-VL-8B-Instruct`
  - `Qwen/Qwen3.5-9B`
  - `google/gemma-4-12B-it`
- **After QLoRA:** merge adapter or export checkpoint, quantize/select GGUF, then re-run the
  exact same TurboQuant benchmark pack.

This avoids pretending that production GGUF files are directly fine-tuned in-place.

## Created mock artifacts

```text
configs/stylist_finetune_mock.yaml          # QLoRA model/run/dataset/Kaggle mock config
scripts/stylist/mock_finetune_stylist.py    # dry-run manifest generator, no training
data/stylist/fine_tune/                     # local ignored dataset workspace
  stylist_knowledge/                        # user-provided knowledge set
  users_query_and_response/                 # user query/response set
  runs/                                     # generated local mock manifests/reports
```

`data/stylist/` is intentionally ignored by git, so real datasets and run outputs stay local.

## QLoRA recipe in the mock

Default shared mock settings:

- 4-bit loading: `nf4`
- double quant: enabled
- compute dtype: `bfloat16`
- gradient checkpointing: enabled
- max sequence length: `4096`
- train/eval batch size per device: `1`
- gradient accumulation steps: `16`
- learning rate: `2e-4`
- scheduler: `cosine`
- warmup ratio: `0.03`
- epochs: `2`
- LoRA: `r=16`, `alpha=32`, `dropout=0.05`, `bias=none`
- target module strategy: `auto_find_linear_layers_excluding_lm_head`

Per-model mock adapter scope:

- `tune_vision_tower: false`
- `tune_projector: true`
- `target_modules_hint`: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`

These values are mock defaults for the next implementation task; exact module names still need
runtime inspection on the loaded trainable checkpoints.

## Dataset contract for the next implementation

Input set 1 — `stylist_knowledge/`:

- KB/style facts, controlled-vocabulary reminders, product/store explanations, sizing rules.
- Accepted mock extensions: `.jsonl`, `.json`, `.parquet`, `.md`, `.txt`.

Input set 2 — `users_query_and_response/`:

- Supervised user conversations and desired assistant responses.
- Target normalized format for SFT: ChatML-like JSONL with fields:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "task_type": "tool_calling|ask_missing_info|recommend_explain|multi_turn|edge_case",
  "source_set": "stylist_knowledge|users_query_and_response"
}
```

## Kaggle mock mapping

The local `.env.local` should contain only private token values. The mock config references
variable names only:

| Model run | Kaggle env var |
|---|---|
| `qwen3vl8b_instruct_gguf` | `KAGGLE_API_TOKEN_1` |
| `qwen35_9b_gguf` | `KAGGLE_API_TOKEN_2` |
| `gemma4_12b_it_gguf` | `KAGGLE_API_TOKEN_3` |

Do not print or commit token values.

## Dry-run command

```bash
uv run python scripts/stylist/mock_finetune_stylist.py \
  --config configs/stylist_finetune_mock.yaml \
  --create-dirs
```

Expected output:

```text
Wrote mock manifest: data/stylist/fine_tune/runs/mock_manifest.json
```

The generated manifest is redacted and reports:

- dataset directory existence
- count of source files in both data folders
- whether required Kaggle env variable names exist
- shared QLoRA training defaults
- per-model QLoRA recipe hints and adapter output directories
- the GGUF inference repo and trainable base model for each run
- hard gates for later benchmark comparison

## Next task checklist

- [ ] Add/confirm real files in `data/stylist/fine_tune/stylist_knowledge/`.
- [ ] Add/confirm real files in `data/stylist/fine_tune/users_query_and_response/`.
- [ ] Implement dataset normalizer to `train.jsonl` / `eval.jsonl` using the ChatML contract.
- [ ] Build benchmark prompt pack for:
  - enum-safe `search_outfits` JSON/tool extraction
  - Vietnamese stylist response quality
  - missing-info follow-up behavior
  - outfit ID hallucination guard
  - image fashion perception when image input is present
- [ ] Run base GGUF benchmark through Llama Turbo Quant for all three candidates.
- [ ] Run QLoRA fine-tune on trainable base weights in Kaggle.
- [ ] Merge/export checkpoint and quantize/select GGUF artifacts.
- [ ] Re-run the exact same TurboQuant benchmark and compare deltas.

## Browser-verified source notes used for this mock

- `unsloth/Qwen3-VL-8B-Instruct-GGUF`: HF card lists Apache-2.0, image-text-to-text,
  GGUF, llama.cpp `llama-server -hf ...:UD-Q4_K_XL`, Kaggle notebook link, and an
  Unsloth Qwen3-VL fine-tuning notebook reference.
- `unsloth/Qwen3.5-9B-GGUF`: HF card lists Apache-2.0, image-text-to-text, GGUF,
  llama.cpp `llama-server -hf ...:UD-Q4_K_XL`, 262K context, 201 languages/dialects,
  OpenAI-compatible serving, and tool-call parser guidance for Qwen3.5.
- `unsloth/gemma-4-12b-it-GGUF`: HF card lists Apache-2.0, image-text-to-text GGUF,
  llama.cpp `llama-server -hf ...:UD-Q4_K_XL --jinja`, Gemma 4 multimodal support,
  native function calling, and notes that Gemma 4 12B can be run/fine-tuned in Unsloth Studio.
