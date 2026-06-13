"""Run local inference with the fine-tuned Qwen3.5-9B stylist adapter."""

from __future__ import annotations

import argparse
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DEFAULT_ADAPTER_REPO_ID = "Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora"
DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3.5-9B"
DEFAULT_SYSTEM_PROMPT = (
    "Bạn là AI stylist tiếng Việt của OutfitMatch cho thị trường Việt Nam. "
    "Trả lời ngắn gọn, thực tế, ưu tiên gợi ý dễ mặc và phù hợp khí hậu Việt Nam."
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="User prompt to send to the model.")
    parser.add_argument("--adapter-repo", default=DEFAULT_ADAPTER_REPO_ID)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL_ID)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--load-in-4bit", action="store_true")
    return parser


def build_messages(system_prompt: str, prompt: str) -> list[dict[str, str]]:
    """Build a text-only chat conversation."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]


def load_model_and_tokenizer(args: argparse.Namespace) -> tuple[Any, Any]:
    """Load base model + PEFT adapter for inference."""
    quantization_config = None
    if args.load_in_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

    tokenizer = AutoTokenizer.from_pretrained(args.adapter_repo, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        quantization_config=quantization_config,
    )
    model = PeftModel.from_pretrained(model, args.adapter_repo)
    model.eval()
    return model, tokenizer


def generate_response(args: argparse.Namespace) -> str:
    """Generate one stylist response."""
    model, tokenizer = load_model_and_tokenizer(args)
    model_device = next(model.parameters()).device
    messages = build_messages(args.system_prompt, args.prompt)
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(rendered, return_tensors="pt")
    inputs = {name: tensor.to(model_device) for name, tensor in inputs.items()}

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            do_sample=args.temperature > 0,
        )

    prompt_tokens = inputs["input_ids"].shape[1]
    completion = generated[0][prompt_tokens:]
    return tokenizer.decode(completion, skip_special_tokens=True).strip()


def main() -> None:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    print(generate_response(args))


if __name__ == "__main__":
    main()
