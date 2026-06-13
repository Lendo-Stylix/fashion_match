# Stylist QLoRA Kaggle Fine-Tune — stylist_knowledge only

Date: 2026-06-12

## User constraints

1. Temporarily ignore `data/stylist/fine_tune/users_query_and_response`.
2. Use only Kaggle/HF secret names `HF_API_TOKEN_2` and `HF_API_TOKEN_3` inside Kaggle kernels.
   `HF_API_TOKEN_1`, `HF_TOKEN`, and `HUGGINGFACE_TOKEN` are forbidden for this run.
3. Fine-tune the 3 planned Stylist models with **Unsloth QLoRA**.
4. Optimize Kaggle GPU usage for `NvidiaTeslaT4x2`.

## Implemented artifacts

```text
configs/stylist_finetune_kaggle.yaml
scripts/stylist/prepare_stylist_qlora_kaggle.py
tests/test_stylist_qlora_kaggle.py
```

Generated local Kaggle package (ignored by git):

```text
data/stylist/fine_tune/runs/kaggle_qlora/
  kaggle_dataset/
    dataset-metadata.json
    train.jsonl   # 39,790 examples from stylist_knowledge
    eval.jsonl    # 512 examples from stylist_knowledge
  kaggle_kernel_qwen3vl8b-instruct/
  kaggle_kernel_qwen35-9b/
  kaggle_kernel_gemma4-12b-it/
  manifest.json
```

## Token mapping

| Run | HF secret/env used |
|---|---|
| `qwen3vl8b_instruct` | `HF_API_TOKEN_2` |
| `qwen35_9b` | `HF_API_TOKEN_2` |
| `gemma4_12b_it` | `HF_API_TOKEN_3` |

## Kaggle optimization choices

- `machine_shape: NvidiaTeslaT4x2`
- generated scripts relaunch with `torchrun --nproc_per_node=2` when 2 GPUs are visible
- QLoRA 4-bit NF4 + double quant
- T4-safe `float16` (not bf16)
- `packing: true` for short knowledge Q&A throughput
- `adamw_8bit`, gradient checkpointing through Unsloth
- effective batch size = `per_device_train_batch_size * visible_gpus * gradient_accumulation_steps`

## Commands

Build package locally:

```bash
PYTHONIOENCODING=utf-8 uv run python scripts/stylist/prepare_stylist_qlora_kaggle.py --clean
```

Push dataset + kernels with Kaggle CLI:

```bash
PYTHONIOENCODING=utf-8 uv run python scripts/stylist/prepare_stylist_qlora_kaggle.py --push
```

Current push attempt created the private dataset:

```text
nhatquangvominh/om-stylist-qlora-data
```

Kernel pushes were blocked by Kaggle account state at the time of the run. The first attempt hit GPU batch quota; a follow-up attempt against the same generated slugs returned partial-create/update errors:

```text
Kernel push error: Maximum batch GPU session count of 2 reached.
Kernel push error: Notebook not found
```

Re-run `--push` after existing Kaggle GPU batch sessions finish. If the `Notebook not found` partial-create state persists, change `kaggle.kernel_slug_prefix` (or append a date suffix), rebuild, then push the fresh kernel folders:

```bash
kaggle kernels push -p data/stylist/fine_tune/runs/kaggle_qlora/kaggle_kernel_qwen3vl8b-instruct
kaggle kernels push -p data/stylist/fine_tune/runs/kaggle_qlora/kaggle_kernel_qwen35-9b
kaggle kernels push -p data/stylist/fine_tune/runs/kaggle_qlora/kaggle_kernel_gemma4-12b-it
```

## Verification

```bash
uv run pytest tests/test_stylist_qlora_kaggle.py -q
uv run ruff check scripts/stylist/prepare_stylist_qlora_kaggle.py tests/test_stylist_qlora_kaggle.py
```
