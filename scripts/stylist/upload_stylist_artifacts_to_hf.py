"""Upload OutfitMatch stylist datasets and LoRA adapters to Hugging Face.

- Dataset repo already exists: ``Nhat-Quang/VN_Fashion_data``.
- This script can create/update 2 model repos for the fine-tuned Qwen adapters.
- Model repos are staged so PEFT files stay at repo root for direct loading.

Examples:
    uv run python scripts/stylist/upload_stylist_artifacts_to_hf.py --dry-run
    uv run python scripts/stylist/upload_stylist_artifacts_to_hf.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import HfApi

DEFAULT_DATASET_REPO_ID = "Nhat-Quang/VN_Fashion_data"
DEFAULT_DATASET_REPO_TYPE = "dataset"
DEFAULT_MODEL_REPO_TYPE = "model"

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DatasetUpload:
    source: Path
    path_in_repo: str


@dataclass(frozen=True)
class ModelUpload:
    repo_id: str
    adapter_dir: Path
    base_model: str
    training_summary: Path | None = None
    trainer_state: Path | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class UploadPlan:
    dataset_repo_id: str
    dataset_uploads: tuple[DatasetUpload, ...]
    model_uploads: tuple[ModelUpload, ...]


def build_default_upload_plan() -> UploadPlan:
    """Return the default HF upload plan for current stylist artifacts."""
    dataset_uploads = (
        DatasetUpload(
            source=REPO_ROOT
            / "data/stylist/fine_tune/stylist_knowledge/finetuning_data_fashion_knowledge.csv",
            path_in_repo=(
                "stylist/fine_tune/stylist_knowledge/finetuning_data_fashion_knowledge.csv"
            ),
        ),
        DatasetUpload(
            source=REPO_ROOT / "data/stylist/fine_tune/runs/stylist_distilled_behavioral",
            path_in_repo="stylist/fine_tune/runs/stylist_distilled_behavioral",
        ),
        DatasetUpload(
            source=(
                REPO_ROOT / "data/stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen/kaggle_dataset"
            ),
            path_in_repo="stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen/kaggle_dataset",
        ),
    )
    model_uploads = (
        ModelUpload(
            repo_id="Nhat-Quang/outfitmatch-stylist-qwen3vl8b-lora",
            adapter_dir=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen/"
                "download_qwen3vl8b_instruct/outfitmatch_stylist_qlora/"
                "qwen3vl8b_instruct/adapter"
            ),
            base_model="Qwen/Qwen3-VL-8B-Instruct",
            training_summary=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen/"
                "download_qwen3vl8b_instruct/outfitmatch_stylist_qlora/"
                "qwen3vl8b_instruct/training_summary.json"
            ),
            trainer_state=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen/"
                "download_qwen3vl8b_instruct/outfitmatch_stylist_qlora/"
                "qwen3vl8b_instruct/checkpoint-2487/trainer_state.json"
            ),
            notes=(
                "Knowledge-only QLoRA run from Kaggle token3 T4 training package.",
                "Upload root keeps adapter files at repo top for direct PEFT loading.",
            ),
        ),
        ModelUpload(
            repo_id="Nhat-Quang/outfitmatch-stylist-qwen35-9b-lora",
            adapter_dir=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/"
                "kaggle_qlora_token1_qwen35_distilled_resume/download_latest/"
                "outfitmatch_stylist_qlora/qwen35_9b/adapter"
            ),
            base_model="Qwen/Qwen3.5-9B",
            training_summary=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/"
                "kaggle_qlora_token1_qwen35_distilled_resume/download_latest/"
                "outfitmatch_stylist_qlora/qwen35_9b/training_summary.json"
            ),
            trainer_state=REPO_ROOT
            / (
                "data/stylist/fine_tune/runs/"
                "kaggle_qlora_token1_qwen35_distilled_resume/download_latest/"
                "outfitmatch_stylist_qlora/qwen35_9b/checkpoint-346/trainer_state.json"
            ),
            notes=(
                "Distilled+behavioral QLoRA run resumed from checkpoint-250 to completion.",
                "Resume metadata is included for reproducibility.",
            ),
        ),
    )
    return UploadPlan(
        dataset_repo_id=DEFAULT_DATASET_REPO_ID,
        dataset_uploads=dataset_uploads,
        model_uploads=model_uploads,
    )


def ensure_sources_exist(plan: UploadPlan) -> None:
    """Fail fast if any local upload source is missing."""
    missing: list[str] = []
    for item in plan.dataset_uploads:
        if not item.source.exists():
            missing.append(str(item.source))
    for item in plan.model_uploads:
        if not item.adapter_dir.exists():
            missing.append(str(item.adapter_dir))
        if item.training_summary and not item.training_summary.exists():
            missing.append(str(item.training_summary))
        if item.trainer_state and not item.trainer_state.exists():
            missing.append(str(item.trainer_state))
    if missing:
        raise FileNotFoundError("Missing upload sources:\n- " + "\n- ".join(missing))


def build_model_readme(model_upload: ModelUpload) -> str:
    """Create a small README for the staged model repo."""
    lines = [
        "---",
        "library_name: peft",
        f"base_model: {model_upload.base_model}",
        "tags:",
        "- outfitmatch",
        "- stylist",
        "- qlora",
        "- lora",
        "---",
        "",
        f"# {model_upload.repo_id.split('/', 1)[1]}",
        "",
        f"Base model: `{model_upload.base_model}`",
        "",
        "This repo stores the PEFT adapter at the repo root so it can be loaded with",
        "`PeftModel.from_pretrained(...)` or equivalent Hugging Face/PEFT APIs.",
        "",
        "## Notes",
    ]
    lines.extend(f"- {note}" for note in model_upload.notes)
    lines.extend(
        [
            "",
            "## Included files",
            "- adapter_config.json",
            "- adapter_model.safetensors",
            "- tokenizer / processor files copied from the final adapter folder",
            "- training_summary.json when available",
            "- trainer_state.json from the final checkpoint when available",
        ]
    )
    return "\n".join(lines) + "\n"


def upload_dataset_item(api: HfApi, *, repo_id: str, item: DatasetUpload) -> None:
    """Upload one dataset item, handling both single files and folders."""
    if item.source.is_file():
        api.upload_file(
            path_or_fileobj=str(item.source),
            repo_id=repo_id,
            repo_type=DEFAULT_DATASET_REPO_TYPE,
            path_in_repo=item.path_in_repo,
            commit_message=f"Upload {item.path_in_repo}",
        )
        return

    api.upload_folder(
        folder_path=str(item.source),
        repo_id=repo_id,
        repo_type=DEFAULT_DATASET_REPO_TYPE,
        path_in_repo=item.path_in_repo,
        commit_message=f"Upload {item.path_in_repo}",
    )


def stage_model_artifact(
    *,
    adapter_dir: Path,
    output_dir: Path,
    extra_files: dict[str, Path] | None = None,
    readme_text: str | None = None,
) -> Path:
    """Stage a model repo folder with adapter files at root."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for source in adapter_dir.iterdir():
        destination = output_dir / source.name
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    for name, path in (extra_files or {}).items():
        shutil.copy2(path, output_dir / name)

    if readme_text is not None:
        (output_dir / "README.md").write_text(readme_text, encoding="utf-8")

    return output_dir


