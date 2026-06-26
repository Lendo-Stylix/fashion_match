"""Prepare Kaggle Unsloth QLoRA jobs for the Stylist model comparison.

This local packaging utility converts `stylist_knowledge` to ChatML JSONL, creates a
Kaggle dataset bundle, and creates three Kaggle script kernels that run Unsloth QLoRA on
Kaggle T4x2 GPUs.

Security invariants:
- Generated kernels reference only Kaggle secret names, never token values.
- Only HF_API_TOKEN_2 and HF_API_TOKEN_3 are accepted by the config validator.
- `users_query_and_response` is ignored; supported dataset.source_mode values are
  `stylist_knowledge_only`, `distilled_behavioral_bundle`, and `grounded_bundle`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("configs/stylist_finetune_kaggle.yaml")
SUPPORTED_SUFFIXES = {".csv", ".jsonl", ".json", ".md", ".txt"}
TORCH_CUDA_REQUIREMENTS: dict[str, list[str]] = {
    "torch==2.4.0": [
        "nvidia-cuda-nvrtc-cu12==12.1.105",
        "nvidia-cuda-runtime-cu12==12.1.105",
        "nvidia-cuda-cupti-cu12==12.1.105",
        "nvidia-cudnn-cu12==9.1.0.70",
        "nvidia-cublas-cu12==12.1.3.1",
        "nvidia-cufft-cu12==11.0.2.54",
        "nvidia-curand-cu12==10.3.2.106",
        "nvidia-cusolver-cu12==11.4.5.107",
        "nvidia-cusparse-cu12==12.1.0.106",
        "nvidia-nccl-cu12==2.20.5",
        "nvidia-nvtx-cu12==12.1.105",
    ]
}


@dataclass(frozen=True)
class ChatExample:
    """Normalized SFT example using a ChatML-like messages schema."""

    messages: list[dict[str, str]]
    task_type: str
    source_set: str
    source_file: str


def load_config(path: Path) -> dict[str, Any]:
    """Load and validate the Kaggle QLoRA YAML config."""
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    validate_config(config)
    return config


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE pairs from an env file without exporting them."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_env_value(name: str, env_file: Path) -> str | None:
    """Resolve a single env value from process env first, then a local env file."""
    return os.environ.get(name) or read_env_file(env_file).get(name)


def validate_config(config: dict[str, Any]) -> None:
    """Validate token and dataset invariants from the user request."""
    allowed = set(config.get("secrets", {}).get("allowed_hf_token_env_vars", []))
    forbidden = set(config.get("secrets", {}).get("forbidden_hf_token_env_vars", []))
    if allowed != {"HF_API_TOKEN_2", "HF_API_TOKEN_3"}:
        raise ValueError("Only HF_API_TOKEN_2 and HF_API_TOKEN_3 may be allowed")
    if "HF_API_TOKEN_1" not in forbidden:
        raise ValueError("HF_API_TOKEN_1 must be explicitly forbidden")

    source_mode = config.get("dataset", {}).get("source_mode")
    allowed_source_modes = {
        "stylist_knowledge_only",
        "distilled_behavioral_bundle",
        "grounded_bundle",
    }
    if source_mode not in allowed_source_modes:
        raise ValueError(
            "dataset.source_mode must be one of: stylist_knowledge_only, "
            "distilled_behavioral_bundle, grounded_bundle"
        )

    for model in config.get("models", []):
        token_env = model.get("hf_token_env")
        if token_env not in allowed or token_env in forbidden:
            raise ValueError(f"Model {model.get('run_id')} uses disallowed token {token_env}")

    if config.get("training", {}).get("framework") != "unsloth":
        raise ValueError("training.framework must be unsloth")
    if config.get("training", {}).get("strategy") != "qlora_sft":
        raise ValueError("training.strategy must be qlora_sft")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _messages(system_prompt: str, user_text: str, assistant_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]


def _row_to_example(
    row: dict[str, Any], *, system_prompt: str, prefer_translated: bool, source_file: Path
) -> ChatExample | None:
    if "messages" in row and isinstance(row["messages"], list):
        messages = row["messages"]
        valid = all(
            isinstance(item, dict) and "role" in item and "content" in item for item in messages
        )
        if valid:
            return ChatExample(
                messages=[{"role": str(m["role"]), "content": str(m["content"])} for m in messages],
                task_type=str(row.get("task_type", "stylist_knowledge")),
                source_set=str(row.get("source_set", "stylist_knowledge")),
                source_file=str(source_file),
            )

    input_keys = ["translated_input", "input", "prompt", "question", "original_input"]
    output_keys = ["translated_output", "output", "response", "answer", "original_output"]
    if not prefer_translated:
        input_keys = ["original_input", "input", "prompt", "question", "translated_input"]
        output_keys = ["original_output", "output", "response", "answer", "translated_output"]

    user_text = next(
        (_clean_text(row.get(key)) for key in input_keys if _clean_text(row.get(key))),
        "",
    )
    assistant_text = next(
        (_clean_text(row.get(key)) for key in output_keys if _clean_text(row.get(key))), ""
    )
    if not user_text or not assistant_text:
        return None
    return ChatExample(
        messages=_messages(system_prompt, user_text, assistant_text),
        task_type="stylist_knowledge",
        source_set="stylist_knowledge",
        source_file=str(source_file),
    )


def _iter_csv(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(loaded, dict):
                yield loaded


def _iter_json(path: Path) -> Iterable[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        for item in loaded:
            if isinstance(item, dict):
                yield item
    elif isinstance(loaded, dict):
        records = loaded.get("data") or loaded.get("records") or loaded.get("examples")
        if isinstance(records, list):
            for item in records:
                if isinstance(item, dict):
                    yield item
        else:
            yield loaded


def _iter_text_docs(path: Path) -> Iterable[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if text:
        yield {
            "input": "Hãy ghi nhớ và tóm tắt kiến thức stylist sau cho OutfitMatch.",
            "output": text,
        }


def iter_source_rows(path: Path) -> Iterable[dict[str, Any]]:
    """Yield raw rows from a supported stylist_knowledge source file."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        yield from _iter_csv(path)
    elif suffix == ".jsonl":
        yield from _iter_jsonl(path)
    elif suffix == ".json":
        yield from _iter_json(path)
    elif suffix in {".md", ".txt"}:
        yield from _iter_text_docs(path)


