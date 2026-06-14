from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.stylist.prepare_stylist_qlora_kaggle import (
    build_package,
    load_config,
    validate_config,
)


def test_kaggle_qlora_config_enforces_user_constraints() -> None:
    config = load_config(Path("configs/stylist_finetune_kaggle.yaml"))

    assert config["dataset"]["source_mode"] == "stylist_knowledge_only"
    assert set(config["secrets"]["allowed_hf_token_env_vars"]) == {
        "HF_API_TOKEN_2",
        "HF_API_TOKEN_3",
    }
    assert "HF_API_TOKEN_1" in config["secrets"]["forbidden_hf_token_env_vars"]
    assert config["training"]["framework"] == "unsloth"
    assert config["training"]["strategy"] == "qlora_sft"
    assert config["training"]["max_session_steps"] == 1000
    assert config["training"]["wandb"]["kaggle_secret_name"] == "WANDB_API_KEY"
    assert config["kaggle"]["machine_shape"] == "NvidiaTeslaT4x2"
    assert {model["hf_token_env"] for model in config["models"]} <= {
        "HF_API_TOKEN_2",
        "HF_API_TOKEN_3",
    }


def test_validate_config_rejects_hf_token_1() -> None:
    config = load_config(Path("configs/stylist_finetune_kaggle.yaml"))
    config["models"][0] = dict(config["models"][0], hf_token_env="HF_API_TOKEN_1")

    with pytest.raises(ValueError, match="disallowed token"):
        validate_config(config)