def upload_plan(plan: UploadPlan, *, dry_run: bool = False, create_repos: bool = True) -> None:
    """Upload the configured dataset/model artifacts to HF."""
    ensure_sources_exist(plan)
    api = HfApi()

    for item in plan.dataset_uploads:
        print(f"[dataset] {item.source} -> {plan.dataset_repo_id}/{item.path_in_repo}")
        if dry_run:
            continue
        upload_dataset_item(api, repo_id=plan.dataset_repo_id, item=item)

    with tempfile.TemporaryDirectory(prefix="stylist-hf-stage-") as temp_dir:
        temp_root = Path(temp_dir)
        for item in plan.model_uploads:
            staged = stage_model_artifact(
                adapter_dir=item.adapter_dir,
                output_dir=temp_root / item.repo_id.split("/", 1)[1],
                extra_files={
                    name: path
                    for name, path in {
                        "training_summary.json": item.training_summary,
                        "trainer_state.json": item.trainer_state,
                    }.items()
                    if path is not None
                },
                readme_text=build_model_readme(item),
            )
            print(f"[model] {staged} -> {item.repo_id}")
            if dry_run:
                continue
            if create_repos:
                api.create_repo(item.repo_id, repo_type=DEFAULT_MODEL_REPO_TYPE, exist_ok=True)
            api.upload_folder(
                folder_path=str(staged),
                repo_id=item.repo_id,
                repo_type=DEFAULT_MODEL_REPO_TYPE,
                commit_message="Upload stylist LoRA adapter",
            )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the upload plan without sending files to Hugging Face.",
    )
    parser.add_argument(
        "--skip-create-repos",
        action="store_true",
        help="Assume model repos already exist and skip create_repo(...).",
    )
    parser.add_argument(
        "--print-plan-json",
        action="store_true",
        help="Dump the resolved upload plan as JSON before uploading.",
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    plan = build_default_upload_plan()

    if args.print_plan_json:
        payload = {
            "dataset_repo_id": plan.dataset_repo_id,
            "dataset_uploads": [
                {"source": str(item.source), "path_in_repo": item.path_in_repo}
                for item in plan.dataset_uploads
            ],
            "model_uploads": [
                {
                    "repo_id": item.repo_id,
                    "adapter_dir": str(item.adapter_dir),
                    "base_model": item.base_model,
                    "training_summary": str(item.training_summary),
                    "trainer_state": str(item.trainer_state),
                }
                for item in plan.model_uploads
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    upload_plan(plan, dry_run=args.dry_run, create_repos=not args.skip_create_repos)


if __name__ == "__main__":
    main()
