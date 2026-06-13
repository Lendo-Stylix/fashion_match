"""Run local inference with the fine-tuned Qwen3-VL-8B stylist adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

DEFAULT_ADAPTER_REPO_ID = "Nhat-Quang/outfitmatch-stylist-qwen3vl8b-lora"
DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_SYSTEM_PROMPT = (
    "Bạn là AI stylist tiếng Việt của OutfitMatch cho thị trường Việt Nam. "
    "Nếu có ảnh thì tận dụng ảnh để phân tích item/phối đồ; nếu không có ảnh thì chỉ dùng text."
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="User prompt to send to the model.")
    parser.add_argument("--image-path", help="Optional local image path for multimodal prompting.")
    parser.add_argument("--adapter-repo", default=DEFAULT_ADAPTER_REPO_ID)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL_ID)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--load-in-4bit", action="store_true")
    return parser


def build_messages(
    *,
    system_prompt: str,
    prompt: str,
    image_path: Path | None,
) -> list[dict[str, Any]]:
    """Build a Qwen3-VL chat conversation with optional image."""
    user_content: list[dict[str, str]] = []
    if image_path is not None:
        user_content.append({"type": "image", "image": str(image_path)})
    user_content.append({"type": "text", "text": prompt})
    return [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        {"role": "user", "content": user_content},
    ]


def load_model_and_processor(args: argparse.Namespace) -> tuple[Any, Any]:
    """Load base VL model + PEFT adapter for inference."""
    quantization_config = None
    if args.load_in_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

    processor = AutoProcessor.from_pretrained(args.adapter_repo, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        quantization_config=quantization_config,
    )
    model = PeftModel.from_pretrained(model, args.adapter_repo)
    model.eval()
    return model, processor


def generate_response(args: argparse.Namespace) -> str:
    """Generate one stylist response."""
    model, processor = load_model_and_processor(args)
    model_device = next(model.parameters()).device
    image_path = Path(args.image_path) if args.image_path else None
    messages = build_messages(
        system_prompt=args.system_prompt,
        prompt=args.prompt,
        image_path=image_path,
    )
    rendered = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    image_inputs = None
    if image_path is not None:
        with Image.open(image_path) as image:
            image_inputs = [image.convert("RGB")]
            inputs = processor(text=[rendered], images=image_inputs, return_tensors="pt")
    else:
        inputs = processor(text=[rendered], images=None, return_tensors="pt")
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
    return processor.batch_decode([completion], skip_special_tokens=True)[0].strip()


def main() -> None:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    print(generate_response(args))


if __name__ == "__main__":
    main()