def collect_examples(config: dict[str, Any]) -> list[ChatExample]:
    """Read configured training examples and return deterministic, de-duplicated rows."""
    dataset = config["dataset"]
    source_mode = str(dataset["source_mode"])
    source_dir = Path(str(dataset["stylist_knowledge_dir"]))
    accepted = {str(ext).lower() for ext in dataset.get("accepted_extensions", [])}
    accepted &= SUPPORTED_SUFFIXES
    system_prompt = str(dataset["system_prompt"])
    prefer_translated = bool(dataset.get("prefer_translated_columns", True))

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Missing training data directory: {source_dir}")

    candidate_paths: list[Path]
    if source_mode in {"distilled_behavioral_bundle", "grounded_bundle"}:
        preferred = source_dir / "train.jsonl"
        candidate_paths = (
            [preferred] if preferred.is_file() else sorted(source_dir.rglob("*.jsonl"))
        )
    else:
        candidate_paths = [
            path
            for path in sorted(source_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in accepted
        ]

    examples: list[ChatExample] = []
    seen: set[str] = set()
    for path in candidate_paths:
        for row in iter_source_rows(path):
            example = _row_to_example(
                row,
                system_prompt=system_prompt,
                prefer_translated=prefer_translated,
                source_file=path,
            )
            if example is None:
                continue
            digest = hashlib.sha256(
                json.dumps(example.messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            examples.append(example)
    return examples


def split_examples(
    examples: list[ChatExample], *, seed: int, eval_fraction: float, max_eval_records: int
) -> tuple[list[ChatExample], list[ChatExample]]:
    """Shuffle and split examples with a capped eval set."""
    if not examples:
        raise ValueError("No training examples found in stylist_knowledge")
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    eval_size = max(1, int(len(shuffled) * eval_fraction))
    eval_size = min(eval_size, max_eval_records, max(1, len(shuffled) - 1))
    return shuffled[eval_size:], shuffled[:eval_size]


def write_jsonl(path: Path, examples: Iterable[ChatExample]) -> int:
    """Write examples as UTF-8 JSONL and return the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(
                json.dumps(
                    {
                        "messages": example.messages,
                        "task_type": example.task_type,
                        "source_set": example.source_set,
                        "source_file": example.source_file,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def _safe_slug(value: str, *, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        raise ValueError("Slug cannot be empty")
    if len(slug) > max_len:
        raise ValueError(f"Slug too long for Kaggle ({len(slug)} > {max_len}): {slug}")
    return slug


def normalize_dataset(config: dict[str, Any], package_root: Path) -> dict[str, Any]:
    """Create normalized train/eval JSONL files under the Kaggle dataset bundle."""
    dataset = config["dataset"]
    outputs = config["outputs"]
    train_path = package_root / "kaggle_dataset" / Path(str(outputs["normalized_train_jsonl"])).name
    eval_path = package_root / "kaggle_dataset" / Path(str(outputs["normalized_eval_jsonl"])).name

    examples = collect_examples(config)
    train, eval_ = split_examples(
        examples,
        seed=int(dataset.get("seed", 42)),
        eval_fraction=float(dataset.get("eval_fraction", 0.03)),
        max_eval_records=int(dataset.get("max_eval_records", 512)),
    )
    train_count = write_jsonl(train_path, train)
    eval_count = write_jsonl(eval_path, eval_)
    return {
        "source_mode": dataset["source_mode"],
        "total_examples": len(examples),
        "train_examples": train_count,
        "eval_examples": eval_count,
        "train_path": str(train_path),
        "eval_path": str(eval_path),
    }


def _resolve_resume_checkpoint_source(path: Path) -> Path:
    if path.is_dir() and (path / "trainer_state.json").is_file():
        return path
    candidates = [candidate for candidate in path.rglob("checkpoint-*") if candidate.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No checkpoint-* directory found under: {path}")
    return sorted(candidates, key=lambda candidate: candidate.name)[-1]


def stage_resume_checkpoint(config: dict[str, Any], package_root: Path) -> dict[str, Any] | None:
    """Copy a local checkpoint into the Kaggle dataset bundle for offline resume."""
    resume_cfg = dict(config.get("training", {}).get("resume_checkpoint", {}))
    local_path = str(resume_cfg.get("local_path", "") or "").strip()
    if not local_path:
        return None

    checkpoint_dir = _resolve_resume_checkpoint_source(Path(local_path))
    packaged_subdir = str(resume_cfg.get("packaged_subdir", "resume_checkpoint") or "").strip()
    if not packaged_subdir:
        raise ValueError("training.resume_checkpoint.packaged_subdir cannot be empty")

    target_root = package_root / "kaggle_dataset" / packaged_subdir
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    target_dir = target_root / checkpoint_dir.name
    shutil.copytree(checkpoint_dir, target_dir)

    return {
        "local_path": str(checkpoint_dir),
        "dataset_subdir": packaged_subdir,
        "checkpoint_dir": checkpoint_dir.name,
    }


def write_dataset_metadata(config: dict[str, Any], package_root: Path) -> dict[str, str]:
    """Write Kaggle dataset metadata."""
    kaggle = config["kaggle"]
    owner = _safe_slug(str(kaggle["owner"]))
    dataset_slug = _safe_slug(str(kaggle["dataset_slug"]))
    metadata = {
        "title": dataset_slug,
        "id": f"{owner}/{dataset_slug}",
        "licenses": [{"name": "CC0-1.0"}],
    }
    out = package_root / "kaggle_dataset" / "dataset-metadata.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"dataset_id": metadata["id"], "dataset_slug": dataset_slug}


def _canonicalize_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).strip().lower()


def _distribution_name_from_filename(filename: str) -> str:
    match = re.match(r"(?P<name>.+?)-\d", filename)
    stem = match.group("name") if match else Path(filename).stem
    return _canonicalize_package_name(stem)


def build_bootstrap_wheelhouse(config: dict[str, Any], package_root: Path) -> dict[str, Any] | None:
    """Download a Kaggle-compatible wheelhouse to reduce runtime pip network dependency."""
    bootstrap = dict(config.get("training", {}).get("bootstrap_wheelhouse", {}))
    if not bootstrap.get("enabled"):
        return None

    requirements = [
        str(item).strip() for item in bootstrap.get("requirements", []) if str(item).strip()
    ]
    augmented_requirements: list[str] = []
    seen_requirements: set[str] = set()
    for req in requirements:
        if req not in seen_requirements:
            augmented_requirements.append(req)
            seen_requirements.add(req)
        for extra in TORCH_CUDA_REQUIREMENTS.get(req, []):
            if extra not in seen_requirements:
                augmented_requirements.append(extra)
                seen_requirements.add(extra)
    requirements = augmented_requirements
    skipped: list[str] = []
    wheelable: list[str] = []
    for req in requirements:
        if req.startswith("git+") or req.startswith("http:") or req.startswith("https:"):
            skipped.append(req)
        else:
            wheelable.append(req)
    if skipped:
        print(f"Skipping non-wheelable requirements from wheelhouse: {skipped}", flush=True)
    requirements = wheelable
    if not requirements:
        return None

    wheelhouse_dir = package_root / "kaggle_dataset" / "wheelhouse"
    if wheelhouse_dir.exists():
        shutil.rmtree(wheelhouse_dir)
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)

    pip_executable = shutil.which(str(bootstrap.get("pip_executable", "pip")))
    if not pip_executable:
        raise RuntimeError("bootstrap_wheelhouse requires a local pip executable on PATH")

    platform_values = [str(bootstrap.get("platform", "manylinux2014_x86_64"))]
    platform_values.extend(str(item) for item in bootstrap.get("extra_platforms", []))
    platform_args: list[str] = []
    seen_platforms: set[str] = set()
    for platform in platform_values:
        if not platform or platform in seen_platforms:
            continue
        seen_platforms.add(platform)
        platform_args.extend(["--platform", platform])

    base_command = [
        pip_executable,
        "download",
        "--dest",
        str(wheelhouse_dir),
        "--only-binary=:all:",
        *platform_args,
        "--python-version",
        str(bootstrap.get("python_version", "3.12")),
        "--implementation",
        str(bootstrap.get("implementation", "cp")),
        "--abi",
        str(bootstrap.get("abi", "cp312")),
    ]
    no_deps_packages = {
        _canonicalize_package_name(str(item))
        for item in bootstrap.get("no_deps_packages", [])
        if str(item).strip()
    }

    def _requirement_name(requirement: str) -> str:
        return _canonicalize_package_name(
            requirement.split("==", 1)[0].split(">=", 1)[0].split("<", 1)[0]
        )

    grouped_requirements = {
        True: [req for req in requirements if _requirement_name(req) in no_deps_packages],
        False: [req for req in requirements if _requirement_name(req) not in no_deps_packages],
    }

    download_commands: list[list[str]] = []
    download_stdout_parts: list[str] = []
    for use_no_deps in (True, False):
        group = grouped_requirements[use_no_deps]
        if not group:
            continue
        command = [
            *base_command,
            *(["--no-deps"] if use_no_deps else []),
            *group,
        ]
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        download_commands.append(command)
        stdout = str(getattr(completed, "stdout", "") or "").strip()
        if stdout:
            download_stdout_parts.append(stdout)

    excluded = {
        _canonicalize_package_name(str(item))
        for item in bootstrap.get("exclude_packages", ["torch", "torchvision"])
    }
    removed_files: list[str] = []
    for wheel_path in list(wheelhouse_dir.iterdir()):
        if not wheel_path.is_file():
            continue
        if _distribution_name_from_filename(wheel_path.name) in excluded:
            removed_files.append(wheel_path.name)
            wheel_path.unlink()

    wheel_files = sorted(
        wheel_path.name for wheel_path in wheelhouse_dir.iterdir() if wheel_path.is_file()
    )
    manifest = {
        "requirements": requirements,
        "no_deps_packages": sorted(no_deps_packages),
        "excluded_packages": sorted(excluded),
        "wheel_count": len(wheel_files),
        "wheel_files": wheel_files,
        "removed_files": sorted(removed_files),
        "download_commands": download_commands,
    }
    if download_commands:
        manifest["download_command"] = download_commands[0]
    (wheelhouse_dir / "wheelhouse_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "enabled": True,
        "path": str(wheelhouse_dir),
        "requirements": requirements,
        "no_deps_packages": sorted(no_deps_packages),
        "excluded_packages": sorted(excluded),
        "wheel_count": len(wheel_files),
        "removed_files": sorted(removed_files),
        "download_stdout": "\n\n".join(download_stdout_parts),
    }


def _kernel_script(config: dict[str, Any], model: dict[str, Any], dataset_slug: str) -> str:
    """Return a self-contained Kaggle training script for one model."""
    training = config["training"]
    packages = " ".join(training.get("install_packages", []))
    model_py = repr(model)
    training_py = repr(training)
    target_modules_json = json.dumps(training["lora"]["target_modules"])

    return f'''"""Kaggle Unsloth QLoRA job for OutfitMatch Stylist: {model["run_id"]}."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MODEL_CFG = {model_py}
TRAINING_CFG = {training_py}
DATASET_SLUG = {dataset_slug!r}
TARGET_MODULES = {target_modules_json}

# Disable optional framework imports/compilation before importing torch/transformers/Unsloth.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
os.environ.setdefault("OM_SKIP_UNSLOTH_RL_PATCH", "1")


def _is_main_process() -> bool:
    return int(os.environ.get("LOCAL_RANK", "0")) == 0


def _run_pip_with_retries(command: list[str], *, label: str) -> None:
    last_error = None
    for attempt in range(1, 4):
        try:
            subprocess.check_call(command)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if _is_main_process():
                print(f"{{label}} attempt {{attempt}}/3 failed: {{exc}}", flush=True)
            if attempt < 3:
                time.sleep(30 * attempt)
    raise last_error if last_error is not None else RuntimeError(f"{{label}} failed")


def _best_effort_uninstall(packages: list[str]) -> None:
    if not packages:
        return
    command = [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        "-y",
        *packages,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if _is_main_process() and result.returncode == 0:
        package_list = " ".join(packages)
        print(
            f"Reset bootstrap packages before wheelhouse install: {{package_list}}",
            flush=True,
        )


def _resolve_wheelhouses(dataset_root: Path) -> list[Path]:
    wheelhouses: list[Path] = []
    seen: set[str] = set()
    extraction_index = 0

    def _add_dir(candidate: Path, label: str) -> None:
        if not candidate.is_dir() or not any(candidate.glob("*.whl")):
            return
        key = str(candidate.resolve())
        if key in seen:
            return
        seen.add(key)
        wheelhouses.append(candidate)
        if _is_main_process():
            print(f"Using {{label}} wheelhouse dir: {{candidate}}", flush=True)

    def _extract_archive(archive: Path, label: str) -> None:
        nonlocal extraction_index
        if not archive.is_file():
            return
        extraction_index += 1
        if _is_main_process():
            print(f"Using {{label}} wheelhouse archive: {{archive}}", flush=True)
        extract_root = Path("/kaggle/working") / f"_bootstrap_wheelhouse_{{extraction_index}}"
        if extract_root.exists():
            shutil.rmtree(extract_root)
        shutil.unpack_archive(str(archive), str(extract_root))
        preferred = [
            extract_root / archive.stem,
            extract_root / "wheelhouse",
            extract_root,
        ]
        for candidate in preferred:
            _add_dir(candidate, f"extracted {{label}}")
        for candidate in sorted(extract_root.glob("**/wheelhouse*")):
            _add_dir(candidate, f"extracted {{label}}")

    def _add_loose_wheel_dir(wheel_path: Path, label: str) -> None:
        if not wheel_path.is_file() or wheel_path.suffix != ".whl":
            return
        candidate = wheel_path.parent
        if not any(candidate.glob("*.whl")):
            return
        key = str(candidate.resolve())
        if key in seen:
            return
        seen.add(key)
        wheelhouses.append(candidate)
        if _is_main_process():
            print(f"Using {{label}} loose wheel dir: {{candidate}}", flush=True)

    for candidate in sorted(dataset_root.glob("wheelhouse*")):
        if candidate.is_dir():
            _add_dir(candidate, "dataset")
        elif candidate.is_file() and candidate.suffix == ".zip":
            _extract_archive(candidate, "dataset")

    for candidate in sorted(Path("/kaggle/input").glob("**/wheelhouse*")):
        if candidate.is_dir():
            _add_dir(candidate, "discovered")
        elif candidate.is_file() and candidate.suffix == ".zip":
            _extract_archive(candidate, "discovered")

    for wheel_path in sorted(Path("/kaggle/input").glob("**/*.whl")):
        _add_loose_wheel_dir(wheel_path, "discovered")

    if _is_main_process() and wheelhouses:
        print(f"Found {{len(wheelhouses)}} wheelhouse directories", flush=True)
    return wheelhouses


def _wheel_distribution_key(path: Path) -> str:
    try:
        from pip._vendor.packaging.utils import parse_wheel_filename

        name, _, _, _ = parse_wheel_filename(path.name)
        return str(name).replace("_", "-").lower()
    except Exception:
        return path.name.split("-", 1)[0].replace("_", "-").lower()


def _wheelhouse_wheel_paths(wheelhouses: list[Path]) -> list[str]:
    selected: dict[str, str] = {{}}
    for wheelhouse in wheelhouses:
        for path in sorted(wheelhouse.glob("*.whl")):
            key = _wheel_distribution_key(path)
            selected[key] = str(path)
    return list(selected.values())


def _bitsandbytes_wheel_paths(wheel_paths: list[str]) -> list[str]:
    return [
        candidate
        for candidate in wheel_paths
        if _wheel_distribution_key(Path(candidate)) == "bitsandbytes"
    ]

def _bitsandbytes_cuda_lib_present() -> bool:
    import site
    import torch

    cuda_version = str(getattr(getattr(torch, "version", None), "cuda", "") or "")
    if not cuda_version:
        return True
    cuda_tag = cuda_version.replace(".", "")
    expected = f"libbitsandbytes_cuda{{cuda_tag}}.so"
    search_roots = [Path(root) for root in site.getsitepackages()]
    user_site = site.getusersitepackages()
    if user_site:
        search_roots.append(Path(user_site))
    checked = []
    for root in search_roots:
        candidate = root / "bitsandbytes" / expected
        checked.append(str(candidate))
        if candidate.exists():
            return True
    if _is_main_process():
        print(
            f"bitsandbytes CUDA library missing: {{expected}}; searched={{checked}}",
            flush=True,
        )
    return False


def _bitsandbytes_import_ok() -> bool:
    stale = [
        name
        for name in list(sys.modules)
        if name == "bitsandbytes" or name.startswith("bitsandbytes.")
    ]
    for name in stale:
        sys.modules.pop(name, None)
    try:
        import bitsandbytes  # noqa: F401
        return True
    except Exception as exc:
        if _is_main_process():
            print(f"bitsandbytes import failed before repair: {{exc}}", flush=True)
        return False


def _repair_bitsandbytes_for_cuda(wheel_paths: list[str]) -> None:
    import torch

    cuda_version = str(getattr(getattr(torch, "version", None), "cuda", "") or "")
    needs_repair = not _bitsandbytes_cuda_lib_present() or not _bitsandbytes_import_ok()
    if not cuda_version or not needs_repair:
        return
    candidates = _bitsandbytes_wheel_paths(wheel_paths)
    if candidates:
        repair_command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            *candidates,
        ]
        try:
            _run_pip_with_retries(repair_command, label="bitsandbytes local wheel repair")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "bitsandbytes local repair failed; no network repair attempted"
            ) from exc
        if not _bitsandbytes_cuda_lib_present():
            raise RuntimeError(
                "bitsandbytes local repair failed for CUDA "
                f"{{cuda_version}}; CUDA library still missing"
            )
        if not _bitsandbytes_import_ok():
            if _is_main_process():
                print(
                    "bitsandbytes import sanity still failed after local repair; "
                    "continuing because repeated import in the bootstrap process can "
                    "double-register torch custom operators. A fresh training process "
                    "will import bitsandbytes after torchrun relaunch.",
                    flush=True,
                )
        return
    raise RuntimeError(
        "bitsandbytes needs CUDA repair but no local bitsandbytes wheel was found; "
        "no network repair attempted"
    )


def _install(dataset_root: Path) -> None:
    if os.environ.get("OM_SKIP_PIP_INSTALL") == "1":
        return
    packages = list({packages!r}.split())

    # Separate git URLs from versioned packages to avoid pip dependency conflicts
    # (e.g. latest unsloth-zoo requires newer trl than our pinned trl==0.15.2).
    git_packages = [p for p in packages if p.startswith("git+")]
    versioned_packages = [p for p in packages if not p.startswith("git+")]

    wheelhouse_enabled = bool(TRAINING_CFG.get("bootstrap_wheelhouse", {{}}).get("enabled", True))
    wheelhouses = _resolve_wheelhouses(dataset_root) if wheelhouse_enabled else []
    wheelhouse_installed = False
    if wheelhouses:
        # Exclude git URLs from reset_packages; they can't be force-reinstalled as paths.
        reset_packages = sorted(set(versioned_packages + ["xformers", "torchvision", "torchaudio"]))
        _best_effort_uninstall(reset_packages)
        wheel_paths = _wheelhouse_wheel_paths(wheelhouses)
        local_command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--no-deps",
            "--force-reinstall",
            *wheel_paths,
        ]
        try:
            _run_pip_with_retries(local_command, label="local wheelhouse pip install")
            _repair_bitsandbytes_for_cuda(wheel_paths)
            wheelhouse_installed = True
            if _is_main_process():
                print(
                    "Installed "
                    f"{{len(wheel_paths)}} wheelhouse packages from "
                    f"{{len(wheelhouses)}} wheelhouse directories without dependency resolution: "
                    f"{{wheelhouses}}",
                    flush=True,
                )
            if not git_packages:
                return
        except subprocess.CalledProcessError as exc:
            if _is_main_process():
                print(
                    f"Local wheelhouse install failed; falling back to network pip: {{exc}}",
                    flush=True,
                )

    # Install git URLs after wheelhouse, but with --no-deps so Unsloth git code
    # cannot pull newer torch/torchao/trl deps than our Kaggle-compatible wheels.
    if git_packages:
        _run_pip_with_retries(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                "--upgrade",
                "--no-deps",
                *git_packages,
            ],
            label="network git install",
        )
    if wheelhouse_installed:
        _repair_bitsandbytes_for_cuda(wheel_paths)
        return
    # Then install versioned packages from network only if wheelhouse was absent/failed.
    if versioned_packages:
        _run_pip_with_retries(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                "--upgrade",
                "--force-reinstall",
                *versioned_packages,
            ],
            label="network pip install",
        )
    _repair_bitsandbytes_for_cuda(wheel_paths)