def test_build_package_normalizes_only_stylist_knowledge(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "stylist_knowledge"
    ignored_user_dir = tmp_path / "users_query_and_response"
    resume_root = tmp_path / "resume_seed"
    resume_checkpoint = resume_root / "checkpoint-123"
    package_root = tmp_path / "runs" / "kaggle_qlora"
    knowledge_dir.mkdir(parents=True)
    ignored_user_dir.mkdir(parents=True)
    resume_checkpoint.mkdir(parents=True)
    (knowledge_dir / "knowledge.csv").write_text(
        "original_input,original_output,translated_input,translated_output\n"
        "Which fabric?,Cotton is breathable.,Vải nào?,Cotton thoáng khí.\n",
        encoding="utf-8",
    )
    (ignored_user_dir / "ignored.csv").write_text(
        "translated_input,translated_output\nKhông dùng,Tuyệt đối không xuất hiện\n",
        encoding="utf-8",
    )
    (resume_checkpoint / "trainer_state.json").write_text(
        json.dumps({"global_step": 123}),
        encoding="utf-8",
    )

    config = load_config(Path("configs/stylist_finetune_kaggle.yaml"))
    config["dataset"]["stylist_knowledge_dir"] = str(knowledge_dir)
    config["dataset"]["users_query_response_dir"] = str(ignored_user_dir)
    config["dataset"]["max_eval_records"] = 1
    config["training"]["resume_checkpoint"] = {
        "local_path": str(resume_root),
        "packaged_subdir": "resume_checkpoint",
    }
    config["outputs"]["package_root"] = str(package_root)
    config["outputs"]["manifest"] = str(package_root / "manifest.json")
    config_path = tmp_path / "config.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    manifest = build_package(config_path, clean=True, push=False)
    assert manifest["dataset"]["total_examples"] == 1
    assert manifest["dataset"]["eval_examples"] == 1
    assert len(manifest["kernels"]) == 3
    assert manifest["resume_checkpoint"] == {
        "local_path": str(resume_checkpoint),
        "dataset_subdir": "resume_checkpoint",
        "checkpoint_dir": "checkpoint-123",
    }

    eval_text = (package_root / "kaggle_dataset" / "eval.jsonl").read_text(encoding="utf-8")
    eval_row = json.loads(eval_text)
    assert eval_row["messages"][1]["content"] == "Vải nào?"
    assert eval_row["messages"][2]["content"] == "Cotton thoáng khí."
    assert "Tuyệt đối không xuất hiện" not in eval_text
    assert (
        package_root
        / "kaggle_dataset"
        / "resume_checkpoint"
        / "checkpoint-123"
        / "trainer_state.json"
    ).is_file()

    kernel_path = package_root / "kaggle_kernel_qwen3vl8b-instruct" / "train_qwen3vl8b-instruct.py"
    kernel_text = kernel_path.read_text(encoding="utf-8")
    kernel_bytes = kernel_path.read_bytes()
    compile(kernel_text, str(kernel_path), "exec")
    assert "HF_API_TOKEN_2" in kernel_text
    assert "HF_API_TOKEN_1" not in kernel_text
    assert "torchrun" in kernel_text
    assert "OM_SKIP_PIP_INSTALL" in kernel_text
    assert "resume_from_checkpoint=" in kernel_text
    assert "_restore_checkpoint_from_dataset" in kernel_text
    assert "_wait_for_restored_checkpoint" in kernel_text
    expected_marker = b'marker.write_text(label + "' + bytes([92, 110]) + b'", encoding="utf-8")'
    assert expected_marker in kernel_bytes
    assert "_restore_checkpoint_from_wandb" in kernel_text
    assert "WANDB_API_KEY" in kernel_text
    assert "max_session_steps" in kernel_text
    assert "local wheelhouse" in kernel_text
    assert "wheelhouse_enabled" in kernel_text
    assert "network pip install" in kernel_text
    assert "bitsandbytes network repair" in kernel_text


def test_build_package_supports_distilled_behavioral_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "distilled_behavioral"
    package_root = tmp_path / "runs" / "kaggle_qlora_distilled"
    source_dir.mkdir(parents=True)

    knowledge_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Làm sao phối blazer đi làm?"},
            {
                "role": "assistant",
                "content": "Phối blazer cùng quần suông và giày loafer.",
            },
        ],
        "task_type": "stylist_knowledge",
        "source_set": "stylist_knowledge",
        "source_file": "knowledge_distilled.jsonl",
    }
    behavioral_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {
                "role": "user",
                "content": "Tìm outfit đi làm phong cách minimalist dưới 900k.",
            },
            {
                "role": "assistant",
                "content": (
                    '<tool_call>{"name":"search_outfits","arguments":'
                    '{"occasion":"office","style":"minimalist"}}</tool_call>'
                ),
            },
        ],
        "task_type": "tool_calling",
        "source_set": "behavioral_synthetic",
        "source_file": "behavioral_synthetic.jsonl",
    }
    lines = "\n".join(
        [
            json.dumps(knowledge_row, ensure_ascii=False),
            json.dumps(behavioral_row, ensure_ascii=False),
        ]
    )
    (source_dir / "knowledge_distilled.jsonl").write_text(lines + "\n", encoding="utf-8")
    (source_dir / "behavioral_synthetic.jsonl").write_text(
        json.dumps(behavioral_row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (source_dir / "train.jsonl").write_text(lines + "\n", encoding="utf-8")
    (source_dir / "manifest.json").write_text(
        json.dumps({"combined_examples": 2}),
        encoding="utf-8",
    )

    config = load_config(Path("configs/stylist_finetune_kaggle_distilled_behavioral.yaml"))
    config["dataset"]["stylist_knowledge_dir"] = str(source_dir)
    config["dataset"]["max_eval_records"] = 1
    config["outputs"]["package_root"] = str(package_root)
    config["outputs"]["manifest"] = str(package_root / "manifest.json")
    config_path = tmp_path / "distilled_config.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    manifest = build_package(config_path, clean=True, push=False)
    assert manifest["dataset"]["source_mode"] == "distilled_behavioral_bundle"
    assert manifest["dataset"]["total_examples"] == 2
    assert manifest["dataset"]["train_examples"] == 1
    assert manifest["dataset"]["eval_examples"] == 1

    packaged_rows = []
    for split_name in ("train", "eval"):
        split_path = package_root / "kaggle_dataset" / f"{split_name}.jsonl"
        packaged_rows.extend(
            json.loads(line)
            for line in split_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    assert {row["source_set"] for row in packaged_rows} == {
        "stylist_knowledge",
        "behavioral_synthetic",
    }
    assert {row["task_type"] for row in packaged_rows} == {
        "stylist_knowledge",
        "tool_calling",
    }
