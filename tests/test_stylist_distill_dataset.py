from __future__ import annotations

import json
from pathlib import Path

from scripts.stylist.distill_stylist_dataset import (
    BEHAVIORAL_TASKS,
    ChatExample,
    build_distilled_bundle,
    distill_knowledge_examples,
    inspect_example_quality,
    synthesize_behavioral_examples,
)

SYSTEM_PROMPT = "Bạn là stylist thử nghiệm."


def _example(user_text: str, assistant_text: str) -> ChatExample:
    return ChatExample(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ],
        task_type="stylist_knowledge",
        source_set="stylist_knowledge",
        source_file="mock.csv",
    )


def test_distill_knowledge_examples_limits_near_duplicates_and_keeps_coverage() -> None:
    examples = [
        _example(
            "Làm thế nào để chọn một chiếc áo blazer bất hủ cho công sở?",
            "Hãy ưu tiên vai gọn, màu trung tính và chất liệu đứng form.",
        ),
        _example(
            "Làm thế nào để chọn một chiếc áo blazer bất hủ cho cuối tuần?",
            "Hãy ưu tiên blazer mềm, dễ phối cùng quần jeans hoặc chân váy.",
        ),
        _example(
            "Làm thế nào để chọn một chiếc áo blazer bất hủ cho mùa thu?",
            "Hãy chọn blazer dệt chặt, có thể mặc nhiều lớp nhưng không quá dày.",
        ),
        _example(
            "Làm sao xác định tông da để chọn màu quần áo phù hợp?",
            "Quan sát undertone và thử các nhóm màu ấm, lạnh, trung tính.",
        ),
        _example(
            "Cách giặt áo lụa để giữ bề mặt mịn và bền lâu?",
            "Giặt tay nhẹ bằng nước mát, tránh vắt mạnh và phơi râm.",
        ),
        _example(
            "Tôi nên mặc gì khi đi đám cưới ngoài trời buổi chiều?",
            "Ưu tiên trang phục thanh lịch, chất liệu thoáng và giày đi êm chân.",
        ),
    ]

    distilled = distill_knowledge_examples(examples, target_size=4, seed=7, max_per_family=1)
    users = [example.messages[1]["content"].lower() for example in distilled]

    assert len(distilled) == 4
    assert sum("áo blazer bất hủ" in user for user in users) == 1
    assert any("tông da" in user for user in users)
    assert any("lụa" in user for user in users)
    assert any("đám cưới" in user for user in users)


def test_synthesize_behavioral_examples_covers_required_task_types() -> None:
    seeds = [
        _example(
            "Làm sao chọn màu áo hợp undertone ấm?",
            "Hãy ưu tiên các tông màu đất, kem, nâu ấm và xanh olive.",
        ),
        _example(
            "Tôi muốn xây tủ đồ tối giản để đi làm mỗi ngày.",
            "Bắt đầu với blazer, quần suông, sơ mi trơn và giày dễ phối.",
        ),
    ]

    behavioral = synthesize_behavioral_examples(
        seeds,
        system_prompt=SYSTEM_PROMPT,
        counts_by_task={task: 1 for task in BEHAVIORAL_TASKS},
        seed=11,
    )

    assert {example.task_type for example in behavioral} == set(BEHAVIORAL_TASKS)

    multi_turn = next(example for example in behavioral if example.task_type == "multi_turn")
    assert [message["role"] for message in multi_turn.messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    tool_calling = next(example for example in behavioral if example.task_type == "tool_calling")
    tool_response = tool_calling.messages[-1]["content"]
    assert "search_outfits" in tool_response
    assert '"occasion"' in tool_response


def test_synthesize_behavioral_examples_repeated_tasks_stay_unique() -> None:
    seeds = [
        _example(
            "Làm sao chọn màu áo hợp undertone ấm?",
            "Hãy ưu tiên các tông màu đất, kem, nâu ấm và xanh olive.",
        ),
    ]

    behavioral = synthesize_behavioral_examples(
        seeds,
        system_prompt=SYSTEM_PROMPT,
        counts_by_task={"polite_decline": 3, "edge_case": 3},
        seed=17,
    )

    signatures = {
        json.dumps(example.messages, ensure_ascii=False, sort_keys=True) for example in behavioral
    }
    assert len(behavioral) == 6
    assert len(signatures) == 6


def test_build_distilled_bundle_writes_expected_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "stylist_knowledge"
    output_dir = tmp_path / "distilled"
    source_dir.mkdir(parents=True)
    (source_dir / "knowledge.csv").write_text(
        "original_input,original_output,translated_input,translated_output\n"
        "A,B,Làm sao phối sơ mi trắng?,Phối với quần suông và giày loafers.\n"
        "A,B,Làm sao phối sơ mi trắng cho công sở?,Thêm blazer và túi dáng cứng để chỉn chu hơn.\n"
        "A,B,Cách giặt áo len?,Giặt tay nhẹ và phơi ngang để giữ form.\n",
        encoding="utf-8",
    )

    manifest = build_distilled_bundle(
        source_dir=source_dir,
        output_dir=output_dir,
        system_prompt=SYSTEM_PROMPT,
        knowledge_target=2,
        seed=5,
        max_per_family=1,
        counts_by_task={"ask_missing_info": 1, "tool_calling": 1},
    )

    assert manifest["knowledge_examples"] == 2
    assert manifest["behavioral_examples"] == 2
    assert manifest["combined_examples"] == 4
    assert (output_dir / "knowledge_distilled.jsonl").exists()
    assert (output_dir / "behavioral_synthetic.jsonl").exists()
    assert (output_dir / "train.jsonl").exists()
    assert (output_dir / "manifest.json").exists()

    rows = [
        json.loads(line)
        for line in (output_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 4
    assert {row["task_type"] for row in rows} >= {
        "stylist_knowledge",
        "ask_missing_info",
        "tool_calling",
    }


def test_inspect_example_quality_flags_mixed_script_and_overlong_rows() -> None:
    weird = _example(
        "Làm thế nào để phối cardigan cho công sở?",
        "Bạn có thể mặc cardigan поверх áo sơ mi để trông gọn gàng và chuyên nghiệp.",
    )
    long_answer = _example(
        "Tôi nên xây tủ đồ cơ bản thế nào?",
        " ".join(["chi tiết"] * 281),
    )

    weird_quality = inspect_example_quality(weird, max_answer_words=280, echo_threshold=0.65)
    long_quality = inspect_example_quality(long_answer, max_answer_words=280, echo_threshold=0.65)

    assert "mixed_script" in weird_quality.flags
    assert "too_long" in long_quality.flags
