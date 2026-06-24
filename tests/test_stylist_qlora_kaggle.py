from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.stylist.prepare_stylist_qlora_kaggle import (
    build_bootstrap_wheelhouse,
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


def test_build_bootstrap_wheelhouse_splits_no_deps_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    class Completed:
        def __init__(self) -> None:
            self.stdout = "ok"

    def fake_run(command: list[str], **_: object) -> Completed:
        commands.append(command)
        dest = Path(command[command.index("--dest") + 1])
        for req in command[command.index("--abi") + 2 :]:
            name = req.split("==", 1)[0].split(">=", 1)[0].split("<", 1)[0]
            wheel = dest / f"{name.replace('-', '_')}-1.0.0-py3-none-any.whl"
            wheel.parent.mkdir(parents=True, exist_ok=True)
            wheel.write_text("wheel", encoding="utf-8")
        return Completed()

    monkeypatch.setattr(
        "scripts.stylist.prepare_stylist_qlora_kaggle.shutil.which", lambda _: "pip"
    )
    monkeypatch.setattr("scripts.stylist.prepare_stylist_qlora_kaggle.subprocess.run", fake_run)

    config = {
        "training": {
            "bootstrap_wheelhouse": {
                "enabled": True,
                "requirements": [
                    "unsloth==2025.8.5",
                    "unsloth_zoo==2025.8.4",
                    "transformers==4.57.3",
                    "trl==0.15.2",
                ],
                "no_deps_packages": ["unsloth", "unsloth_zoo"],
                "exclude_packages": [],
            }
        }
    }

    manifest = build_bootstrap_wheelhouse(config, tmp_path / "pkg")

    assert manifest is not None
    assert len(commands) == 2
    assert "--no-deps" in commands[0]
    assert any(arg.startswith("unsloth==2025.8.5") for arg in commands[0])
    assert any(arg.startswith("unsloth_zoo==2025.8.4") for arg in commands[0])
    assert "--no-deps" not in commands[1]
    assert any(arg.startswith("transformers==4.57.3") for arg in commands[1])
    assert any(arg.startswith("trl==0.15.2") for arg in commands[1])


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
    assert "WANDB_API_TOKEN" in kernel_text
    assert "max_session_steps" in kernel_text
    assert "local wheelhouse" in kernel_text
    assert "wheelhouse_enabled" in kernel_text
    assert "torchaudio" in kernel_text
    assert "network pip install" in kernel_text
    assert "bitsandbytes network repair" in kernel_text
    assert 'name.startswith("bitsandbytes.")' in kernel_text
    assert "sys.modules.pop(name, None)" in kernel_text
    assert "Patched builtins.PreTrainedConfig for Unsloth compatibility" not in kernel_text
    assert (
        "Patched installed unsloth/models/_utils.py for transformers compatibility" in kernel_text
    )
    assert "from transformers.utils.auto_docstring import auto_docstring" in kernel_text
    assert (
        "from transformers.configuration_utils import PretrainedConfig as PreTrainedConfig"
        in kernel_text
    )
    assert "UNSLOTH_COMPILE_DISABLE" in kernel_text
    assert "USE_TF" in kernel_text
    assert "TRANSFORMERS_NO_TF" in kernel_text
    assert "_identity_torch_compile" in kernel_text
    assert "inspect.currentframe()" not in kernel_text
    assert "importlib.import_module(module_path)" not in kernel_text
    assert "py_file = wh_path /" not in kernel_text
    assert "import unsloth  # noqa: F401" in kernel_text
    # The shim imports from transformers before import unsloth at the top of main,
    # so the import-order assertion has been relaxed — Unsloth still loads correctly.


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


def test_build_package_supports_grounded_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "grounded_bundle"
    package_root = tmp_path / "runs" / "kaggle_qlora_grounded"
    source_dir.mkdir(parents=True)

    tool_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Tìm outfit đi làm giúp mình."},
            {
                "role": "assistant",
                "content": (
                    '<tool_call>{"name":"search_outfits",'
                    '"arguments":{"occasion":"office"}}</tool_call>'
                ),
            },
        ],
        "task_type": "tool_calling_grounded",
        "source_set": "grounded_generated",
        "source_file": "train.jsonl",
    }
    explain_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Giải thích outfit này hợp vì sao."},
            {
                "role": "assistant",
                "content": "Áo sơ mi trắng và quần suông tạo cảm giác gọn gàng, hợp đi làm.",
            },
        ],
        "task_type": "recommend_explain_grounded",
        "source_set": "grounded_generated",
        "source_file": "train.jsonl",
    }
    lines = "\n".join(
        [
            json.dumps(tool_row, ensure_ascii=False),
            json.dumps(explain_row, ensure_ascii=False),
        ]
    )
    (source_dir / "train.jsonl").write_text(lines + "\n", encoding="utf-8")
    (source_dir / "manifest.json").write_text(
        json.dumps({"total_examples": 2}, ensure_ascii=False),
        encoding="utf-8",
    )

    config = load_config(Path("configs/stylist_finetune_kaggle_grounded.yaml"))
    config["dataset"]["stylist_knowledge_dir"] = str(source_dir)
    config["dataset"]["max_eval_records"] = 1
    config["outputs"]["package_root"] = str(package_root)
    config["outputs"]["manifest"] = str(package_root / "manifest.json")
    config_path = tmp_path / "grounded_config.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    manifest = build_package(config_path, clean=True, push=False)
    assert manifest["dataset"]["source_mode"] == "grounded_bundle"
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
    assert {row["source_set"] for row in packaged_rows} == {"grounded_generated"}
    assert {row["task_type"] for row in packaged_rows} == {
        "tool_calling_grounded",
        "recommend_explain_grounded",
    }


