"""Generate grounded stylist ChatML examples from a scenario bank."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution path
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    src_root_str = str(repo_root / "src")
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)

from outfitmatch.stylist.tools import render_search_outfits_tool_call

DEFAULT_SYSTEM_PROMPT = (
    "Bạn là stylist của OutfitMatch. Chỉ tư vấn dựa trên dữ liệu catalog và "
    "nếu cần tìm outfit thì phải gọi đúng tool search_outfits."
)
DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_grounded_v2/generated_dialogues")
DEFAULT_ENV_FILE = Path(".env.local")
DEFAULT_OPENAI_BASE_URL = "http://127.0.0.1:8087/v1"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
ZAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
THINK_BLOCK_RE = re.compile(r"<(?:think|thinking)[^>]*>.*?</(?:think|thinking)>", re.DOTALL)
NVIDIA_MODELS = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3-ultra-550b-a55b",
}
ZAI_MODELS = {
    "glm-4.5-flash",
    "glm-4.7-flash",
    "zai/glm-4.5-flash",
    "zai/glm-4.7-flash",
}


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _profile_text(scenario: dict[str, Any]) -> str:
    profile = scenario.get("user_profile") or {}
    height_cm = int(profile.get("height_cm") or 0)
    weight_kg = int(profile.get("weight_kg") or 0)
    return f"mình cao {height_cm}cm, nặng {weight_kg}kg"


def _user_request_text(scenario: dict[str, Any]) -> str:
    request = scenario["request"]
    style = request.get("style")
    budget = request.get("price_max")
    occasion = request.get("occasion") or scenario.get("target_occasion")
    profile_text = _profile_text(scenario)
    seed_title = (scenario.get("seed_item") or {}).get("title_vi") or "item này"
    scenario_id = scenario.get("scenario_id", "")
    if scenario["task_type"] == "ask_missing_info_grounded":
        return (
            f"{profile_text}, thích phong cách {style}, đang xem {seed_title} "
            f"với ngân sách khoảng {budget:,}đ [{scenario_id}] nhưng chưa chắc nên mặc vào dịp nào."
        ).replace(",", ".")
    if scenario["task_type"] == "no_result_or_relax_constraints":
        return (
            f"{profile_text}, mình cần outfit đi {occasion}, thích phong cách {style} "
            f"nhưng ngân sách chỉ khoảng {budget:,}đ [{scenario_id}] thôi."
        ).replace(",", ".")
    if scenario["task_type"] == "polite_decline_anti_hallucination":
        return (
            f"{profile_text}, bạn kiểm tra giúp outfit "
            f"{request['requested_outfit_id']} [{scenario_id}] "
            "có còn không và chốt luôn cho mình nhé."
        )
    if scenario["task_type"] == "multi_turn_grounded":
        return (
            f"{profile_text}, mình cần một outfit dễ mặc, nghiêng về phong cách {style} "
            f"với ngân sách khoảng {budget:,}đ [{scenario_id}] nhưng chưa biết nên ưu tiên dịp nào."
        ).replace(",", ".")
    if scenario["task_type"] == "body_fit_grounded":
        return (
            f"{profile_text}, mình muốn outfit đi {occasion} hợp dáng {request['body_shape']} "
            f"và phong cách {style}, ưu tiên item như {seed_title} [{scenario_id}]."
        )
    if scenario["task_type"] == "recommend_explain_grounded":
        return (
            f"{profile_text}, gợi ý giúp mình outfit đi {occasion}, nghiêng về {style}, "
            f"ưu tiên {seed_title} [{scenario_id}] và giải thích vì sao hợp nhé."
        )
    return (
        f"{profile_text}, mình cần outfit đi {occasion}, phong cách {style}, "
        f"ngân sách tối đa {budget:,}đ [{scenario_id}]."
    ).replace(",", ".")


def _format_candidate(candidate: dict[str, Any]) -> str:
    colors = ", ".join(candidate.get("colors") or []) or "màu trung tính"
    price_vnd = int(candidate.get("price_vnd") or 0)
    return f"{candidate['title_vi']} ({colors}, {price_vnd:,}đ)".replace(",", ".")


def _template_assistant_messages(
    scenario: dict[str, Any],
) -> list[dict[str, str]]:
    request = dict(scenario["request"])
    task_type = scenario["task_type"]
    seed_item = scenario.get("seed_item") or {}
    candidate_items = scenario.get("candidate_items") or []
    user_text = _user_request_text(scenario)

    if task_type == "tool_calling_grounded":
        tool_call = render_search_outfits_tool_call(request)
        return [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": tool_call},
        ]

    if task_type == "ask_missing_info_grounded":
        question = (
            f"Mình có thể tư vấn chính xác hơn cho phong cách {request['style']} "
            "nếu bạn cho biết dịp mặc chính, ví dụ đi làm, đi chơi hay du lịch."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": question}]

    if task_type == "no_result_or_relax_constraints":
        answer = (
            f"Hiện mình chưa thấy item phù hợp dưới mức {request['price_max']:,}đ "
            f"cho dịp {request['occasion']} theo phong cách {request['style']}. "
            "Bạn có thể tăng ngân sách hoặc nới lỏng màu/phong cách để mình tìm thêm lựa chọn."
        ).replace(",", ".")
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    if task_type == "recommend_explain_grounded":
        picks = "; ".join(_format_candidate(item) for item in candidate_items[:3])
        answer = (
            f"Mình ưu tiên {seed_item.get('title_vi', 'mẫu chính')} "
            f"vì hợp dịp {request['occasion']}, đúng tinh thần {request['style']} và dễ phối. "
            f"Các lựa chọn nền tảng trong catalog hiện có: {picks}."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    if task_type == "polite_decline_anti_hallucination":
        answer = (
            "Mình chưa thể xác nhận một outfit_id không có trong dữ liệu đã truy xuất. "
            "Nếu bạn muốn, mình sẽ tìm lại outfit thật từ catalog theo dịp và ngân sách hiện có."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    if task_type == "multi_turn_grounded":
        follow_up = (
            f"Bạn cho mình biết dịp chính nhé. Với phong cách {request['style']}, "
            "mình sẽ lọc chính xác hơn khi biết là đi làm, đi chơi hay du lịch."
        )
        resolved_request = {**request, "occasion": scenario["target_occasion"]}
        tool_call = render_search_outfits_tool_call(resolved_request)
        return [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": follow_up},
            {
                "role": "user",
                "content": (
                    f"Ưu tiên dịp {scenario['target_occasion']} nhé, mình vẫn giữ ngân sách "
                    f"{request['price_max']:,}đ."
                ).replace(",", "."),
            },
            {"role": "assistant", "content": tool_call},
        ]

    if task_type == "body_fit_grounded":
        answer = (
            f"{seed_item.get('title_vi', 'Item này')} là lựa chọn ổn "
            f"vì phom {seed_item.get('category', 'item')} dễ cân bằng "
            f"cho dáng {request['body_shape']} trong bối cảnh {request['occasion']} "
            f"và vẫn giữ tinh thần {request['style']}."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    raise ValueError(f"Unsupported task_type: {task_type}")


def _api_model_name(model: str) -> str:
    if model.startswith("zai/"):
        return model.split("/", 1)[1]
    return model


def _resolve_client_config(
    model: str,
    *,
    base_url_override: str | None = None,
    api_key_override: str | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
) -> tuple[str, str, str]:
    _load_env_file(env_file)
    if base_url_override and api_key_override:
        return base_url_override.rstrip("/"), api_key_override, _api_model_name(model)
    if model in NVIDIA_MODELS or model.startswith("openai/gpt-oss") or model.startswith("nvidia/"):
        api_key = api_key_override or _env_first(
            "NVIDIA_API_KEY",
            "NVIDIA_NIM_API_TOKEN",
            "NIVIDIA_NIM_API_TOKEN",
        )
        if not api_key:
            raise ValueError("Missing NVIDIA API key (NVIDIA_API_KEY / NVIDIA_NIM_API_TOKEN)")
        base_url = (base_url_override or os.getenv("NVIDIA_BASE_URL") or NVIDIA_BASE_URL).rstrip(
            "/"
        )
        return base_url, api_key, _api_model_name(model)
    if model in ZAI_MODELS or model.startswith("glm-") or model.startswith("zai/"):
        api_key = api_key_override or _env_first("ZAI_API_TOKEN", "ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("Missing ZAI API key (ZAI_API_TOKEN / ZHIPU_API_KEY)")
        base_url = (base_url_override or os.getenv("ZAI_BASE_URL") or ZAI_BASE_URL).rstrip("/")
        return base_url, api_key, _api_model_name(model)
    base_url = (
        base_url_override or os.getenv("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
    ).rstrip("/")
    api_key = api_key_override or os.getenv("OPENAI_API_KEY", "")
    if not api_key and not base_url_override:
        raise ValueError("Missing OPENAI_API_KEY for generic openai-compatible backend")
    return base_url, api_key, _api_model_name(model)


def _extract_message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for item in message:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _strip_reasoning(content: str) -> str:
    return THINK_BLOCK_RE.sub("", content).strip()


def _chat_completion_request(
    prompt_messages: list[dict[str, str]],
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float = 0.2,
    max_tokens: int = 600,
    timeout: int = 300,
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    effective_max_tokens = max_tokens
    if model.startswith("glm-") and effective_max_tokens < 1400:
        effective_max_tokens = 1400
    payload = {
        "model": model,
        "messages": prompt_messages,
        "temperature": temperature,
        "max_tokens": effective_max_tokens,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - live backend path
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible HTTP {exc.code}: {detail}") from exc
    choices = response_payload.get("choices") or []
    if not choices:
        raise ValueError("OpenAI-compatible response had no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    content = _extract_message_text(message.get("content"))
    content = _strip_reasoning(content)
    if not content:
        reasoning = _extract_message_text(message.get("reasoning_content"))
        finish_reason = choice.get("finish_reason")
        if reasoning and finish_reason == "length":
            raise ValueError(
                "OpenAI-compatible response exhausted tokens in reasoning before final content"
            )
        raise ValueError("OpenAI-compatible response returned no text payload")
    return content


def _grounding_summary(scenario: dict[str, Any]) -> str:
    request = scenario["request"]
    seed_item = scenario.get("seed_item") or {}
    candidate_items = scenario.get("candidate_items") or []
    candidates = "; ".join(_format_candidate(item) for item in candidate_items[:5]) or "(không có)"
    return "\n".join(
        [
            f"task_type: {scenario['task_type']}",
            f"request: {json.dumps(request, ensure_ascii=False, sort_keys=True)}",
            f"seed_item: {json.dumps(seed_item, ensure_ascii=False, sort_keys=True)}",
            f"candidate_items: {candidates}",
        ]
    )


def _rewrite_prompt_messages(
    scenario: dict[str, Any],
    *,
    system_prompt: str,
) -> list[dict[str, str]]:
    draft_messages = _template_assistant_messages(scenario)
    task_type = scenario["task_type"]
    final_target = draft_messages[-1]["content"]
    if task_type == "tool_calling_grounded":
        instruction = (
            "Bạn đang tạo dữ liệu SFT grounded cho stylist. "
            "Dữ liệu đã có đủ occasion/style/budget nên assistant PHẢI "
            "trả về đúng 1 block tool_call, không thêm giải thích, "
            "không thêm markdown, không đổi schema."
        )
    elif task_type == "multi_turn_grounded":
        instruction = (
            "Bạn chỉ viết lại assistant ở TURN 1 theo tiếng Việt tự nhiên, "
            "ngắn gọn, giữ đúng intent hỏi thêm dịp mặc. TURN cuối vẫn là "
            "tool_call chuẩn nên không được động tới."
        )
    else:
        instruction = (
            "Viết lại câu trả lời assistant bằng tiếng Việt tự nhiên, "
            "ngắn gọn 1-3 câu, bám đúng dữ liệu grounded, không bịa thêm "
            "item/outfit/thuộc tính ngoài prompt."
        )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"{instruction}\n\n"
                f"Grounding:\n{_grounding_summary(scenario)}\n\n"
                f"User message: {draft_messages[0]['content']}\n\n"
                f"Current target draft: {final_target}"
            ),
        },
    ]


def _render_openai_compatible_messages(
    scenario: dict[str, Any],
    *,
    system_prompt: str,
    model: str,
    base_url_override: str | None,
    api_key_override: str | None,
    env_file: Path,
    max_retries: int,
) -> list[dict[str, str]]:
    base_url, api_key, api_model = _resolve_client_config(
        model,
        base_url_override=base_url_override,
        api_key_override=api_key_override,
        env_file=env_file,
    )
    request = dict(scenario["request"])
    task_type = scenario["task_type"]
    draft_messages = _template_assistant_messages(scenario)
    prompt_messages = _rewrite_prompt_messages(scenario, system_prompt=system_prompt)
    rewritten: str | None = None
    last_error: Exception | None = None
    for _attempt in range(max_retries):
        try:
            rewritten = _chat_completion_request(
                prompt_messages,
                model=api_model,
                base_url=base_url,
                api_key=api_key,
            )
            break
        except Exception as exc:  # pragma: no cover - live backend path
            last_error = exc
            time.sleep(1)
    if rewritten is None:
        raise RuntimeError(f"LLM generation failed for task_type={task_type}") from last_error
    if task_type == "multi_turn_grounded":
        resolved_request = {**request, "occasion": scenario["target_occasion"]}
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": draft_messages[0]["content"]},
            {"role": "assistant", "content": _normalize_assistant_output(task_type, rewritten)},
            draft_messages[2],
            {"role": "assistant", "content": render_search_outfits_tool_call(resolved_request)},
        ]
    return [
        {"role": "system", "content": system_prompt},
        draft_messages[0],
        {"role": "assistant", "content": _normalize_assistant_output(task_type, rewritten)},
    ]


def _normalize_assistant_output(task_type: str, content: str) -> str:
    stripped = content.strip()
    if task_type == "tool_calling_grounded":
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return f"<tool_call>{stripped}</tool_call>"
    return stripped


def _build_row(
    scenario: dict[str, Any],
    *,
    messages: list[dict[str, str]],
    source_file: str,
) -> dict[str, Any]:
    return {
        "messages": messages,
        "task_type": str(scenario["task_type"]),
        "source_set": "grounded_generated",
        "source_file": source_file,
        "scenario_id": str(scenario["scenario_id"]),
    }


def generate_dialogues_from_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    backend: str = "template",
    model: str | None = None,
    source_file: str = "scenario_bank.jsonl",
    base_url_override: str | None = None,
    api_key_override: str | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
    max_workers: int = 1,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    if backend == "template":
        return [
            _build_row(
                scenario,
                messages=[{"role": "system", "content": system_prompt}]
                + _template_assistant_messages(scenario),
                source_file=source_file,
            )
            for scenario in scenarios
        ]
    if backend != "openai-compatible":
        raise ValueError(f"Unsupported backend: {backend}")
    if not model:
        raise ValueError("model is required for openai-compatible backend")

    def _run_one(index: int, scenario: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        messages = _render_openai_compatible_messages(
            scenario,
            system_prompt=system_prompt,
            model=model,
            base_url_override=base_url_override,
            api_key_override=api_key_override,
            env_file=env_file,
            max_retries=max_retries,
        )
        return index, _build_row(scenario, messages=messages, source_file=source_file)

    if max_workers <= 1:
        return [_run_one(index, scenario)[1] for index, scenario in enumerate(scenarios)]

    ordered_rows: list[dict[str, Any] | None] = [None] * len(scenarios)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_run_one, index, scenario) for index, scenario in enumerate(scenarios)
        ]
        for future in as_completed(futures):
            index, row = future.result()
            ordered_rows[index] = row
    return [row for row in ordered_rows if row is not None]


def _message_signatures(rows: list[dict[str, Any]]) -> set[str]:
    return {json.dumps(row["messages"], ensure_ascii=False, sort_keys=True) for row in rows}


def _assistant_turns(row: dict[str, Any]) -> list[str]:
    return [
        str(message.get("content", ""))
        for message in row.get("messages", [])
        if message.get("role") == "assistant"
    ]


def build_generation_manifest(rows: list[dict[str, Any]], train_path: Path) -> dict[str, Any]:
    signatures = _message_signatures(rows)
    turn_counts = [len(row["messages"]) for row in rows]
    tool_rows = 0
    for row in rows:
        assistant_text = "\n".join(_assistant_turns(row))
        if "<tool_call>" in assistant_text:
            tool_rows += 1
    return {
        "total_examples": len(rows),
        "task_counts": dict(sorted(Counter(str(row["task_type"]) for row in rows).items())),
        "unique_message_examples": len(signatures),
        "duplicate_message_examples": len(rows) - len(signatures),
        "tool_call_rows": tool_rows,
        "avg_turns": round(sum(turn_counts) / len(turn_counts), 2) if turn_counts else 0.0,
        "max_turns": max(turn_counts, default=0),
        "train_file": str(train_path),
    }


def write_generated_dialogues(output_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    train_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest = build_generation_manifest(rows, train_path)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_bank", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--backend",
        choices=["template", "openai-compatible"],
        default="template",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = load_scenarios(args.scenario_bank)
    rows = generate_dialogues_from_scenarios(
        scenarios,
        system_prompt=args.system_prompt,
        backend=args.backend,
        model=args.model,
        source_file=args.scenario_bank.name,
        base_url_override=args.base_url,
        api_key_override=args.api_key,
        env_file=args.env_file,
        max_workers=args.max_workers,
        max_retries=args.max_retries,
    )
    result = write_generated_dialogues(args.output_dir, rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
