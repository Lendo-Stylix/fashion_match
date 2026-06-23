"""Generate grounded stylist ChatML examples from a scenario bank."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
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


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _user_request_text(scenario: dict[str, Any]) -> str:
    request = scenario["request"]
    style = request.get("style")
    budget = request.get("price_max")
    occasion = request.get("occasion") or scenario.get("target_occasion")
    if scenario["task_type"] == "ask_missing_info_grounded":
        return "Mình muốn phối đồ đẹp hơn nhưng chưa chắc nên mặc vào dịp nào."
    if scenario["task_type"] == "no_result_or_relax_constraints":
        return (
            f"Mình cần outfit đi {occasion} nhưng ngân sách chỉ khoảng {budget:,}đ thôi.".replace(
                ",", "."
            )
        )
    if scenario["task_type"] == "polite_decline_anti_hallucination":
        return (
            "Bạn kiểm tra giúp outfit "
            f"{request['requested_outfit_id']} có còn không và chốt luôn cho mình nhé."
        )
    if scenario["task_type"] == "multi_turn_grounded":
        return "Mình cần một outfit dễ mặc nhưng chưa biết nên ưu tiên dịp nào."
    if scenario["task_type"] == "body_fit_grounded":
        return (
            f"Mình muốn outfit đi {occasion} hợp dáng {request['body_shape']} "
            f"và phong cách {style}."
        )
    if scenario["task_type"] == "recommend_explain_grounded":
        return f"Gợi ý giúp mình outfit đi {occasion} và giải thích vì sao hợp nhé."
    return (
        f"Mình cần outfit đi {occasion}, phong cách {style}, ngân sách tối đa {budget:,}đ.".replace(
            ",", "."
        )
    )


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
            "Mình có thể tư vấn chính xác hơn nếu bạn cho biết dịp mặc chính, "
            "ví dụ đi làm, đi chơi hay du lịch."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": question}]

    if task_type == "no_result_or_relax_constraints":
        answer = (
            f"Hiện mình chưa thấy item phù hợp dưới mức {request['price_max']:,}đ "
            f"cho dịp {request['occasion']}. "
            "Bạn có thể tăng ngân sách hoặc nới lỏng màu/phong cách để mình tìm thêm lựa chọn."
        ).replace(",", ".")
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    if task_type == "recommend_explain_grounded":
        picks = "; ".join(_format_candidate(item) for item in candidate_items[:3])
        answer = (
            f"Mình ưu tiên {seed_item.get('title_vi', 'mẫu chính')} "
            f"vì hợp dịp {request['occasion']} và dễ phối. "
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
            "Bạn cho mình biết dịp chính nhé, ví dụ đi làm hay du lịch, để mình lọc đúng outfit."
        )
        resolved_request = {**request, "occasion": scenario["target_occasion"]}
        tool_call = render_search_outfits_tool_call(resolved_request)
        return [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": follow_up},
            {"role": "user", "content": f"Ưu tiên dịp {scenario['target_occasion']} nhé."},
            {"role": "assistant", "content": tool_call},
        ]

    if task_type == "body_fit_grounded":
        answer = (
            f"{seed_item.get('title_vi', 'Item này')} là lựa chọn ổn "
            f"vì phom {seed_item.get('category', 'item')} dễ cân bằng "
            f"cho dáng {request['body_shape']} trong bối cảnh {request['occasion']}."
        )
        return [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]

    raise ValueError(f"Unsupported task_type: {task_type}")


def _call_openai_compatible(prompt_messages: list[dict[str, str]], *, model: str) -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8087/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": prompt_messages,
        "temperature": 0.2,
        "max_tokens": 600,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - live backend path
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible HTTP {exc.code}: {detail}") from exc
    choices = response_payload.get("choices") or []
    if not choices:
        raise ValueError("OpenAI-compatible response had no choices")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenAI-compatible response returned no text payload")
    return content


def generate_dialogues_from_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    backend: str = "template",
    model: str | None = None,
    source_file: str = "scenario_bank.jsonl",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        messages = [{"role": "system", "content": system_prompt}]
        if backend == "template":
            messages.extend(_template_assistant_messages(scenario))
        elif backend == "openai-compatible":
            if not model:
                raise ValueError("model is required for openai-compatible backend")
            draft_messages = _template_assistant_messages(scenario)
            prompt_messages = (
                messages
                + draft_messages[:-1]
                + [
                    {
                        "role": "user",
                        "content": (
                            "Viết lại câu trả lời assistant ngắn gọn, bám đúng dữ liệu có sẵn "
                            "và giữ nguyên tool_call nếu có."
                        ),
                    }
                ]
            )
            rewritten = _call_openai_compatible(prompt_messages, model=model)
            messages.extend(draft_messages[:-1])
            messages.append({"role": "assistant", "content": rewritten})
        else:
            raise ValueError(f"Unsupported backend: {backend}")
        rows.append(
            {
                "messages": messages,
                "task_type": str(scenario["task_type"]),
                "source_set": "grounded_generated",
                "source_file": source_file,
                "scenario_id": str(scenario["scenario_id"]),
            }
        )
    return rows


def write_generated_dialogues(output_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    train_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "total_examples": len(rows),
        "task_counts": dict(sorted(Counter(str(row["task_type"]) for row in rows).items())),
        "train_file": str(train_path),
    }
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
    )
    result = write_generated_dialogues(args.output_dir, rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