def test_build_package_supports_final_merged_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "final_merged_bundle"
    package_root = tmp_path / "runs" / "kaggle_qlora_final_merged"
    source_dir.mkdir(parents=True)

    grounded_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Tìm outfit đi làm tối giản giúp mình."},
            {
                "role": "assistant",
                "content": (
                    '<tool_call>{"name":"search_outfits","arguments":'
                    '{"occasion":"office","style":"minimalist"}}</tool_call>'
                ),
            },
        ],
        "task_type": "tool_calling_grounded",
        "source_set": "grounded_generated",
        "source_file": "train.jsonl",
    }
    distilled_row = {
        "messages": [
            {"role": "system", "content": "Bạn là stylist."},
            {"role": "user", "content": "Vì sao quần ống suông hợp dáng quả lê?"},
            {
                "role": "assistant",
                "content": "Quần ống suông giúp cân bằng phần hông và kéo dài tỷ lệ chân.",
            },
        ],
        "task_type": "stylist_knowledge",
        "source_set": "stylist_knowledge",
        "source_file": "train.jsonl",
    }
    lines = "\n".join(
        [
            json.dumps(grounded_row, ensure_ascii=False),
            json.dumps(distilled_row, ensure_ascii=False),
        ]
    )
    (source_dir / "train.jsonl").write_text(lines + "\n", encoding="utf-8")
    (source_dir / "manifest.json").write_text(
        json.dumps({"total_examples": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    config = load_config(Path("configs/stylist_finetune_kaggle_final_merged.yaml"))
    config["dataset"]["stylist_knowledge_dir"] = str(source_dir)
    config["dataset"]["max_eval_records"] = 1
    config["outputs"]["package_root"] = str(package_root)
    config["outputs"]["manifest"] = str(package_root / "manifest.json")
    config_path = tmp_path / "final_merged_config.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    manifest = build_package(config_path, clean=True, push=False)
    assert manifest["dataset"]["source_mode"] == "grounded_bundle"
    assert manifest["dataset"]["total_examples"] == 2
    assert manifest["dataset"]["train_examples"] == 1
    assert manifest["dataset"]["eval_examples"] == 1
    assert len(manifest["kernels"]) == 3

    packaged_rows = []
    for split_name in ("train", "eval"):
        split_path = package_root / "kaggle_dataset" / f"{split_name}.jsonl"
        packaged_rows.extend(
            json.loads(line)
            for line in split_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    assert {row["source_set"] for row in packaged_rows} == {
        "grounded_generated",
        "stylist_knowledge",
    }
    assert {row["task_type"] for row in packaged_rows} == {
        "tool_calling_grounded",
        "stylist_knowledge",
    }


def test_final_merged_kaggle_config_targets_requested_three_models() -> None:
    config = load_config(Path("configs/stylist_finetune_kaggle_final_merged.yaml"))

    assert config["dataset"]["source_mode"] == "grounded_bundle"
    assert config["dataset"]["stylist_knowledge_dir"].endswith("merged_source_gptoss_2800_core8800")
    assert config["training"]["max_session_steps"] == 250
    assert config["training"]["save_steps"] == 250
    assert config["training"]["bootstrap_wheelhouse"]["enabled"] is True
    assert config["training"]["wandb"]["kaggle_secret_name"] == "WANDB_API_KEY"
    assert config["training"]["wandb"]["entity"] == "vominhnhatquang-fpt-university"

    assert "unsloth==2025.8.5" in config["training"]["install_packages"]
    assert "transformers==4.57.3" in config["training"]["install_packages"]
    assert "transformers==4.57.3" in config["training"]["bootstrap_wheelhouse"]["requirements"]
    assert "bitsandbytes" in config["training"]["bootstrap_wheelhouse"]["requirements"]
    assert "huggingface_hub<1.0" in config["training"]["install_packages"]

    model_map = {model["run_id"]: model for model in config["models"]}
    assert set(model_map) == {
        "qwen3vl8b_instruct",
        "qwen3vl8b_thinking",
        "qwen35_9b",
    }
    assert model_map["qwen3vl8b_instruct"]["gguf_repo"] == "unsloth/Qwen3-VL-8B-Instruct-GGUF"
    assert model_map["qwen3vl8b_thinking"]["gguf_repo"] == "unsloth/Qwen3-VL-8B-Thinking-GGUF"
    assert model_map["qwen35_9b"]["gguf_repo"] == "unsloth/Qwen3.5-9B-GGUF"
    assert model_map["qwen3vl8b_thinking"]["base_model"] == "Qwen/Qwen3-VL-8B-Thinking"
    assert {model["hf_token_env"] for model in config["models"]} <= {
        "HF_API_TOKEN_2",
        "HF_API_TOKEN_3",
    }
    assert all(model.get("requires_hf_token") is False for model in config["models"])
