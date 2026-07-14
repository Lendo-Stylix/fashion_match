"""GRPO RL training script for T3 Qwen3-VL-8B Thinking stylist (verifiable reward).

Launch on Kaggle (T4 x2 or P100) or Colab (T4/A100). Implements the strategy
in docs/reports/stylist_benchmark_expansion/RL_STRATEGY.md:
GRPO + QLoRA with reward = 6 deterministic scorers from fashion_eval.

Local CPU dry-run (sanity check reward shaping, no real training):
    uv run python -m scripts.stylist.train_grpo_kaggle --dry-run

Kaggle/GPU run (set HF_HUB_CACHE to D:/Models locally, /kaggle/working on Kaggle):
    accelerate launch scripts/stylist/train_grpo_kaggle.py \
        --model unsloth/Qwen3-VL-8B-Thinking-bnb-4bit \
        --max-steps 500

Outputs: LoRA adapter to --output-dir (push to HF Hub if --push-to-hub).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("stylist.grpo_train")

# --- reward + pool wiring (importable both as package and standalone) ---
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from grpo_rewards import (  # type: ignore[import-not-found]  # noqa: E402
    FASHION_REWARD_FUNCS,
    ITEM_TYPES,
    build_fashion_prompt_pool,
    canonical_prompt_pool,
)

DEFAULT_MODEL = "unsloth/Qwen3-VL-8B-Thinking-bnb-4bit"  # T3 base
DEFAULT_OUTPUT = "outputs/t3-grpo-lora"


def build_dataset(
    max_per_type: int | None = None,
    canonical: bool = False,
    no_think: bool = False,
    item_type: str | None = None,
):
    """Build the GRPO prompt dataset.

    Each row has a ``prompt`` column (chat messages) + ``item`` (ground-truth
    dict for reward). Set canonical=True for the 28-item regression set.
    """
    try:
        from datasets import Dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("datasets library required: uv add datasets") from exc

    all_items = canonical_prompt_pool() if canonical else build_fashion_prompt_pool(max_per_type)
    if item_type is not None:
        all_items = [it for it in all_items if it.get("item_type") == item_type]
    items = all_items
    rows = []
    for item in items:
        prompt = item.get("prompt", "")
        if no_think:
            # Qwen3-VL chat template directive: disable reasoning for this turn.
            # Lets short completion budgets (8GB VRAM) yield a direct answer instead
            # of being truncated inside the <think> reasoning trace.
            prompt = "/no_think\n" + prompt
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là stylist AI tiếng Việt. Trả lời CỰC NGẮN (dưới 100 token), "
                    "chỉ liệt kê từ khóa / enum / lời gọi công cụ, không giải thích dài. "
                    "Khi cần tìm outfit, gọi công cụ search_outfits."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        rows.append({"prompt": messages, "item": item, "item_type": item.get("item_type", "")})
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="GRPO RL training for stylist (T3)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Base model HF id or path")
    parser.add_argument(
        "--adapter", default=None, help="Optional initial LoRA adapter (e.g. T3 SFT)"
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--max-per-type", type=int, default=None, help="Cap prompts per task type")
    parser.add_argument("--canonical", action="store_true", help="Use 28-item canonical pool")
    parser.add_argument(
        "--no-think",
        action="store_true",
        default=True,
        help="Prepend /no_think directive to prompts (default True; needed for 8GB VRAM",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Force thinking mode (overrides --no-think). Needs large max-completion-length.",
    )
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--beta", type=float, default=0.04, help="Drift KL coefficient")
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-completion-length", type=int, default=256)
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.9,
        help="GRPO sampling temperature (lower = more deterministic, e.g. 0.3).",
    )
    parser.add_argument(
        "--item-type",
        default=None,
        help="Filter dataset to a single item_type to isolate signal.",
    )
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--push-to-hub", default=None, help="HF repo id to push adapter")
    parser.add_argument(
        "--report-to",
        default="none",
        help="W&B logger target. Use 'wandb' on Kaggle for online logging "
        "(requires WANDB_API_KEY in env). Default 'none' for local/offline.",
    )
    parser.add_argument(
        "--wandb-project",
        default="outfitmatch-stylist",
        help="W&B project name (used when --report-to wandb).",
    )
    parser.add_argument(
        "--wandb-run-name",
        default=None,
        help="W&B run name (used when --report-to wandb).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Build dataset + rewards, no training"
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Force HF cache off C: drive when running locally (no-op on Kaggle/Linux).
    os.environ.setdefault("HF_HUB_CACHE", "D:/Models/hf_hub")
    os.environ.setdefault("HF_HOME", "D:/Models/hf_home")

    no_think_enabled = args.no_think and not args.think
    dataset = build_dataset(
        max_per_type=args.max_per_type,
        canonical=args.canonical,
        no_think=no_think_enabled,
        item_type=args.item_type,
    )
    logger.info(
        "No-think mode: %s (prompt prefix /no_think %s)",
        no_think_enabled,
        "ON" if no_think_enabled else "OFF",
    )
    logger.info(
        "Dataset: %d rows; task distribution: %s",
        len(dataset),
        {t: sum(1 for r in dataset["item_type"] if r == t) for t in ITEM_TYPES},
    )

    if args.dry_run:
        # Sanity-check reward shaping: score the canonical pool with a mock
        # generate_fn that always ask-backs (the SFT-collapse behavior).
        def mock_generate(messages):
            return "Bạn muốn mặc cho dịp nào ạ? (đi làm, hẹn hò, đám cưới, ...)"

        from grpo_rewards import fashion_reward  # type: ignore[import-not-found]

        mock_completions = [mock_generate(None) for _ in range(len(dataset))]
        rewards = fashion_reward(mock_completions, items=list(dataset["item"]))
        mean_r = sum(rewards) / max(len(rewards), 1)
        logger.info("DRY-RUN mean reward with mock (always-ask-back) model: %.4f", mean_r)
        logger.info(
            "Per-task reward sum: %s",
            {
                t: sum(
                    r
                    for r, it in zip(rewards, list(dataset["item"]), strict=False)
                    if it.get("item_type") == t
                )
                for t in ITEM_TYPES
            },
        )
        logger.info("Dry-run complete. No training. Use without --dry-run on GPU.")
        return

    # Real training — requires GPU + trl/peft/bitsandbytes.
    try:
        import torch
        from peft import LoraConfig
        from transformers import BitsAndBytesConfig
        from trl import GRPOConfig, GRPOTrainer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Training requires GPU deps: uv add 'trl[peft]' bitsandbytes torch. "
            "Run on Kaggle/Colab. Error: " + str(exc)
        ) from exc

    if not torch.cuda.is_available():  # pragma: no cover
        raise SystemExit("No CUDA GPU. Use --dry-run on CPU, or run on Kaggle/Colab.")

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_dropout=0.05,
    )

    training_args = GRPOConfig(
        output_dir=args.output_dir,
        learning_rate=args.lr,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        temperature=args.temperature,
        beta=args.beta,
        optim="paged_adamw_8bit",
        fp16=True,
        bf16=False,
        gradient_checkpointing=True,
        logging_steps=10,
        save_steps=100,
        seed=args.seed,
        report_to=args.report_to,
        run_name=args.wandb_run_name,
        use_vllm=False,  # never use vllm on Windows; rely on HF generate()
    )

    # Load base model with proven bnb 4-bit single-GPU config (memory mrga01ofns8)
    # AutoModelForImageTextToText handles Qwen3-VL; falls back to CausalLM for text-only.
    from transformers import AutoConfig as _AutoConfig

    try:
        from transformers import AutoModelForImageTextToText as _AutoModel

        _is_vl = True
    except ImportError:
        from transformers import AutoModelForCausalLM as _AutoModel  # type: ignore[assignment]

        _is_vl = False
    _cfg = _AutoConfig.from_pretrained(args.model)
    _is_vl = _is_vl or "VL" in type(_cfg).__name__ or "vl" in args.model.lower()
    if not _is_vl:
        from transformers import AutoModelForCausalLM as _AutoModel  # type: ignore[assignment]
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    model = _AutoModel.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map={"": 0},  # skip infer_auto_device_map (avoids CPU-dispatch ValueError)
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
        # Qwen3-VL + transformers 4.57 has a known SDPA attention-mask shape bug
        # (RuntimeError: Expected key.size(1) == value.size(1)) during GRPO.
        # 'eager' attention avoids the fused sdpa path that triggers it.
        attn_implementation="eager",
    )
    model.config.use_cache = False
    logger.info("Loaded base model: %s (%s, VL=%s)", args.model, type(model).__name__, _is_vl)

    # GRPOTrainer.__init__ sets model.warnings_issued[...] on the wrapped
    # PeftModel; for VL models that don't have it, set the dict manually so
    # the attribute access succeeds after get_peft_model wrapping.
    if not hasattr(model, "warnings_issued"):
        model.warnings_issued = {}  # type: ignore[assignment]
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=list(FASHION_REWARD_FUNCS),
        args=training_args,
        train_dataset=dataset,
        peft_config=peft_config,
    )
    logger.info(
        "Starting GRPO training: model=%s, steps=%d, G=%d",
        args.model,
        args.max_steps,
        args.num_generations,
    )
    trainer.train()

    trainer.save_model(args.output_dir)
    logger.info("Saved LoRA adapter to %s", args.output_dir)
    if args.push_to_hub:
        trainer.model.push_to_hub(args.push_to_hub)
        logger.info("Pushed adapter to HF Hub: %s", args.push_to_hub)


if __name__ == "__main__":
    main()
