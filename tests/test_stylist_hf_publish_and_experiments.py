from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_build_default_upload_plan_targets_expected_hf_repos() -> None:
    module = _load_module(
        "upload_stylist_artifacts_to_hf",
        "scripts/stylist/upload_stylist_artifacts_to_hf.py",
    )

    plan = module.build_default_upload_plan()

    assert plan.dataset_repo_id == "Nhat-Quang/VN_Fashion_data"
    assert {item.path_in_repo for item in plan.dataset_uploads} >= {
        "stylist/fine_tune/stylist_knowledge/finetuning_data_fashion_knowledge.csv",
        "stylist/fine_tune/runs/stylist_distilled_behavioral",
    }
    assert {item.repo_id for item in plan.model_uploads} == {
        "Nhat-Quang/outfitmatch-stylist-qwen3vl8b-lora",
        "Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora",
    }




def test_upload_dataset_item_uses_file_or_folder_api(tmp_path: Path) -> None:
    module = _load_module(
        "upload_stylist_artifacts_to_hf_for_api_test",
        "scripts/stylist/upload_stylist_artifacts_to_hf.py",
    )

    calls: list[tuple[str, str]] = []

    class FakeApi:
        def upload_file(self, *, path_or_fileobj: str, **_: object) -> None:
            calls.append(("file", path_or_fileobj))

        def upload_folder(self, *, folder_path: str, **_: object) -> None:
            calls.append(("folder", folder_path))

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("x", encoding="utf-8")
    folder_path = tmp_path / "bundle"
    folder_path.mkdir()

    module.upload_dataset_item(
        FakeApi(),
        repo_id="Nhat-Quang/VN_Fashion_data",
        item=module.DatasetUpload(csv_path, "a/sample.csv"),
    )
    module.upload_dataset_item(
        FakeApi(),
        repo_id="Nhat-Quang/VN_Fashion_data",
        item=module.DatasetUpload(folder_path, "a/bundle"),
    )

    assert calls == [
        ("file", str(csv_path)),
        ("folder", str(folder_path)),
    ]

def test_stage_model_artifact_keeps_peft_root_files(tmp_path: Path) -> None:
    module = _load_module(
        "upload_stylist_artifacts_to_hf",
        "scripts/stylist/upload_stylist_artifacts_to_hf.py",
    )

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"weights")
    summary = tmp_path / "training_summary.json"
    summary.write_text('{"resume_step": 250}', encoding="utf-8")
    state = tmp_path / "trainer_state.json"
    state.write_text('{"global_step": 346}', encoding="utf-8")

    staged_dir = module.stage_model_artifact(
        adapter_dir=adapter_dir,
        output_dir=tmp_path / "staged",
        extra_files={
            "training_summary.json": summary,
            "trainer_state.json": state,
        },
        readme_text="# Demo model\n",
    )

    assert (staged_dir / "adapter_config.json").is_file()
    assert (staged_dir / "adapter_model.safetensors").is_file()
    assert (staged_dir / "training_summary.json").is_file()
    assert (staged_dir / "trainer_state.json").is_file()
    assert (staged_dir / "README.md").read_text(encoding="utf-8") == "# Demo model\n"


def test_qwen35_experiment_defaults_and_messages() -> None:
    module = _load_module(
        "run_qwen35_9b_stylist_experiment",
        "scripts/stylist/run_qwen35_9b_stylist_experiment.py",
    )

    parser = module.build_parser()
    args = parser.parse_args(["--prompt", "Gợi ý outfit đi làm"]) 
    messages = module.build_messages(args.system_prompt, args.prompt)

    assert args.adapter_repo == "Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora"
    assert args.base_model == "Qwen/Qwen3.5-9B"
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Gợi ý outfit đi làm"


def test_qwen3vl_experiment_defaults_and_image_message() -> None:
    module = _load_module(
        "run_qwen3vl8b_stylist_experiment",
        "scripts/stylist/run_qwen3vl8b_stylist_experiment.py",
    )

    parser = module.build_parser()
    args = parser.parse_args(["--prompt", "Tư vấn set đồ", "--image-path", "look.jpg"])
    messages = module.build_messages(
        system_prompt=args.system_prompt,
        prompt=args.prompt,
        image_path=Path(args.image_path),
    )

    assert args.adapter_repo == "Nhat-Quang/outfitmatch-stylist-qwen3vl8b-lora"
    assert args.base_model == "Qwen/Qwen3-VL-8B-Instruct"
    user_content = messages[1]["content"]
    assert user_content[0]["type"] == "image"
    assert user_content[0]["image"] == "look.jpg"
    assert user_content[1]["text"] == "Tư vấn set đồ"