def _maybe_relaunch_torchrun() -> None:
    if "--ddp-child" in sys.argv or not TRAINING_CFG.get("ddp", {{}}).get("enabled", False):
        return
    import torch
    gpu_count = torch.cuda.device_count()
    if gpu_count <= 1:
        return
    os.environ["OM_SKIP_PIP_INSTALL"] = "1"
    cmd = [
        "torchrun",
        "--standalone",
        f"--nproc_per_node={{gpu_count}}",
        sys.argv[0],
        "--ddp-child",
    ]
    print("Relaunching with torchrun for multi-GPU DDP:", " ".join(cmd), flush=True)
    os.execvp(cmd[0], cmd)


def _configure_cuda_device_for_ddp() -> None:
    import torch

    local_rank = os.environ.get("LOCAL_RANK")
    if local_rank is None or not torch.cuda.is_available():
        return
    device_index = int(local_rank)
    torch.cuda.set_device(device_index)
    if _is_main_process():
        print(f"Set CUDA device from LOCAL_RANK={{device_index}}", flush=True)


def _debug_torch_cuda() -> None:
    import torch

    payload = dict(
        torch_version=getattr(torch, "__version__", None),
        torch_cuda_version=getattr(getattr(torch, "version", None), "cuda", None),
        cuda_is_available=bool(torch.cuda.is_available()),
        cuda_device_count=int(torch.cuda.device_count()),
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
        nvidia_smi=shutil.which("nvidia-smi"),
    )
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    if payload["nvidia_smi"]:
        try:
            result = subprocess.run(
                [payload["nvidia_smi"], "-L"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(
                json.dumps(
                    dict(
                        nvidia_smi_rc=result.returncode,
                        nvidia_smi_stdout=result.stdout.strip(),
                        nvidia_smi_stderr=result.stderr.strip(),
                    ),
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            print(f"nvidia-smi probe failed: {{exc}}", flush=True)


def _require_torch_cuda() -> None:
    import torch

    if torch.cuda.is_available() and torch.cuda.device_count() > 0:
        return
    raise RuntimeError(
        "Kaggle did not attach a CUDA GPU to this run; "
        "torch is CUDA-enabled but no NVIDIA device/nvidia-smi is visible. "
        "Check Kaggle GPU quota/account accelerator availability before retrying."
    )


def _requires_hf_token() -> bool:
    if "requires_hf_token" in MODEL_CFG:
        return bool(MODEL_CFG["requires_hf_token"])
    base_model = str(MODEL_CFG.get("base_model", "")).lower()
    preferred = str(MODEL_CFG.get("preferred_unsloth_4bit_model", "")).lower()
    return base_model.startswith("google/gemma") or "gemma" in preferred


def _get_secret(secret_name: str) -> str | None:
    try:
        from kaggle_secrets import UserSecretsClient
        value = UserSecretsClient().get_secret(secret_name)
    except Exception as exc:
        value = os.environ.get(secret_name, "")
        if _is_main_process() and not value:
            print(f"Kaggle secret/env {{secret_name}} not available: {{exc}}", flush=True)
    return value or None


def _get_hf_token() -> str | None:
    token_name = MODEL_CFG["hf_token_env"]
    if token_name not in {{"HF_API_TOKEN_2", "HF_API_TOKEN_3"}}:
        raise RuntimeError(f"Forbidden HF token name: {{token_name}}")
    token = _get_secret(token_name)
    if not token and _requires_hf_token():
        raise RuntimeError(
            f"Missing Kaggle secret/env {{token_name}} for gated model; do not use token 1"
        )
    if not token and _is_main_process():
        print(f"No {{token_name}} found; continuing without HF auth for public model.", flush=True)
    return token or None


def _wandb_settings() -> dict:
    return dict(TRAINING_CFG.get("wandb", {{}}))


def _configure_wandb(run_id: str) -> bool:
    settings = _wandb_settings()
    secret_name = str(settings.get("kaggle_secret_name", "WANDB_API_KEY"))
    candidates = [secret_name]
    for fallback in ("WANDB_API_KEY", "WANDB_API_TOKEN"):
        if fallback not in candidates:
            candidates.append(fallback)
    api_key = None
    for candidate in candidates:
        api_key = _get_secret(candidate)
        if api_key:
            break
    if not api_key:
        os.environ.setdefault("WANDB_DISABLED", "true")
        return False
    os.environ["WANDB_API_KEY"] = api_key
    os.environ.setdefault("WANDB_PROJECT", str(settings.get("project", "outfitmatch-stylist")))
    entity = str(settings.get("entity", "") or "").strip()
    if entity:
        os.environ["WANDB_ENTITY"] = entity
    os.environ.setdefault("WANDB_NAME", f"outfitmatch-{{run_id}}")
    os.environ.setdefault("WANDB_RUN_ID", f"outfitmatch-{{run_id}}")
    os.environ.setdefault("WANDB_RESUME", "allow")
    os.environ.setdefault("WANDB_SILENT", "true")
    os.environ.setdefault("WANDB_WATCH", "false")
    return True


def _checkpoint_sort_key(path: Path) -> tuple[int, str]:
    try:
        step = int(path.name.rsplit("-", 1)[-1])
    except ValueError:
        step = -1
    return step, path.name


def _latest_checkpoint_dir(output_dir: Path) -> Path | None:
    checkpoints = [path for path in output_dir.glob("checkpoint-*") if path.is_dir()]
    if not checkpoints:
        return None
    return sorted(checkpoints, key=_checkpoint_sort_key)[-1]


def _checkpoint_global_step(checkpoint_dir: Path | None) -> int:
    if checkpoint_dir is None:
        return 0
    state_path = checkpoint_dir / "trainer_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            return int(state.get("global_step", 0))
        except Exception:
            pass
    return max(0, _checkpoint_sort_key(checkpoint_dir)[0])


def _checkpoint_artifact_name(run_id: str) -> str:
    template = str(
        _wandb_settings().get(
            "checkpoint_artifact_name",
            "outfitmatch-{{run_id}}-checkpoint",
        )
    )
    return template.format(run_id=run_id)


def _restore_marker_path(output_dir: Path, checkpoint_name: str) -> Path:
    return output_dir / f".restore-complete-{{checkpoint_name}}"



def _wait_for_restored_checkpoint(
    output_dir: Path,
    checkpoint_name: str,
    *,
    timeout_seconds: int = 300,
) -> Path:
    destination = output_dir / checkpoint_name
    marker = _restore_marker_path(output_dir, checkpoint_name)
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if destination.is_dir() and marker.exists():
            return destination
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for restored checkpoint: {{destination}}")



def _copy_checkpoint_once(source: Path, output_dir: Path, *, label: str) -> Path:
    destination = output_dir / source.name
    marker = _restore_marker_path(output_dir, source.name)
    if destination.is_dir() and marker.exists():
        return destination
    if _is_main_process():
        if destination.exists():
            shutil.rmtree(destination)
        if marker.exists():
            marker.unlink()
        shutil.copytree(source, destination)
        marker.write_text(label + "\\n", encoding="utf-8")
        print(f"Restored checkpoint from {{label}}: {{destination}}", flush=True)
        return destination
    return _wait_for_restored_checkpoint(output_dir, source.name)



def _restore_checkpoint_from_dataset(output_dir: Path, dataset_root: Path) -> Path | None:
    existing = _latest_checkpoint_dir(output_dir)
    if existing is not None:
        return existing
    resume_cfg = dict(TRAINING_CFG.get("resume_checkpoint", {{}}))
    subdir = str(resume_cfg.get("packaged_subdir", "resume_checkpoint") or "").strip()
    if not subdir:
        return None
    source_root = dataset_root / subdir
    if not source_root.exists():
        return None
    candidates = [
        candidate for candidate in source_root.rglob("checkpoint-*") if candidate.is_dir()
    ]
    if not candidates:
        return None
    latest = sorted(candidates, key=_checkpoint_sort_key)[-1]
    return _copy_checkpoint_once(latest, output_dir, label="dataset bundle")



def _restore_checkpoint_from_wandb(output_dir: Path, run_id: str) -> Path | None:
    if os.environ.get("WANDB_DISABLED") == "true":
        return None
    if _latest_checkpoint_dir(output_dir) is not None:
        return _latest_checkpoint_dir(output_dir)
    project = os.environ.get("WANDB_PROJECT", "").strip()
    entity = os.environ.get("WANDB_ENTITY", "").strip()
    if not project:
        return None
    qualified_name = (
        f"{{entity}}/{{project}}/{{_checkpoint_artifact_name(run_id)}}:latest"
        if entity
        else f"{{project}}/{{_checkpoint_artifact_name(run_id)}}:latest"
    )
    try:
        import wandb

        artifact = wandb.Api().artifact(qualified_name)
        download_root = output_dir / "_wandb_resume"
        if download_root.exists():
            shutil.rmtree(download_root)
        artifact_path = Path(artifact.download(root=str(download_root)))
        restored = [
            candidate for candidate in artifact_path.rglob("checkpoint-*") if candidate.is_dir()
        ]
        if restored:
            latest = sorted(restored, key=_checkpoint_sort_key)[-1]
            return _copy_checkpoint_once(latest, output_dir, label="W&B artifact")
    except Exception as exc:
        if _is_main_process():
            print(f"W&B resume artifact unavailable: {{exc}}", flush=True)
    return None



def _upload_checkpoint_to_wandb(output_dir: Path, run_id: str, global_step: int) -> None:
    if os.environ.get("WANDB_DISABLED") == "true" or not _is_main_process():
        return
    latest = _latest_checkpoint_dir(output_dir)
    if latest is None:
        return
    try:
        import wandb

        if wandb.run is None:
            return
        artifact = wandb.Artifact(
            name=_checkpoint_artifact_name(run_id),
            type="model",
            metadata={{
                "run_id": run_id,
                "global_step": int(global_step),
                "checkpoint_dir": latest.name,
            }},
        )
        artifact.add_dir(str(latest), name=latest.name)
        logged = wandb.run.log_artifact(artifact, aliases=["latest", latest.name])
        if hasattr(logged, "wait"):
            logged.wait()
        print(f"Uploaded checkpoint artifact: {{latest.name}}", flush=True)
    except Exception as exc:
        print(f"W&B checkpoint upload failed: {{exc}}", flush=True)


def _format_messages(example, tokenizer):
    rendered = tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False
    )
    return {{"text": rendered}}


def _find_dataset_root() -> Path:
    expected = Path("/kaggle/input") / DATASET_SLUG
    if (expected / "train.jsonl").exists() and (expected / "eval.jsonl").exists():
        return expected
    candidates = []
    for train_path in Path("/kaggle/input").glob("**/train.jsonl"):
        root = train_path.parent
        if (root / "eval.jsonl").exists():
            candidates.append(root)
    if len(candidates) == 1:
        print(f"Using discovered dataset root: {{candidates[0]}}", flush=True)
        return candidates[0]
    raise FileNotFoundError(
        f"Missing normalized dataset files under {{expected}}; candidates={{candidates}}"
    )


def _load_unsloth_model(hf_token: str | None):
    import torch
    model_candidates = [MODEL_CFG.get("preferred_unsloth_4bit_model"), MODEL_CFG["base_model"]]
    last_error = None
    for model_name in [m for m in model_candidates if m]:
        try:
            from unsloth import FastModel
            model, tokenizer = FastModel.from_pretrained(
                model_name=model_name,
                max_seq_length=int(TRAINING_CFG["max_seq_length"]),
                dtype=None,
                load_in_4bit=bool(TRAINING_CFG["load_in_4bit"]),
                load_in_8bit=False,
                full_finetuning=False,
                token=hf_token,
                trust_remote_code=True,
            )
            model = FastModel.get_peft_model(
                model,
                r=int(TRAINING_CFG["lora"]["r"]),
                target_modules=TARGET_MODULES,
                lora_alpha=int(TRAINING_CFG["lora"]["alpha"]),
                lora_dropout=float(TRAINING_CFG["lora"].get("dropout", 0.0)),
                bias=str(TRAINING_CFG["lora"].get("bias", "none")),
                use_gradient_checkpointing="unsloth",
                random_state=42,
                max_seq_length=int(TRAINING_CFG["max_seq_length"]),
            )
            return model, tokenizer, model_name, "FastModel"
        except Exception as exc:
            last_error = exc
            if _is_main_process():
                print(f"FastModel failed for {{model_name}}: {{exc}}", flush=True)
        try:
            from unsloth import FastLanguageModel
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_name,
                max_seq_length=int(TRAINING_CFG["max_seq_length"]),
                dtype=torch.float16,
                load_in_4bit=bool(TRAINING_CFG["load_in_4bit"]),
                token=hf_token,
                trust_remote_code=True,
            )
            model = FastLanguageModel.get_peft_model(
                model,
                r=int(TRAINING_CFG["lora"]["r"]),
                target_modules=TARGET_MODULES,
                lora_alpha=int(TRAINING_CFG["lora"]["alpha"]),
                lora_dropout=float(TRAINING_CFG["lora"].get("dropout", 0.0)),
                bias=str(TRAINING_CFG["lora"].get("bias", "none")),
                use_gradient_checkpointing="unsloth",
                random_state=42,
                max_seq_length=int(TRAINING_CFG["max_seq_length"]),
            )
            return model, tokenizer, model_name, "FastLanguageModel"
        except Exception as exc:
            last_error = exc
            if _is_main_process():
                print(f"FastLanguageModel failed for {{model_name}}: {{exc}}", flush=True)
        try:
            from unsloth import FastVisionModel
            model, tokenizer = FastVisionModel.from_pretrained(
                model_name=model_name,
                max_seq_length=int(TRAINING_CFG["max_seq_length"]),
                dtype=torch.float16,
                load_in_4bit=bool(TRAINING_CFG["load_in_4bit"]),
                token=hf_token,
                trust_remote_code=True,
            )
            model = FastVisionModel.get_peft_model(
                model,
                finetune_vision_layers=False,
                finetune_language_layers=True,
                finetune_attention_modules=True,
                finetune_mlp_modules=True,
                r=int(TRAINING_CFG["lora"]["r"]),
                lora_alpha=int(TRAINING_CFG["lora"]["alpha"]),
                lora_dropout=float(TRAINING_CFG["lora"].get("dropout", 0.0)),
                bias=str(TRAINING_CFG["lora"].get("bias", "none")),
                random_state=42,
                use_gradient_checkpointing="unsloth",
            )
            return model, tokenizer, model_name, "FastVisionModel"
        except Exception as exc:
            last_error = exc
            if _is_main_process():
                print(f"FastVisionModel failed for {{model_name}}: {{exc}}", flush=True)
    raise RuntimeError(f"Could not load any Unsloth model candidate: {{last_error}}")




def _identity_decorator(*args, **kwargs):
    if args and len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def _wrap(obj):
        return obj

    return _wrap


def _patch_unsloth_auto_docstring() -> None:
    import site
    import torch as _torch_for_unsloth_patch

    kaggle_input = Path("/kaggle/input")
    wheelhouse_candidate = None
    if kaggle_input.is_dir():
        for candidate in sorted(kaggle_input.glob("**/wheelhouse*")):
            if candidate.is_dir() and any(candidate.glob("*.whl")):
                wheelhouse_candidate = candidate
                break
    if wheelhouse_candidate is None:
        if _is_main_process():
            print("Skipping Unsloth compatibility patch: no wheelhouse found", flush=True)
        return

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    wheelhouse_str = str(wheelhouse_candidate)
    try:
        while wheelhouse_str in sys.path:
            sys.path.remove(wheelhouse_str)
    except ValueError:
        pass
    sys.path.insert(0, wheelhouse_str)
    sys.path.insert(0, wheelhouse_str)
    if _is_main_process():
        print(f"Added wheelhouse to sys.path: {{wheelhouse_candidate}}", flush=True)

    def _find_site_file(relative_path: str) -> Path | None:
        search_roots = [Path(root) for root in site.getsitepackages()]
        user_site = site.getusersitepackages()
        if user_site:
            search_roots.append(Path(user_site))
        for root in search_roots:
            candidate = root / relative_path
            if candidate.is_file():
                return candidate
        return None

    def _patch_installed_unsloth_utils() -> None:
        utils_path = _find_site_file("unsloth/models/_utils.py")
        if utils_path is None:
            if _is_main_process():
                print("Skipping Unsloth compatibility patch: _utils.py not found", flush=True)
            return

        text = utils_path.read_text(encoding="utf-8", errors="ignore")
        original = text

        import_anchor = "from transformers import PretrainedConfig\\n"
        compat_imports = (
            "from transformers.configuration_utils import PretrainedConfig as PreTrainedConfig\\n"
            "from transformers.utils.auto_docstring import auto_docstring\\n"
            "from transformers.models.llama.configuration_llama import LlamaConfig\\n"
            "from transformers.models.mistral.configuration_mistral import MistralConfig\\n"
            "from transformers.models.gemma.configuration_gemma import GemmaConfig\\n"
            "from transformers.models.gemma2.configuration_gemma2 import Gemma2Config\\n"
            "from transformers.models.qwen2.configuration_qwen2 import Qwen2Config\\n"
            "from transformers.models.granite.configuration_granite import GraniteConfig\\n"
            "from transformers.models.qwen3.configuration_qwen3 import Qwen3Config\\n"
            "from transformers.models.qwen3_moe.configuration_qwen3_moe import Qwen3MoeConfig\\n"
            "from transformers.models.falcon_h1.configuration_falcon_h1 import FalconH1Config\\n"
            "from transformers.modeling_rope_utils import (\\n"
            "    ROPE_INIT_FUNCTIONS,\\n"
            "    RopeParameters,\\n"
            "    rope_config_validation,\\n"
            ")\\n"
            "\\n"
            "def strict(*args, **kwargs):\\n"
            "    if args and len(args) == 1 and callable(args[0]) and not kwargs:\\n"
            "        return args[0]\\n"
            "\\n"
            "    def _wrap(obj):\\n"
            "        return obj\\n"
            "\\n"
            "    return _wrap\\n"
        )
        if (
            "from transformers.utils.auto_docstring import auto_docstring" not in text
            and import_anchor in text
        ):
            text = text.replace(import_anchor, import_anchor + compat_imports, 1)

        compile_start = text.find("# Torch compile settings")
        compile_end = text.find("del accelerate", compile_start)
        if (
            compile_start != -1
            and compile_end != -1
            and "_UNSLOTH_TORCH_COMPILE_PATCHED" not in text
        ):
            compile_end = text.find("\\n", compile_end)
            if compile_end == -1:
                compile_end = len(text)
            else:
                compile_end += 1
            replacement = (
                "# Torch compile settings\\n"
                "UNSLOTH_COMPILE_DEBUG = False\\n"
                "UNSLOTH_COMPILE_MAXIMUM = False\\n"
                "UNSLOTH_COMPILE_IGNORE_ERRORS = True\\n"
                "_UNSLOTH_TORCH_COMPILE_PATCHED = True\\n"
                "\\n"
                "@functools.lru_cache(None)\\n"
                "def is_big_gpu(index) -> bool:\\n"
                "    return False\\n"
                "\\n"
                "torch_compile_options = {{}}\\n"
                "\\n"
                "def torch_compile_kwargs(*args, **kwargs):\\n"
                "    return {{\\"dynamic\\": False, \\"fullgraph\\": False, "
                "\\"options\\": torch_compile_options}}\\n"
            )
            text = text[:compile_start] + replacement + text[compile_end:]

        if text != original:
            utils_path.write_text(text, encoding="utf-8")
            if _is_main_process():
                print(
                    "Patched installed unsloth/models/_utils.py for transformers compatibility: "
                    f"{{utils_path}}",
                    flush=True,
                )
        elif _is_main_process():
            print("Installed unsloth/models/_utils.py already patched", flush=True)


    def _patch_installed_unsloth_vision() -> None:
        vision_path = _find_site_file("unsloth/models/vision.py")
        if vision_path is None:
            if _is_main_process():
                print("Skipping Unsloth compatibility patch: vision.py not found", flush=True)
            return

        text = vision_path.read_text(encoding="utf-8", errors="ignore")
        original = text
        old_import = "from transformers import GenerationConfig, CompileConfig, HybridCache"
        new_import = chr(10).join(
            [
                "from transformers import GenerationConfig, CompileConfig",
                "try:",
                "    from transformers import HybridCache",
                "except ImportError:",
                "    try:",
                "        from transformers.cache_utils import HybridCache",
                "    except ImportError:",
                "        from typing import Any as HybridCache",
            ]
        )
        if old_import in text and "from transformers.cache_utils import HybridCache" not in text:
            text = text.replace(old_import, new_import, 1)

        if text != original:
            vision_path.write_text(text, encoding="utf-8")
            if _is_main_process():
                print(
                    "Patched installed unsloth/models/vision.py for HybridCache compatibility: "
                    f"{{vision_path}}",
                    flush=True,
                )
        elif _is_main_process():
            print("Installed unsloth/models/vision.py already patched", flush=True)

    def _patch_installed_unsloth_llama_rl() -> None:
        llama_path = _find_site_file("unsloth/models/llama.py")
        if llama_path is None:
            if _is_main_process():
                print("Skipping Unsloth compatibility patch: llama.py not found", flush=True)
            return

        text = llama_path.read_text(encoding="utf-8", errors="ignore")
        original = text
        old_call = "PatchFastRL(FastLanguageModel = FastLlamaModel)"
        new_call = "pass  # OM_SKIP_UNSLOTH_RL_PATCH skipped PatchFastRL"
        if old_call in text and "OM_SKIP_UNSLOTH_RL_PATCH" not in text:
            text = text.replace(old_call, new_call, 1)

        if text != original:
            llama_path.write_text(text, encoding="utf-8")
            if _is_main_process():
                print(
                    "Patched installed unsloth/models/llama.py to skip RL trainer patch: "
                    f"{{llama_path}}",
                    flush=True,
                )
        elif _is_main_process():
            print("Installed unsloth/models/llama.py already patched", flush=True)
    _patch_installed_unsloth_utils()
    _patch_installed_unsloth_vision()
    _patch_installed_unsloth_llama_rl()

    _ORIGINAL_TORCH_COMPILE = getattr(_torch_for_unsloth_patch, "compile", None)

    def _identity_torch_compile(fn=None, *args, **kwargs):
        if fn is not None and callable(fn):
            return fn

        def _wrap(obj):
            return obj

        return _wrap

    if _ORIGINAL_TORCH_COMPILE is not None:
        _torch_for_unsloth_patch.compile = _identity_torch_compile

    if not hasattr(_torch_for_unsloth_patch.nn.Module, "set_submodule"):
        def _om_set_submodule(self, target, module, strict=False):
            if target == "":
                raise ValueError("Cannot set the root module via set_submodule")
            atoms = target.split(".")
            parent_path = ".".join(atoms[:-1])
            parent = self.get_submodule(parent_path) if parent_path else self
            if strict and not hasattr(parent, atoms[-1]):
                raise AttributeError("Target submodule does not exist")
            setattr(parent, atoms[-1], module)

        _torch_for_unsloth_patch.nn.Module.set_submodule = _om_set_submodule
        if _is_main_process():
            print("Patched torch.nn.Module.set_submodule for Unsloth compatibility", flush=True)

    try:
        import torch._inductor as _torch_inductor
        import torch._inductor.config as _torch_inductor_config

        if not hasattr(_torch_inductor, "config"):
            _torch_inductor.config = _torch_inductor_config
            if _is_main_process():
                print("Patched torch._inductor.config attribute for unsloth_zoo", flush=True)
    except Exception as exc:
        if _is_main_process():
            print(f"Skipping torch._inductor.config compatibility patch: {{exc}}", flush=True)

    try:
        import unsloth  # noqa: F401
    finally:
        if _ORIGINAL_TORCH_COMPILE is not None:
            _torch_for_unsloth_patch.compile = _ORIGINAL_TORCH_COMPILE

    if _is_main_process():
        print(
            "Unsloth loaded successfully with patched installed transformers compatibility",
            flush=True,
        )


def main() -> None:
    dataset_root = _find_dataset_root()
    _install(dataset_root)
    _maybe_relaunch_torchrun()

    import torch

    _configure_cuda_device_for_ddp()
    _debug_torch_cuda()
    _require_torch_cuda()
    _patch_unsloth_auto_docstring()
    import unsloth  # noqa: F401
    from datasets import load_dataset
    from huggingface_hub import login
    from transformers import (
        DataCollatorForLanguageModeling,
        Trainer,
        TrainerCallback,
        TrainingArguments,
    )

    hf_token = _get_hf_token()
    if hf_token:
        login(token=hf_token, add_to_git_credential=False)

    train_path = dataset_root / "train.jsonl"
    eval_path = dataset_root / "eval.jsonl"

    model, tokenizer, loaded_model_name, loader_name = _load_unsloth_model(hf_token)
    dataset = load_dataset("json", data_files={{"train": str(train_path), "eval": str(eval_path)}})
    text_dataset = dataset.map(
        lambda row: _format_messages(row, tokenizer),
        remove_columns=dataset["train"].column_names,
    )

    lm_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
    if getattr(lm_tokenizer, "pad_token", None) is None:
        lm_tokenizer.pad_token = lm_tokenizer.eos_token

    def _tokenize(batch):
        return lm_tokenizer(
            batch["text"],
            truncation=True,
            max_length=int(TRAINING_CFG["max_seq_length"]),
            padding=False,
        )

    tokenized_dataset = text_dataset.map(
        _tokenize,
        batched=True,
        remove_columns=["text"],
    )

    run_id = MODEL_CFG["run_id"]
    output_dir = Path(TRAINING_CFG["output_root"]) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    report_to = list(TRAINING_CFG.get("report_to", []))
    if not _configure_wandb(run_id):
        report_to = []

    resume_checkpoint = _latest_checkpoint_dir(output_dir)
    if resume_checkpoint is None:
        resume_checkpoint = _restore_checkpoint_from_dataset(output_dir, dataset_root)
    if resume_checkpoint is None:
        resume_checkpoint = _restore_checkpoint_from_wandb(output_dir, run_id)
    resume_step = _checkpoint_global_step(resume_checkpoint)
    session_step_limit = int(TRAINING_CFG.get("max_session_steps", 0) or 0)

    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=int(TRAINING_CFG["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(TRAINING_CFG["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(TRAINING_CFG["gradient_accumulation_steps"]),
        num_train_epochs=float(TRAINING_CFG["num_train_epochs"]),
        learning_rate=float(TRAINING_CFG["learning_rate"]),
        warmup_ratio=float(TRAINING_CFG["warmup_ratio"]),
        lr_scheduler_type=str(TRAINING_CFG["lr_scheduler_type"]),
        optim=str(TRAINING_CFG["optim"]),
        weight_decay=float(TRAINING_CFG["weight_decay"]),
        fp16=True,
        bf16=False,
        logging_steps=int(TRAINING_CFG["logging_steps"]),
        eval_strategy="steps",
        eval_steps=int(TRAINING_CFG["eval_steps"]),
        save_strategy="steps",
        save_steps=int(TRAINING_CFG["save_steps"]),
        save_total_limit=int(TRAINING_CFG["save_total_limit"]),
        report_to=report_to,
        run_name=f"outfitmatch-{{run_id}}",
        ddp_find_unused_parameters=bool(
            TRAINING_CFG.get("ddp", {{}}).get("ddp_find_unused_parameters", False)
        ),
        remove_unused_columns=False,
        dataloader_num_workers=2,
        seed=42,
    )

    class SessionLimitCallback(TrainerCallback):
        def __init__(self, start_step: int, step_limit: int):
            self.start_step = max(0, int(start_step))
            self.step_limit = max(0, int(step_limit))
            self.triggered = False

        def on_step_end(self, args, state, control, **kwargs):
            if self.triggered or self.step_limit <= 0:
                return control
            progressed = int(state.global_step) - self.start_step
            if progressed >= self.step_limit:
                self.triggered = True
                control.should_save = True
                control.should_training_stop = True
                if _is_main_process():
                    print(
                        f"Stopping after session step budget: +{{progressed}} steps "
                        f"from global_step={{self.start_step}}",
                        flush=True,
                    )
            return control

    class WandbCheckpointCallback(TrainerCallback):
        def __init__(self, run_id: str, output_dir: Path):
            self.run_id = run_id
            self.output_dir = output_dir

        def on_save(self, args, state, control, **kwargs):
            _upload_checkpoint_to_wandb(
                self.output_dir,
                self.run_id,
                int(getattr(state, "global_step", 0)),
            )
            return control

        def on_train_end(self, args, state, control, **kwargs):
            _upload_checkpoint_to_wandb(
                self.output_dir,
                self.run_id,
                int(getattr(state, "global_step", 0)),
            )
            return control

    callbacks = []
    if session_step_limit > 0:
        callbacks.append(SessionLimitCallback(resume_step, session_step_limit))
    if report_to:
        callbacks.append(WandbCheckpointCallback(run_id, output_dir))

    data_collator = DataCollatorForLanguageModeling(tokenizer=lm_tokenizer, mlm=False)
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["eval"],
        data_collator=data_collator,
        callbacks=callbacks,
    )
    if _is_main_process():
        print(json.dumps({{
            "run_id": run_id,
            "loaded_model_name": loaded_model_name,
            "loader": loader_name,
            "gpu_count": torch.cuda.device_count(),
            "train_rows": len(tokenized_dataset["train"]),
            "eval_rows": len(tokenized_dataset["eval"]),
            "effective_batch_size": int(TRAINING_CFG["per_device_train_batch_size"])
            * max(1, torch.cuda.device_count())
            * int(TRAINING_CFG["gradient_accumulation_steps"]),
            "resume_checkpoint": str(resume_checkpoint) if resume_checkpoint else None,
            "resume_step": resume_step,
            "session_step_limit": session_step_limit,
            "wandb_enabled": bool(report_to),
        }}, ensure_ascii=False, indent=2), flush=True)

    trainer.train(resume_from_checkpoint=str(resume_checkpoint) if resume_checkpoint else None)
    trainer.save_model(str(output_dir / "adapter"))
    tokenizer.save_pretrained(str(output_dir / "adapter"))

    if _is_main_process():
        summary_path = output_dir / "training_summary.json"
        summary_path.write_text(json.dumps({{
            "run_id": run_id,
            "base_model": MODEL_CFG["base_model"],
            "loaded_model_name": loaded_model_name,
            "loader": loader_name,
            "hf_token_env": MODEL_CFG["hf_token_env"],
            "output_dir": str(output_dir),
            "resume_checkpoint": str(resume_checkpoint) if resume_checkpoint else None,
            "resume_step": resume_step,
            "session_step_limit": session_step_limit,
            "wandb_enabled": bool(report_to),
            "wandb_project": os.environ.get("WANDB_PROJECT"),
            "wandb_entity": os.environ.get("WANDB_ENTITY"),
        }}, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
        archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
        print(f"Saved QLoRA adapter archive: {{archive}}", flush=True)


if __name__ == "__main__":
    main()
'''


def write_kernel_packages(
    config: dict[str, Any], package_root: Path, *, dataset_id: str, dataset_slug: str
) -> list[dict[str, str]]:
    """Write one Kaggle kernel directory per model and return manifest rows."""
    kaggle = config["kaggle"]
    owner = _safe_slug(str(kaggle["owner"]))
    prefix = _safe_slug(str(kaggle["kernel_slug_prefix"]), max_len=30)
    rows: list[dict[str, str]] = []
    for model in config["models"]:
        run_id = _safe_slug(str(model["run_id"]), max_len=30)
        kernel_slug = _safe_slug(f"{prefix}-{run_id}", max_len=50)
        kernel_dir = package_root / f"kaggle_kernel_{run_id}"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        code_file = f"train_{run_id}.py"
        (kernel_dir / code_file).write_text(
            _kernel_script(config, model, dataset_slug), encoding="utf-8"
        )
        extra_dataset_sources = [str(source) for source in kaggle.get("extra_dataset_sources", [])]
        metadata = {
            "id": f"{owner}/{kernel_slug}",
            "title": kernel_slug,
            "code_file": code_file,
            "language": "python",
            "kernel_type": "script",
            "is_private": str(bool(kaggle.get("is_private", True))).lower(),
            "enable_gpu": str(bool(kaggle.get("enable_gpu", True))).lower(),
            "enable_tpu": "false",
            "enable_internet": str(bool(kaggle.get("enable_internet", True))).lower(),
            "dataset_sources": [dataset_id, *extra_dataset_sources],
            "competition_sources": [],
            "kernel_sources": [],
            "model_sources": [],
            "machine_shape": str(kaggle.get("machine_shape", "NvidiaTeslaT4")),
        }
        (kernel_dir / "kernel-metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rows.append(
            {
                "run_id": str(model["run_id"]),
                "kernel_id": metadata["id"],
                "kernel_dir": str(kernel_dir),
                "code_file": str(kernel_dir / code_file),
                "hf_token_env": str(model["hf_token_env"]),
            }
        )
    return rows


def push_with_kaggle_cli(
    package_root: Path,
    kernel_rows: list[dict[str, str]],
    *,
    env_file: Path,
    token_env_var: str,
    username_env_var: str | None,
) -> list[str]:
    """Push the dataset and kernels with Kaggle CLI, returning command summaries."""
    dataset_dir = package_root / "kaggle_dataset"
    commands: list[tuple[list[str], Path]] = [
        (["kaggle", "datasets", "create", "-p", ".", "-r", "zip"], dataset_dir),
    ]
    commands.extend(
        (["kaggle", "kernels", "push", "-p", "."], Path(row["kernel_dir"])) for row in kernel_rows
    )

    env = os.environ.copy()
    token = resolve_env_value(token_env_var, env_file)
    if not token:
        raise RuntimeError(
            f"Missing Kaggle token '{token_env_var}'. Set it in the environment or {env_file}."
        )
    env["KAGGLE_API_TOKEN"] = token
    username = resolve_env_value(username_env_var, env_file) if username_env_var else None
    if not username:
        metadata_path = dataset_dir / "dataset-metadata.json"
        if metadata_path.exists():
            try:
                dataset_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                dataset_id = str(dataset_meta.get("id", ""))
                if "/" in dataset_id:
                    username = dataset_id.split("/", 1)[0].strip()
            except Exception:
                username = None
    if not username:
        for row in kernel_rows:
            kernel_id = str(row.get("kernel_id", ""))
            if "/" in kernel_id:
                username = kernel_id.split("/", 1)[0].strip()
                break
    if username:
        env["KAGGLE_USERNAME"] = username

    summaries: list[str] = []
    for command, cwd in commands:
        try:
            completed = subprocess.run(
                command,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
                cwd=cwd,
            )
        except subprocess.CalledProcessError as exc:
            output = "\n".join(part for part in [exc.stdout, exc.stderr] if part)
            if command[:3] == ["kaggle", "datasets", "create"]:
                version_cmd = [
                    "kaggle",
                    "datasets",
                    "version",
                    "-p",
                    ".",
                    "-m",
                    "update",
                    "-r",
                    "zip",
                ]
                completed = subprocess.run(
                    version_cmd,
                    check=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    env=env,
                    cwd=dataset_dir,
                )
                summaries.append(f"(cd {dataset_dir}) {' '.join(version_cmd)}")
                if completed.stdout:
                    summaries.append(completed.stdout.strip())
                continue
            raise RuntimeError(output or exc.stderr or exc.stdout) from exc
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        if command[:3] == ["kaggle", "datasets", "create"] and "already in use" in output:
            version_cmd = ["kaggle", "datasets", "version", "-p", ".", "-m", "update", "-r", "zip"]
            completed = subprocess.run(
                version_cmd,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
                cwd=dataset_dir,
            )
            summaries.append(f"(cd {dataset_dir}) {' '.join(version_cmd)}")
            if completed.stdout:
                summaries.append(completed.stdout.strip())
            continue
        summaries.append(f"(cd {cwd}) {' '.join(command)}")
        if output:
            summaries.append(output.strip())
    return summaries


def build_package(
    config_path: Path,
    *,
    clean: bool,
    push: bool,
    env_file: Path = Path(".env.local"),
    kaggle_token_env_var: str = "KAGGLE_API_TOKEN_4",
    kaggle_username_env_var: str | None = None,
) -> dict[str, Any]:
    """Build the Kaggle package and optionally push it."""
    config = load_config(config_path)
    package_root = Path(str(config["outputs"]["package_root"]))
    if clean and package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True, exist_ok=True)

    dataset_manifest = normalize_dataset(config, package_root)
    wheelhouse_manifest = build_bootstrap_wheelhouse(config, package_root)
    resume_checkpoint_manifest = stage_resume_checkpoint(config, package_root)
    dataset_meta = write_dataset_metadata(config, package_root)
    kernel_rows = write_kernel_packages(
        config,
        package_root,
        dataset_id=dataset_meta["dataset_id"],
        dataset_slug=dataset_meta["dataset_slug"],
    )
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config_path": str(config_path),
        "task": config.get("task"),
        "mode": config.get("mode"),
        "constraints": {
            "dataset_source_mode": config["dataset"]["source_mode"],
            "allowed_hf_token_env_vars": config["secrets"]["allowed_hf_token_env_vars"],
            "framework": config["training"]["framework"],
            "strategy": config["training"]["strategy"],
            "machine_shape": config["kaggle"]["machine_shape"],
        },
        "dataset": {**dataset_manifest, **dataset_meta},
        "bootstrap_wheelhouse": wheelhouse_manifest,
        "resume_checkpoint": resume_checkpoint_manifest,
        "kernels": kernel_rows,
        "push_commands": [],
    }
    if push:
        manifest["push_commands"] = push_with_kaggle_cli(
            package_root,
            kernel_rows,
            env_file=env_file,
            token_env_var=kaggle_token_env_var,
            username_env_var=kaggle_username_env_var,
        )

    manifest_path = Path(str(config["outputs"]["manifest"]))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--clean", action="store_true", help="Remove old package output first")
    parser.add_argument("--push", action="store_true", help="Push dataset/kernels with Kaggle CLI")
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--kaggle-token-env-var", default="KAGGLE_API_TOKEN_4")
    parser.add_argument("--kaggle-username-env-var")
    args = parser.parse_args()

    manifest = build_package(
        args.config,
        clean=args.clean,
        push=args.push,
        env_file=args.env_file,
        kaggle_token_env_var=args.kaggle_token_env_var,
        kaggle_username_env_var=args.kaggle_username_env_var,
    )
    manifest_path = Path(str(load_config(args.config)["outputs"]["manifest"]))
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "train_examples": manifest["dataset"]["train_examples"],
                "eval_examples": manifest["dataset"]["eval_examples"],
                "kernels": [row["kernel_id"] for row in manifest["kernels"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
