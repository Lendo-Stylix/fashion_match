# OutfitMatch — Experiment-Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a config-driven, W&B-tracked experiment harness for OutfitMatch, then run Scrum/XP experiment cycles that systematically vary (a) dataset type, (b) number of training rows, and (c) model, to select the best catalog encoder, body pipeline, and outfit composer.

**Architecture:** Every experiment is a single YAML config consumed by one CLI entrypoint (`om-exp run <config>`). The harness loads a HuggingFace dataset (with a row cap), instantiates an encoder behind a `BaseEncoder` ABC, runs train/eval, and logs every metric + the resolved config to Weights & Biases. Scrum sprints map 1:1 to experiment cycles; each cycle is a *grid* over one axis (dataset / rows / model) holding the others fixed. TDD on all harness code; models are validated by metric thresholds, not unit tests.

**Tech Stack:** Python 3.13, `uv`, PyTorch ≥2.12, `open_clip_torch` (FashionSigLIP/FashionCLIP), `transformers` (CLIP baselines, ViT), `ultralytics` (YOLO-pose), `datasets` (HF), `qdrant-client`, `wandb`, `pytest`/`ruff`/`mypy`, `pydantic` v2, `typer`.

---

## Research Findings: Model & Dataset Selection

This section records the HuggingFace research that drives every model/dataset choice below. Cite it in the final report's Related Work / Method sections.

### Catalog Encoder (the highest-graded model choice)

| Model | Arch | Params | Downloads | License | Verdict |
|---|---|---:|---:|---|---|
| **[Marqo/marqo-fashionSigLIP](https://hf.co/Marqo/marqo-fashionSigLIP)** | SigLIP | 203M | 8.4M | Apache-2.0 | **PRIMARY** — SOTA fashion retrieval, trained with Generalised Contrastive Learning on 7 fashion datasets, sigmoid loss matches our planned SigLIP fine-tuning, permissive license |
| [patrickjohncyh/fashion-clip](https://hf.co/patrickjohncyh/fashion-clip) | CLIP | 151M | 109.5M | MIT | Ablation baseline — most-used fashion encoder (2023), domain CLIP |
| [Marqo/marqo-fashionCLIP](https://hf.co/Marqo/marqo-fashionCLIP) | CLIP | 150M | 463K | Apache-2.0 | Ablation baseline — Marqo's CLIP variant, same training recipe as SigLIP variant |
| [openai/clip-vit-base-patch32](https://hf.co/openai/clip-vit-base-patch32) | CLIP | 151M | — | MIT | Ablation floor — generic zero-shot CLIP (the plan's stated baseline) |

**Decision:** Fine-tune `Marqo/marqo-fashionSigLIP` via `open_clip`. Ablation 1 compares: CLIP-ZS → FashionCLIP-ZS → FashionSigLIP-ZS → **FashionSigLIP fine-tuned (our contribution)**. Target: ≥+5% Recall@5 over CLIP-ZS.

### Body Pipeline

- No body-shape-labelled dataset exists on HF (searched — zero results). Therefore body-shape labels are **derived from pose keypoint ratios** (rule-based v0), then optionally distilled into a ViT classifier (v1). This matches the existing storymap (a3-s1, a3-s2).
- Pose model: `ultralytics` pip package, weights auto-downloaded (`yolov8n-pose.pt`, `yolo11n-pose.pt`). HF mirrors ([Xenova/yolov8n-pose](https://hf.co/Xenova/yolov8n-pose), [AXERA-TECH/YOLO11-Pose](https://hf.co/AXERA-TECH/YOLO11-Pose)) are not used — the pip package is the Python-3.13-safe path (per `TECH_STACK_PY313.md`). Experiment axis: YOLOv8n-pose vs YOLO11n-pose.
- Body-shape ViT distillation base: `google/vit-base-patch16-224`.

### Outfit Composer

- Reference architecture: **OutfitTransformer** (Sarkar et al. 2022, [hf.co/papers/2204.04812](https://hf.co/papers/2204.04812)) — task-specific tokens + self-attention + set-wise ranking loss. No pretrained weights on HF → implement from scratch (matches storymap a5-s1).

### Datasets

| HF Dataset | Rows | Size | Schema (key cols) | Role |
|---|---:|---:|---|---|
| [Marqo/deepfashion-inshop](https://hf.co/datasets/Marqo/deepfashion-inshop) | 52.6K | 216 MB | image, category1-3, color, description, text, item_ID | Encoder retrieval train/eval |
| [Marqo/deepfashion-multimodal](https://hf.co/datasets/Marqo/deepfashion-multimodal) | 42.5K | 153 MB | image, category1-3, text, item_ID | Attribute extractor |
| [Marqo/fashion200k](https://hf.co/datasets/Marqo/fashion200k) | 201.6K | 3.5 GB | image, category1-3, text, item_ID | Large-scale fine-tune signal |
| [owj0421/polyvore-outfits](https://hf.co/datasets/owj0421/polyvore-outfits) | 413.8K | small (JSON) | example_id, items (list[str]), label | Composer: FITB + compatibility |
| [mvasil/polyvore-outfits](https://hf.co/datasets/mvasil/polyvore-outfits) | 100K–1M | parquet | (gated) | Fallback (original author) |

**Key finding:** `owj0421/polyvore-outfits` ships ready-made configs that map directly to our metrics and give us the dataset-axis experiment grid for free:

- `{disjoint,nondisjoint}_compatibility` (3 cols: example_id, items, label) → compatibility AUC
- `{disjoint,nondisjoint}_fill_in_the_blank` (5 cols) → FITB accuracy
- `{disjoint,nondisjoint}_default` (2 cols) → outfit sets
- `disjoint` train = 17K outfits (hard, no item overlap); `nondisjoint` train = 53K (easier). This *is* the dataset-type × row-count experiment axis.

---

## Experiment Axes (what every cycle varies)

Each Scrum sprint runs a **grid over exactly one axis, holding the others fixed**:

1. **Dataset type** — deepfashion-inshop vs fashion200k vs both; polyvore disjoint vs nondisjoint.
2. **Number of rows** — data-scaling curve: `5_000 / 25_000 / 100_000 / null(all)`.
3. **Model** — clip-zs / fashionclip-zs / fashionsiglip-zs / fashionsiglip-finetuned; yolov8 vs yolo11; composer depth/heads.
4. **Conditioning** — body on/off, occasion on/off (composer only).

The harness makes a cycle = "loop N configs that differ on one field". W&B `group` = sprint name, `job_type` = axis, so cross-runs are charted automatically.

---

## File Structure

```
src/outfitmatch/
  __init__.py
  config.py            # Pydantic ExperimentConfig + loader
  seeding.py           # set_seed
  tracking.py          # W&B init wrapper (offline-safe)
  cli.py               # `om-exp` Typer app: run / sweep
  data/
    __init__.py
    base.py            # BaseFashionDataset ABC
    retrieval.py       # RetrievalDataset (DeepFashion/Fashion200K image+text)
    polyvore.py        # PolyvoreFITBDataset, PolyvoreCompatDataset
  encoders/
    __init__.py
    base.py            # BaseEncoder ABC
    openclip_encoder.py# FashionSigLIP / FashionCLIP via open_clip
    hf_clip_encoder.py # openai CLIP / fashion-clip via transformers
  metrics/
    __init__.py
    retrieval.py       # recall_at_k, mean_average_precision
    outfit.py          # fitb_accuracy, compatibility_auc
  train/
    __init__.py
    contrastive.py     # SigLIPContrastiveTrainer
    composer.py        # OutfitTransformer model + trainer
  body/
    __init__.py
    pose.py            # PoseExtractor (ultralytics wrapper)
    shape_rules.py     # keypoints -> 5-class body shape (rule-based v0)
  eval/
    __init__.py
    retrieval_eval.py  # evaluate_retrieval(encoder, dataset) -> dict
configs/
  encoder/             # one YAML per encoder experiment
  composer/
  body/
tests/
  conftest.py
  test_config.py
  test_data_retrieval.py
  test_data_polyvore.py
  test_encoders.py
  test_metrics_retrieval.py
  test_metrics_outfit.py
  test_body_shape_rules.py
  test_cli.py
docs/experiments/      # per-cycle markdown result logs
```

Responsibilities: `config.py` is the single source of experiment truth; `data/` only loads & caps rows; `encoders/` only embed; `metrics/` are pure functions (trivial to TDD); `eval/` composes encoder+dataset+metrics; `cli.py` wires a config into a run. Files split by responsibility so each is independently reviewable.

---

## SPRINT 0 — Repo & Harness Foundation (Storymap a1-s2, a1-s3)

**Sprint goal:** `uv sync` green, `pytest` green, `om-exp run <config>` executes an end-to-end no-op run logged to W&B (offline). XP: this is the infrastructure spike — everything else depends on it.

### Task 0.1: Project skeleton + pyproject

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `src/outfitmatch/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `.python-version`**

```
3.13
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "outfitmatch"
version = "0.1.0"
description = "Body & Occasion-Aware Fashion Recommender"
requires-python = ">=3.13"
dependencies = [
    "torch>=2.12",
    "torchvision>=0.26",
    "open-clip-torch>=2.26",
    "transformers>=4.52",
    "datasets>=3.2",
    "huggingface-hub>=0.30",
    "ultralytics>=8.3",
    "pillow>=11.0",
    "numpy>=2.1",
    "scikit-learn>=1.6",
    "qdrant-client>=1.12",
    "wandb>=0.19",
    "pydantic>=2.10",
    "pyyaml>=6.0",
    "typer>=0.15",
    "rich>=13.9",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
]

[project.scripts]
om-exp = "outfitmatch.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/outfitmatch"]

[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 3: Create `src/outfitmatch/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import os

os.environ["WANDB_MODE"] = "offline"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
```

- [ ] **Step 5: Sync and verify**

Run: `uv sync --group dev`
Expected: resolves and installs without error; creates `.venv`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version src/outfitmatch/__init__.py tests/conftest.py
git commit -m "chore: project skeleton with uv + pytest + ruff config"
```

### Task 0.2: ExperimentConfig schema (TDD)

**Files:**
- Create: `src/outfitmatch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import textwrap
from pathlib import Path

import pytest

from outfitmatch.config import ExperimentConfig, load_config


def test_load_minimal_config(tmp_path: Path):
    yaml_text = textwrap.dedent("""
        name: enc-clip-zs
        seed: 42
        task: retrieval
        model:
          kind: hf_clip
          checkpoint: openai/clip-vit-base-patch32
          finetune: false
        dataset:
          hf_id: Marqo/deepfashion-inshop
          config: default
          split: data
          max_rows: 5000
        train:
          epochs: 1
          batch_size: 32
          lr: 1.0e-5
    """)
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    cfg = load_config(p)
    assert isinstance(cfg, ExperimentConfig)
    assert cfg.name == "enc-clip-zs"
    assert cfg.dataset.max_rows == 5000
    assert cfg.model.finetune is False


def test_invalid_task_rejected(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("name: x\nseed: 1\ntask: NOPE\nmodel:\n  kind: hf_clip\n  checkpoint: a\ndataset:\n  hf_id: a\ntrain: {}\n")
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: outfitmatch.config`.

- [ ] **Step 3: Implement `src/outfitmatch/config.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    kind: Literal["hf_clip", "open_clip"]
    checkpoint: str
    pretrained: str | None = None  # open_clip pretrained tag
    finetune: bool = False


class DatasetConfig(BaseModel):
    hf_id: str
    config: str | None = None
    split: str = "data"
    max_rows: int | None = None


class TrainConfig(BaseModel):
    epochs: int = 1
    batch_size: int = 32
    lr: float = 1e-5
    weight_decay: float = 0.0
    num_workers: int = 2


class ExperimentConfig(BaseModel):
    name: str
    seed: int = 42
    task: Literal["retrieval", "fitb", "compatibility"]
    model: ModelConfig
    dataset: DatasetConfig
    train: TrainConfig = Field(default_factory=TrainConfig)
    wandb_project: str = "outfitmatch-grading"


def load_config(path: str | Path) -> ExperimentConfig:
    data = yaml.safe_load(Path(path).read_text())
    return ExperimentConfig.model_validate(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/config.py tests/test_config.py
git commit -m "feat: pydantic ExperimentConfig + yaml loader"
```

### Task 0.3: Seeding + W&B tracking wrapper (TDD)

**Files:**
- Create: `src/outfitmatch/seeding.py`
- Create: `src/outfitmatch/tracking.py`
- Test: `tests/test_tracking.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tracking.py
from outfitmatch.config import ExperimentConfig
from outfitmatch.seeding import set_seed
from outfitmatch.tracking import start_run


def _cfg() -> ExperimentConfig:
    return ExperimentConfig.model_validate({
        "name": "t", "seed": 7, "task": "retrieval",
        "model": {"kind": "hf_clip", "checkpoint": "x"},
        "dataset": {"hf_id": "y"}, "train": {},
    })


def test_set_seed_is_deterministic():
    set_seed(123)
    import random
    a = random.random()
    set_seed(123)
    assert random.random() == a


def test_start_run_offline_returns_run():
    run = start_run(_cfg(), group="sprint0", job_type="smoke")
    run.log({"dummy": 1.0})
    run.finish()
    assert run is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tracking.py -v`
Expected: FAIL — `ModuleNotFoundError: outfitmatch.seeding`.

- [ ] **Step 3: Implement `src/outfitmatch/seeding.py`**

```python
from __future__ import annotations

import os
import random

import numpy as np
import torch


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
```

- [ ] **Step 4: Implement `src/outfitmatch/tracking.py`**

```python
from __future__ import annotations

import wandb

from outfitmatch.config import ExperimentConfig


def start_run(cfg: ExperimentConfig, group: str, job_type: str):
    return wandb.init(
        project=cfg.wandb_project,
        name=cfg.name,
        group=group,
        job_type=job_type,
        config=cfg.model_dump(),
        reinit=True,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_tracking.py -v`
Expected: PASS (2 passed). W&B writes to `./wandb/offline-*`.

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/seeding.py src/outfitmatch/tracking.py tests/test_tracking.py
git commit -m "feat: deterministic seeding + offline-safe W&B run wrapper"
```

### Task 0.4: CLI entrypoint skeleton (TDD)

**Files:**
- Create: `src/outfitmatch/cli.py`
- Create: `src/outfitmatch/eval/__init__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from outfitmatch.cli import app

runner = CliRunner()


def test_run_command_validates_config(tmp_path: Path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(textwrap.dedent("""
        name: smoke
        seed: 1
        task: retrieval
        model: {kind: hf_clip, checkpoint: openai/clip-vit-base-patch32}
        dataset: {hf_id: Marqo/deepfashion-inshop, max_rows: 4}
        train: {epochs: 1, batch_size: 2}
    """))
    result = runner.invoke(app, ["run", str(cfg), "--dry-run"])
    assert result.exit_code == 0
    assert "smoke" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: outfitmatch.cli`.

- [ ] **Step 3: Implement `src/outfitmatch/eval/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/cli.py`**

```python
from __future__ import annotations

import typer
from rich import print as rprint

from outfitmatch.config import load_config

app = typer.Typer(add_completion=False, help="OutfitMatch experiment runner")


@app.command()
def run(config: str, dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    cfg = load_config(config)
    rprint(f"[bold green]Loaded experiment:[/] {cfg.name} "
           f"(task={cfg.task}, model={cfg.model.checkpoint}, "
           f"rows={cfg.dataset.max_rows})")
    if dry_run:
        rprint("[yellow]--dry-run set, exiting before training.[/]")
        raise typer.Exit(0)
    from outfitmatch.runner import execute  # imported lazily

    execute(cfg)


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/cli.py src/outfitmatch/eval/__init__.py tests/test_cli.py
git commit -m "feat: om-exp CLI with --dry-run config validation"
```

### Task 0.5: Pre-commit + CI gate

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main, dev]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - run: uv sync --group dev
      - run: uv run ruff check src tests
      - run: uv run ruff format --check src tests
      - run: uv run pytest tests -v --cov=src/outfitmatch --cov-report=term-missing
```

- [ ] **Step 3: Verify locally**

Run: `uv run ruff check src tests && uv run pytest tests -v`
Expected: ruff clean, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml
git commit -m "ci: ruff + pytest gate on PR"
```

---

## SPRINT 1 — Data Loaders + Metrics (Storymap a2-s1)

**Sprint goal:** Row-capped HF dataset loaders + pure metric functions, fully TDD'd. This is the machinery the dataset-axis and row-count-axis cycles depend on.

### Task 1.1: BaseFashionDataset ABC + RetrievalDataset (TDD)

**Files:**
- Create: `src/outfitmatch/data/__init__.py`
- Create: `src/outfitmatch/data/base.py`
- Create: `src/outfitmatch/data/retrieval.py`
- Test: `tests/test_data_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_retrieval.py
from outfitmatch.data.retrieval import RetrievalDataset


class _FakeHF:
    def __init__(self, n):
        self._rows = [
            {"image": f"img{i}", "text": f"a red dress {i}",
             "category1": "dress", "item_ID": str(i)}
            for i in range(n)
        ]

    def __len__(self):
        return len(self._rows)

    def select(self, idxs):
        f = _FakeHF(0)
        f._rows = [self._rows[i] for i in idxs]
        return f

    def __getitem__(self, i):
        return self._rows[i]


def test_max_rows_caps_length(monkeypatch):
    monkeypatch.setattr(
        "outfitmatch.data.retrieval._load_hf",
        lambda hf_id, config, split: _FakeHF(100),
    )
    ds = RetrievalDataset("Marqo/deepfashion-inshop", config="default",
                           split="data", max_rows=10)
    assert len(ds) == 10
    sample = ds[0]
    assert sample["text"] == "a red dress 0"
    assert sample["image"] == "img0"


def test_no_cap_keeps_all(monkeypatch):
    monkeypatch.setattr(
        "outfitmatch.data.retrieval._load_hf",
        lambda hf_id, config, split: _FakeHF(42),
    )
    ds = RetrievalDataset("x", config=None, split="data", max_rows=None)
    assert len(ds) == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: outfitmatch.data.retrieval`.

- [ ] **Step 3: Implement `src/outfitmatch/data/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/data/base.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from torch.utils.data import Dataset


class BaseFashionDataset(Dataset, ABC):
    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __getitem__(self, idx: int) -> dict[str, Any]: ...
```

- [ ] **Step 5: Implement `src/outfitmatch/data/retrieval.py`**

```python
from __future__ import annotations

from typing import Any

from datasets import load_dataset

from outfitmatch.data.base import BaseFashionDataset


def _load_hf(hf_id: str, config: str | None, split: str):
    return load_dataset(hf_id, name=config, split=split)


class RetrievalDataset(BaseFashionDataset):
    """Image+text pairs for contrastive retrieval (DeepFashion / Fashion200K)."""

    def __init__(self, hf_id: str, config: str | None, split: str,
                 max_rows: int | None) -> None:
        ds = _load_hf(hf_id, config, split)
        if max_rows is not None and max_rows < len(ds):
            ds = ds.select(range(max_rows))
        self._ds = ds

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "image": row["image"],
            "text": row["text"],
            "category": row.get("category1", ""),
            "item_ID": row["item_ID"],
        }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_data_retrieval.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add src/outfitmatch/data tests/test_data_retrieval.py
git commit -m "feat: RetrievalDataset with max_rows cap (row-count experiment axis)"
```

### Task 1.2: Polyvore FITB + compatibility datasets (TDD)

**Files:**
- Create: `src/outfitmatch/data/polyvore.py`
- Test: `tests/test_data_polyvore.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_polyvore.py
from outfitmatch.data.polyvore import PolyvoreCompatDataset, PolyvoreFITBDataset


class _FakeHF:
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def select(self, idxs):
        return _FakeHF([self._rows[i] for i in idxs])

    def __getitem__(self, i):
        return self._rows[i]


def test_compat_dataset_parses_label(monkeypatch):
    rows = [{"example_id": "1", "items": ["a", "b"], "label": "1"},
            {"example_id": "2", "items": ["c"], "label": "0"}]
    monkeypatch.setattr("outfitmatch.data.polyvore._load_hf",
                        lambda *a, **k: _FakeHF(rows))
    ds = PolyvoreCompatDataset("owj0421/polyvore-outfits",
                               config="disjoint_compatibility",
                               split="test", max_rows=None)
    assert len(ds) == 2
    assert ds[0]["items"] == ["a", "b"]
    assert ds[0]["label"] == 1
    assert ds[1]["label"] == 0


def test_fitb_dataset_exposes_question_and_answer(monkeypatch):
    rows = [{"example_id": "1", "question": ["a", "b"],
             "answers": ["x", "y", "z", "w"], "label": 2}]
    monkeypatch.setattr("outfitmatch.data.polyvore._load_hf",
                        lambda *a, **k: _FakeHF(rows))
    ds = PolyvoreFITBDataset("owj0421/polyvore-outfits",
                             config="disjoint_fill_in_the_blank",
                             split="test", max_rows=1)
    s = ds[0]
    assert s["question"] == ["a", "b"]
    assert s["answers"][s["label"]] == "z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_polyvore.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/data/polyvore.py`**

```python
from __future__ import annotations

from typing import Any

from datasets import load_dataset

from outfitmatch.data.base import BaseFashionDataset


def _load_hf(hf_id: str, config: str, split: str):
    return load_dataset(hf_id, name=config, split=split)


def _cap(ds, max_rows: int | None):
    if max_rows is not None and max_rows < len(ds):
        return ds.select(range(max_rows))
    return ds


class PolyvoreCompatDataset(BaseFashionDataset):
    """Outfit compatibility: items list + binary label (compatibility AUC)."""

    def __init__(self, hf_id: str, config: str, split: str,
                 max_rows: int | None) -> None:
        self._ds = _cap(_load_hf(hf_id, config, split), max_rows)

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "example_id": row["example_id"],
            "items": list(row["items"]),
            "label": int(row["label"]),
        }


class PolyvoreFITBDataset(BaseFashionDataset):
    """Fill-in-the-blank: partial outfit + 4 candidate answers (FITB acc)."""

    def __init__(self, hf_id: str, config: str, split: str,
                 max_rows: int | None) -> None:
        self._ds = _cap(_load_hf(hf_id, config, split), max_rows)

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "question": list(row["question"]),
            "answers": list(row["answers"]),
            "label": int(row["label"]),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_polyvore.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/data/polyvore.py tests/test_data_polyvore.py
git commit -m "feat: Polyvore compat + FITB datasets (disjoint/nondisjoint axis)"
```

### Task 1.3: Retrieval metrics (TDD)

**Files:**
- Create: `src/outfitmatch/metrics/__init__.py`
- Create: `src/outfitmatch/metrics/retrieval.py`
- Test: `tests/test_metrics_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_retrieval.py
import torch

from outfitmatch.metrics.retrieval import mean_average_precision, recall_at_k


def test_recall_at_k_perfect_diagonal():
    sims = torch.eye(5)
    assert recall_at_k(sims, k=1) == 1.0


def test_recall_at_k_partial():
    # row 0 ranks correct item (idx 0) at position 2 -> not in top-1
    sims = torch.tensor([[0.1, 0.9, 0.2], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert recall_at_k(sims, k=1) == round(2 / 3, 6)
    assert recall_at_k(sims, k=2) == 1.0


def test_map_is_between_zero_and_one():
    sims = torch.rand(8, 8)
    m = mean_average_precision(sims)
    assert 0.0 <= m <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/metrics/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/metrics/retrieval.py`**

```python
from __future__ import annotations

import torch


def recall_at_k(sims: torch.Tensor, k: int) -> float:
    """sims[i][j] = similarity(query i, candidate j). Correct match is j == i."""
    n = sims.size(0)
    topk = sims.topk(k, dim=1).indices
    gold = torch.arange(n).unsqueeze(1)
    hits = (topk == gold).any(dim=1).float().sum().item()
    return round(hits / n, 6)


def mean_average_precision(sims: torch.Tensor) -> float:
    n = sims.size(0)
    ranks = sims.argsort(dim=1, descending=True)
    gold = torch.arange(n)
    ap = []
    for i in range(n):
        pos = (ranks[i] == gold[i]).nonzero(as_tuple=True)[0].item()
        ap.append(1.0 / (pos + 1))
    return round(sum(ap) / n, 6)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_retrieval.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/metrics tests/test_metrics_retrieval.py
git commit -m "feat: recall@k + mAP retrieval metrics"
```

### Task 1.4: Outfit metrics — FITB accuracy + compatibility AUC (TDD)

**Files:**
- Create: `src/outfitmatch/metrics/outfit.py`
- Test: `tests/test_metrics_outfit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_outfit.py
from outfitmatch.metrics.outfit import compatibility_auc, fitb_accuracy


def test_fitb_accuracy_all_correct():
    preds = [1, 0, 3]
    labels = [1, 0, 3]
    assert fitb_accuracy(preds, labels) == 1.0


def test_fitb_accuracy_half():
    assert fitb_accuracy([0, 1], [0, 0]) == 0.5


def test_compatibility_auc_separable():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    assert compatibility_auc(scores, labels) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_outfit.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/metrics/outfit.py`**

```python
from __future__ import annotations

from collections.abc import Sequence

from sklearn.metrics import roc_auc_score


def fitb_accuracy(preds: Sequence[int], labels: Sequence[int]) -> float:
    if not preds:
        return 0.0
    correct = sum(int(p == y) for p, y in zip(preds, labels, strict=True))
    return round(correct / len(preds), 6)


def compatibility_auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    return round(float(roc_auc_score(list(labels), list(scores))), 6)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_outfit.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/metrics/outfit.py tests/test_metrics_outfit.py
git commit -m "feat: FITB accuracy + compatibility AUC metrics"
```

---

## SPRINT 2 — Encoders + Retrieval Eval (Storymap a1-s5, a4-s1)

**Sprint goal:** All four encoder variants behind one `BaseEncoder` ABC; `evaluate_retrieval` ties encoder+dataset+metrics together; CLI `run` executes a real zero-shot retrieval run logged to W&B.

### Task 2.1: BaseEncoder ABC + HF CLIP encoder (TDD)

**Files:**
- Create: `src/outfitmatch/encoders/__init__.py`
- Create: `src/outfitmatch/encoders/base.py`
- Create: `src/outfitmatch/encoders/hf_clip_encoder.py`
- Test: `tests/test_encoders.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_encoders.py
import torch
from PIL import Image

from outfitmatch.encoders.hf_clip_encoder import HfClipEncoder


def test_hf_clip_encoder_shapes():
    enc = HfClipEncoder("openai/clip-vit-base-patch32", device="cpu")
    imgs = [Image.new("RGB", (224, 224), "red")]
    txts = ["a red dress"]
    iv = enc.encode_image(imgs)
    tv = enc.encode_text(txts)
    assert iv.shape[0] == 1 and tv.shape[0] == 1
    assert iv.shape[1] == tv.shape[1]
    assert torch.allclose(iv.norm(dim=1), torch.ones(1), atol=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_encoders.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/encoders/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/encoders/base.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod

import torch
from PIL.Image import Image


class BaseEncoder(ABC):
    embed_dim: int

    @abstractmethod
    def encode_image(self, images: list[Image]) -> torch.Tensor: ...

    @abstractmethod
    def encode_text(self, texts: list[str]) -> torch.Tensor: ...
```

- [ ] **Step 5: Implement `src/outfitmatch/encoders/hf_clip_encoder.py`**

```python
from __future__ import annotations

import torch
from PIL.Image import Image
from transformers import CLIPModel, CLIPProcessor

from outfitmatch.encoders.base import BaseEncoder


class HfClipEncoder(BaseEncoder):
    """openai/clip-* and patrickjohncyh/fashion-clip via transformers."""

    def __init__(self, checkpoint: str, device: str = "cpu") -> None:
        self.device = device
        self.model = CLIPModel.from_pretrained(checkpoint).to(device).eval()
        self.proc = CLIPProcessor.from_pretrained(checkpoint)
        self.embed_dim = self.model.config.projection_dim

    @torch.no_grad()
    def encode_image(self, images: list[Image]) -> torch.Tensor:
        inp = self.proc(images=images, return_tensors="pt").to(self.device)
        v = self.model.get_image_features(**inp)
        return v / v.norm(dim=1, keepdim=True)

    @torch.no_grad()
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        inp = self.proc(text=texts, return_tensors="pt", padding=True,
                         truncation=True).to(self.device)
        v = self.model.get_text_features(**inp)
        return v / v.norm(dim=1, keepdim=True)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_encoders.py -v`
Expected: PASS (downloads ~600MB CLIP weights on first run; allow time).

- [ ] **Step 7: Commit**

```bash
git add src/outfitmatch/encoders tests/test_encoders.py
git commit -m "feat: BaseEncoder ABC + HF CLIP encoder (clip-zs / fashion-clip)"
```

### Task 2.2: open_clip encoder for FashionSigLIP / FashionCLIP (TDD)

**Files:**
- Create: `src/outfitmatch/encoders/openclip_encoder.py`
- Modify: `tests/test_encoders.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# tests/test_encoders.py  (append)
def test_openclip_fashionsiglip_shapes():
    from outfitmatch.encoders.openclip_encoder import OpenClipEncoder
    enc = OpenClipEncoder(
        "hf-hub:Marqo/marqo-fashionSigLIP", device="cpu")
    iv = enc.encode_image([Image.new("RGB", (224, 224), "blue")])
    tv = enc.encode_text(["blue jeans"])
    assert iv.shape[1] == tv.shape[1] == enc.embed_dim
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_encoders.py::test_openclip_fashionsiglip_shapes -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/encoders/openclip_encoder.py`**

```python
from __future__ import annotations

import open_clip
import torch
from PIL.Image import Image

from outfitmatch.encoders.base import BaseEncoder


class OpenClipEncoder(BaseEncoder):
    """Marqo FashionSigLIP / FashionCLIP via open_clip hf-hub loading."""

    def __init__(self, checkpoint: str, device: str = "cpu") -> None:
        self.device = device
        model, _, preprocess = open_clip.create_model_and_transforms(checkpoint)
        self.model = model.to(device).eval()
        self.preprocess = preprocess
        self.tokenizer = open_clip.get_tokenizer(checkpoint)
        with torch.no_grad():
            d = self.model.encode_text(self.tokenizer(["x"])).shape[1]
        self.embed_dim = d

    @torch.no_grad()
    def encode_image(self, images: list[Image]) -> torch.Tensor:
        batch = torch.stack([self.preprocess(im) for im in images]).to(self.device)
        v = self.model.encode_image(batch)
        return v / v.norm(dim=1, keepdim=True)

    @torch.no_grad()
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        toks = self.tokenizer(texts).to(self.device)
        v = self.model.encode_text(toks)
        return v / v.norm(dim=1, keepdim=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_encoders.py -v`
Expected: PASS (all encoder tests).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/encoders/openclip_encoder.py tests/test_encoders.py
git commit -m "feat: open_clip encoder for FashionSigLIP/FashionCLIP"
```

### Task 2.3: Encoder factory + retrieval eval (TDD)

**Files:**
- Create: `src/outfitmatch/encoders/factory.py`
- Create: `src/outfitmatch/eval/retrieval_eval.py`
- Test: `tests/test_retrieval_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retrieval_eval.py
import torch
from PIL import Image

from outfitmatch.eval.retrieval_eval import evaluate_retrieval


class _StubEncoder:
    embed_dim = 4

    def encode_image(self, images):
        return torch.eye(len(images), 4)

    def encode_text(self, texts):
        return torch.eye(len(texts), 4)


class _StubDS:
    def __len__(self):
        return 4

    def __getitem__(self, i):
        return {"image": Image.new("RGB", (8, 8)), "text": f"t{i}"}


def test_evaluate_retrieval_returns_metrics():
    out = evaluate_retrieval(_StubEncoder(), _StubDS(), batch_size=2)
    assert out["recall@1"] == 1.0
    assert "recall@5" in out and "recall@10" in out and "map" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retrieval_eval.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/encoders/factory.py`**

```python
from __future__ import annotations

from outfitmatch.config import ModelConfig
from outfitmatch.encoders.base import BaseEncoder


def build_encoder(mc: ModelConfig, device: str = "cpu") -> BaseEncoder:
    if mc.kind == "hf_clip":
        from outfitmatch.encoders.hf_clip_encoder import HfClipEncoder

        return HfClipEncoder(mc.checkpoint, device=device)
    if mc.kind == "open_clip":
        from outfitmatch.encoders.openclip_encoder import OpenClipEncoder

        return OpenClipEncoder(mc.checkpoint, device=device)
    raise ValueError(f"unknown encoder kind: {mc.kind}")
```

- [ ] **Step 4: Implement `src/outfitmatch/eval/retrieval_eval.py`**

```python
from __future__ import annotations

import torch

from outfitmatch.metrics.retrieval import mean_average_precision, recall_at_k


def evaluate_retrieval(encoder, dataset, batch_size: int = 64) -> dict[str, float]:
    img_vecs, txt_vecs = [], []
    for start in range(0, len(dataset), batch_size):
        rows = [dataset[i] for i in range(start, min(start + batch_size,
                                                     len(dataset)))]
        img_vecs.append(encoder.encode_image([r["image"] for r in rows]))
        txt_vecs.append(encoder.encode_text([r["text"] for r in rows]))
    iv = torch.cat(img_vecs)
    tv = torch.cat(txt_vecs)
    sims = tv @ iv.T
    return {
        "recall@1": recall_at_k(sims, 1),
        "recall@5": recall_at_k(sims, 5),
        "recall@10": recall_at_k(sims, 10),
        "map": mean_average_precision(sims),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_retrieval_eval.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/encoders/factory.py src/outfitmatch/eval/retrieval_eval.py tests/test_retrieval_eval.py
git commit -m "feat: encoder factory + evaluate_retrieval"
```

### Task 2.4: Runner wiring — config → eval → W&B (TDD)

**Files:**
- Create: `src/outfitmatch/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner.py
import torch

from outfitmatch.config import ExperimentConfig
from outfitmatch.runner import execute


def test_execute_zero_shot_retrieval(monkeypatch):
    cfg = ExperimentConfig.model_validate({
        "name": "smoke", "seed": 1, "task": "retrieval",
        "model": {"kind": "hf_clip", "checkpoint": "stub"},
        "dataset": {"hf_id": "stub", "max_rows": 4},
        "train": {"epochs": 0, "batch_size": 2},
    })

    class _Enc:
        embed_dim = 4
        def encode_image(self, x): return torch.eye(len(x), 4)
        def encode_text(self, x): return torch.eye(len(x), 4)

    class _DS:
        def __init__(self, *a, **k): pass
        def __len__(self): return 4
        def __getitem__(self, i):
            from PIL import Image
            return {"image": Image.new("RGB", (8, 8)), "text": f"t{i}"}

    monkeypatch.setattr("outfitmatch.runner.build_encoder", lambda *a, **k: _Enc())
    monkeypatch.setattr("outfitmatch.runner.RetrievalDataset", _DS)
    metrics = execute(cfg, group="test", job_type="smoke")
    assert metrics["recall@1"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'execute'`.

- [ ] **Step 3: Implement `src/outfitmatch/runner.py`**

```python
from __future__ import annotations

from outfitmatch.config import ExperimentConfig
from outfitmatch.data.retrieval import RetrievalDataset
from outfitmatch.encoders.factory import build_encoder
from outfitmatch.eval.retrieval_eval import evaluate_retrieval
from outfitmatch.seeding import set_seed
from outfitmatch.tracking import start_run


def execute(cfg: ExperimentConfig, group: str = "default",
            job_type: str = "run") -> dict[str, float]:
    set_seed(cfg.seed)
    run = start_run(cfg, group=group, job_type=job_type)
    try:
        if cfg.task == "retrieval":
            encoder = build_encoder(cfg.model)
            ds = RetrievalDataset(cfg.dataset.hf_id, cfg.dataset.config,
                                  cfg.dataset.split, cfg.dataset.max_rows)
            metrics = evaluate_retrieval(encoder, ds,
                                         batch_size=cfg.train.batch_size)
        else:
            raise NotImplementedError(f"task {cfg.task} added in later sprint")
        run.log(metrics)
        return metrics
    finally:
        run.finish()
```

- [ ] **Step 4: Update CLI to pass group/job_type**

In `src/outfitmatch/cli.py`, change the `execute(cfg)` call to:

```python
    from outfitmatch.runner import execute

    execute(cfg, group=cfg.name.split("-")[0], job_type=cfg.task)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py tests/test_cli.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/runner.py src/outfitmatch/cli.py tests/test_runner.py
git commit -m "feat: runner wires config -> retrieval eval -> W&B"
```

---

## SPRINT 3 — Experiment Cycle: MODEL axis (Ablation 1) (Storymap a4-s2)

**Sprint goal:** Run the encoder-model cycle: 4 zero-shot models on a fixed dataset/row budget, all in one W&B group. This is the first real "different models" cycle the user asked for. Produces `ablation_table_encoder.csv` and answers: does FashionSigLIP beat CLIP zero-shot?

### Task 3.1: Encoder cycle configs

**Files:**
- Create: `configs/encoder/clip_zs.yaml`
- Create: `configs/encoder/fashionclip_zs.yaml`
- Create: `configs/encoder/fashionsiglip_zs.yaml`
- Create: `configs/encoder/marqo_fashionclip_zs.yaml`

- [ ] **Step 1: Create `configs/encoder/clip_zs.yaml`**

```yaml
name: encoder-clip-zs
seed: 42
task: retrieval
model: {kind: hf_clip, checkpoint: openai/clip-vit-base-patch32}
dataset: {hf_id: Marqo/deepfashion-inshop, config: default, split: data, max_rows: 5000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 2: Create `configs/encoder/fashionclip_zs.yaml`**

```yaml
name: encoder-fashionclip-zs
seed: 42
task: retrieval
model: {kind: hf_clip, checkpoint: patrickjohncyh/fashion-clip}
dataset: {hf_id: Marqo/deepfashion-inshop, config: default, split: data, max_rows: 5000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 3: Create `configs/encoder/fashionsiglip_zs.yaml`**

```yaml
name: encoder-fashionsiglip-zs
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: Marqo/deepfashion-inshop, config: default, split: data, max_rows: 5000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 4: Create `configs/encoder/marqo_fashionclip_zs.yaml`**

```yaml
name: encoder-marqofashionclip-zs
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionCLIP"}
dataset: {hf_id: Marqo/deepfashion-inshop, config: default, split: data, max_rows: 5000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 5: Commit**

```bash
git add configs/encoder
git commit -m "feat: encoder model-axis cycle configs (Ablation 1)"
```

### Task 3.2: Sweep command + CSV export (TDD)

**Files:**
- Modify: `src/outfitmatch/cli.py` (add `sweep` command)
- Create: `src/outfitmatch/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export.py
from pathlib import Path

from outfitmatch.export import append_result_row, read_results


def test_append_and_read(tmp_path: Path):
    csv = tmp_path / "ablation.csv"
    append_result_row(csv, {"name": "a", "recall@5": 0.5})
    append_result_row(csv, {"name": "b", "recall@5": 0.7})
    rows = read_results(csv)
    assert len(rows) == 2
    assert rows[1]["name"] == "b"
    assert float(rows[1]["recall@5"]) == 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/export.py`**

```python
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def append_result_row(path: str | Path, row: dict[str, Any]) -> None:
    path = Path(path)
    exists = path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def read_results(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Add `sweep` command to `src/outfitmatch/cli.py`**

Append this command to the Typer app:

```python
@app.command()
def sweep(config_dir: str, out_csv: str = "docs/experiments/ablation.csv") -> None:
    """Run every YAML in a directory as one experiment cycle."""
    from pathlib import Path

    from outfitmatch.export import append_result_row
    from outfitmatch.runner import execute

    for yaml_path in sorted(Path(config_dir).glob("*.yaml")):
        cfg = load_config(yaml_path)
        rprint(f"[cyan]>>> {cfg.name}[/]")
        metrics = execute(cfg, group=Path(config_dir).name, job_type=cfg.task)
        append_result_row(out_csv, {"name": cfg.name,
                                    "model": cfg.model.checkpoint,
                                    "rows": cfg.dataset.max_rows, **metrics})
```

- [ ] **Step 6: Run the cycle (real, on GPU/Thunder Compute)**

Run: `uv run om-exp sweep configs/encoder --out-csv docs/experiments/ablation_encoder.csv`
Expected: 4 W&B runs in group `encoder`; CSV with 4 rows; FashionSigLIP recall@5 highest.

- [ ] **Step 7: Commit**

```bash
git add src/outfitmatch/cli.py src/outfitmatch/export.py tests/test_export.py docs/experiments/ablation_encoder.csv
git commit -m "feat: sweep command + CSV export; run encoder model-axis cycle"
```

---

## SPRINT 4 — Experiment Cycle: DATASET-TYPE axis (Storymap a4-s1)

**Sprint goal:** Hold model = FashionSigLIP-ZS fixed; vary dataset across DeepFashion-InShop, Fashion200K. Answers: which catalog dataset gives the strongest retrieval signal / is hardest?

### Task 4.1: Dataset-axis configs + run

**Files:**
- Create: `configs/dataset/deepfashion_inshop.yaml`
- Create: `configs/dataset/fashion200k.yaml`
- Create: `configs/dataset/deepfashion_multimodal.yaml`

- [ ] **Step 1: Create `configs/dataset/deepfashion_inshop.yaml`**

```yaml
name: dataset-deepfashion-inshop
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: Marqo/deepfashion-inshop, config: default, split: data, max_rows: 10000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 2: Create `configs/dataset/fashion200k.yaml`**

```yaml
name: dataset-fashion200k
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: Marqo/fashion200k, config: default, split: data, max_rows: 10000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 3: Create `configs/dataset/deepfashion_multimodal.yaml`**

```yaml
name: dataset-deepfashion-multimodal
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: Marqo/deepfashion-multimodal, config: default, split: data, max_rows: 10000}
train: {epochs: 0, batch_size: 64}
```

- [ ] **Step 4: Run the cycle**

Run: `uv run om-exp sweep configs/dataset --out-csv docs/experiments/ablation_dataset.csv`
Expected: 3 W&B runs in group `dataset`; CSV comparing recall@K across datasets.

- [ ] **Step 5: Commit**

```bash
git add configs/dataset docs/experiments/ablation_dataset.csv
git commit -m "feat: dataset-type axis cycle (DeepFashion vs Fashion200K)"
```

---

## SPRINT 5 — SigLIP Fine-Tune Trainer + ROW-COUNT axis (Storymap a4-s1)

**Sprint goal:** Implement the SigLIP contrastive trainer so `epochs > 0` fine-tunes the encoder; then run the data-scaling cycle (5K / 25K / 100K rows) to produce the data-scaling curve and the fine-tuned model that beats CLIP-ZS by ≥5% Recall@5.

### Task 5.1: SigLIP contrastive trainer (TDD)

**Files:**
- Create: `src/outfitmatch/train/__init__.py`
- Create: `src/outfitmatch/train/contrastive.py`
- Test: `tests/test_contrastive.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contrastive.py
import torch

from outfitmatch.train.contrastive import siglip_loss


def test_siglip_loss_lower_when_aligned():
    img = torch.eye(4)
    good = siglip_loss(img, img.clone(), t=1.0, b=0.0)
    bad = siglip_loss(img, img.flip(0), t=1.0, b=0.0)
    assert good < bad
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrastive.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/train/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/train/contrastive.py`**

```python
from __future__ import annotations

import torch
import torch.nn.functional as F


def siglip_loss(img: torch.Tensor, txt: torch.Tensor, t: float = 10.0,
                b: float = -10.0) -> torch.Tensor:
    """Sigmoid contrastive loss (SigLIP, Zhai et al. 2023)."""
    img = F.normalize(img, dim=1)
    txt = F.normalize(txt, dim=1)
    logits = (img @ txt.T) * t + b
    n = img.size(0)
    labels = 2 * torch.eye(n, device=img.device) - 1  # +1 diag, -1 off
    return -F.logsigmoid(labels * logits).mean()


def finetune_encoder(encoder, dataset, *, epochs: int, batch_size: int,
                     lr: float, device: str = "cpu",
                     log_fn=lambda d: None) -> None:
    params = [p for p in encoder.model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr)
    encoder.model.train()
    for ep in range(epochs):
        for start in range(0, len(dataset), batch_size):
            rows = [dataset[i] for i in
                    range(start, min(start + batch_size, len(dataset)))]
            iv = encoder.encode_image([r["image"] for r in rows])
            tv = encoder.encode_text([r["text"] for r in rows])
            loss = siglip_loss(iv, tv)
            opt.zero_grad()
            loss.backward()
            opt.step()
            log_fn({"train/loss": loss.item(), "epoch": ep})
    encoder.model.eval()
```

> Note: for true gradient flow, `encode_image/encode_text` must run without `torch.no_grad()` during training. In Task 5.2 add `train_mode: bool` to the encoder ABC and wrap the `@torch.no_grad()` decorators in a runtime check (`if not self._train_mode`). Keep eval path unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_contrastive.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/train tests/test_contrastive.py
git commit -m "feat: SigLIP sigmoid contrastive loss + finetune loop"
```

### Task 5.2: Wire fine-tune into runner (TDD)

**Files:**
- Modify: `src/outfitmatch/encoders/base.py` (add train-mode flag)
- Modify: `src/outfitmatch/encoders/hf_clip_encoder.py` and `openclip_encoder.py` (respect flag)
- Modify: `src/outfitmatch/runner.py` (call `finetune_encoder` when `epochs > 0`)
- Test: `tests/test_runner.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# tests/test_runner.py  (append)
def test_execute_finetune_path_called(monkeypatch):
    from outfitmatch.config import ExperimentConfig
    from outfitmatch.runner import execute
    import torch

    cfg = ExperimentConfig.model_validate({
        "name": "ft", "seed": 1, "task": "retrieval",
        "model": {"kind": "hf_clip", "checkpoint": "stub", "finetune": True},
        "dataset": {"hf_id": "stub", "max_rows": 4},
        "train": {"epochs": 1, "batch_size": 2, "lr": 1e-4},
    })
    called = {}

    class _Enc:
        embed_dim = 4
        class model:  # noqa
            @staticmethod
            def parameters(): return iter([torch.zeros(1, requires_grad=True)])
        def encode_image(self, x): return torch.eye(len(x), 4)
        def encode_text(self, x): return torch.eye(len(x), 4)

    class _DS:
        def __init__(self, *a, **k): pass
        def __len__(self): return 4
        def __getitem__(self, i):
            from PIL import Image
            return {"image": Image.new("RGB", (8, 8)), "text": f"t{i}"}

    monkeypatch.setattr("outfitmatch.runner.build_encoder", lambda *a, **k: _Enc())
    monkeypatch.setattr("outfitmatch.runner.RetrievalDataset", _DS)
    monkeypatch.setattr("outfitmatch.runner.finetune_encoder",
                        lambda *a, **k: called.setdefault("ft", True))
    execute(cfg, group="t", job_type="ft")
    assert called.get("ft") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py::test_execute_finetune_path_called -v`
Expected: FAIL — `finetune_encoder` not imported in runner.

- [ ] **Step 3: Modify `src/outfitmatch/runner.py`**

Add import at top:

```python
from outfitmatch.train.contrastive import finetune_encoder
```

Replace the `if cfg.task == "retrieval":` block body with:

```python
        if cfg.task == "retrieval":
            encoder = build_encoder(cfg.model)
            ds = RetrievalDataset(cfg.dataset.hf_id, cfg.dataset.config,
                                  cfg.dataset.split, cfg.dataset.max_rows)
            if cfg.model.finetune and cfg.train.epochs > 0:
                finetune_encoder(encoder, ds, epochs=cfg.train.epochs,
                                 batch_size=cfg.train.batch_size,
                                 lr=cfg.train.lr, log_fn=run.log)
            metrics = evaluate_retrieval(encoder, ds,
                                         batch_size=cfg.train.batch_size)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS (all runner tests).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/runner.py tests/test_runner.py
git commit -m "feat: runner fine-tunes encoder when finetune+epochs>0"
```

### Task 5.3: Row-count cycle configs + run

**Files:**
- Create: `configs/rows/ft_5k.yaml`, `configs/rows/ft_25k.yaml`, `configs/rows/ft_100k.yaml`

- [ ] **Step 1: Create the three configs**

`configs/rows/ft_5k.yaml`:

```yaml
name: rows-ft-5k
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP", finetune: true}
dataset: {hf_id: Marqo/fashion200k, config: default, split: data, max_rows: 5000}
train: {epochs: 3, batch_size: 64, lr: 1.0e-5}
```

`configs/rows/ft_25k.yaml` (identical except):

```yaml
name: rows-ft-25k
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP", finetune: true}
dataset: {hf_id: Marqo/fashion200k, config: default, split: data, max_rows: 25000}
train: {epochs: 3, batch_size: 64, lr: 1.0e-5}
```

`configs/rows/ft_100k.yaml` (identical except):

```yaml
name: rows-ft-100k
seed: 42
task: retrieval
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP", finetune: true}
dataset: {hf_id: Marqo/fashion200k, config: default, split: data, max_rows: 100000}
train: {epochs: 3, batch_size: 64, lr: 1.0e-5}
```

- [ ] **Step 2: Run the data-scaling cycle (Thunder Compute)**

Run: `uv run om-exp sweep configs/rows --out-csv docs/experiments/scaling_rows.csv`
Expected: 3 W&B runs in group `rows`; recall@5 increases with rows; best run beats `encoder-clip-zs` recall@5 by ≥5pp (the grading target).

- [ ] **Step 3: Commit**

```bash
git add configs/rows docs/experiments/scaling_rows.csv
git commit -m "feat: row-count data-scaling cycle on Fashion200K"
```

---

## SPRINT 6 — Body Pipeline Experiment Cycle (Storymap a3-s1)

**Sprint goal:** Pose extractor behind a wrapper; rule-based 5-class body shape from keypoint ratios (TDD); model-axis cycle YOLOv8n-pose vs YOLO11n-pose comparing detection rate + shape-label stability.

### Task 6.1: Body shape rules (TDD)

**Files:**
- Create: `src/outfitmatch/body/__init__.py`
- Create: `src/outfitmatch/body/shape_rules.py`
- Test: `tests/test_body_shape_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_body_shape_rules.py
from outfitmatch.body.shape_rules import classify_body_shape


def test_hourglass_balanced_shoulders_hips_narrow_waist():
    # shoulder ~= hip, waist much smaller
    assert classify_body_shape(shoulder=40.0, waist=28.0, hip=40.0) == "hourglass"


def test_pear_hips_wider_than_shoulders():
    assert classify_body_shape(shoulder=34.0, waist=30.0, hip=42.0) == "pear"


def test_inverted_triangle_shoulders_wider():
    assert classify_body_shape(shoulder=44.0, waist=32.0, hip=34.0) == "inverted_triangle"


def test_rectangle_all_similar():
    assert classify_body_shape(shoulder=38.0, waist=36.0, hip=38.0) == "rectangle"


def test_apple_waist_largest():
    assert classify_body_shape(shoulder=38.0, waist=42.0, hip=37.0) == "apple"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_body_shape_rules.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/body/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/outfitmatch/body/shape_rules.py`**

```python
from __future__ import annotations

from typing import Literal

BodyShape = Literal["hourglass", "pear", "apple", "rectangle",
                    "inverted_triangle"]


def classify_body_shape(shoulder: float, waist: float, hip: float) -> BodyShape:
    """5-class rule-based body shape from circumference proxies (cm)."""
    sh_hip = shoulder / hip
    waist_ratio = waist / max(shoulder, hip)

    if waist >= shoulder and waist >= hip:
        return "apple"
    if sh_hip > 1.05:
        return "inverted_triangle"
    if sh_hip < 0.95:
        return "pear"
    # shoulders ~= hips
    if waist_ratio <= 0.80:
        return "hourglass"
    return "rectangle"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_body_shape_rules.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/body tests/test_body_shape_rules.py
git commit -m "feat: rule-based 5-class body shape classifier"
```

### Task 6.2: Pose extractor wrapper + pose-model cycle (TDD)

**Files:**
- Create: `src/outfitmatch/body/pose.py`
- Test: `tests/test_pose.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pose.py
import numpy as np

from outfitmatch.body.pose import PoseExtractor, keypoints_to_measures


def test_keypoints_to_measures_computes_widths():
    # COCO-17: 5=L-shoulder,6=R-shoulder,11=L-hip,12=R-hip
    kp = np.zeros((17, 2))
    kp[5] = [10, 0]; kp[6] = [50, 0]      # shoulder width 40
    kp[11] = [15, 100]; kp[12] = [45, 100]  # hip width 30
    m = keypoints_to_measures(kp)
    assert m["shoulder"] == 40.0
    assert m["hip"] == 30.0
    assert m["waist"] > 0


def test_pose_extractor_model_name_recorded():
    pe = PoseExtractor(weights="yolov8n-pose.pt")
    assert pe.model_name == "yolov8n-pose.pt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pose.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/body/pose.py`**

```python
from __future__ import annotations

from typing import Any

import numpy as np


def keypoints_to_measures(kp: np.ndarray) -> dict[str, float]:
    """COCO-17 keypoints -> shoulder/waist/hip width proxies (pixels)."""
    shoulder = float(np.linalg.norm(kp[5] - kp[6]))
    hip = float(np.linalg.norm(kp[11] - kp[12]))
    waist = (shoulder + hip) / 2.0 * 0.85  # proxy: no waist keypoint in COCO
    return {"shoulder": shoulder, "waist": waist, "hip": hip}


class PoseExtractor:
    def __init__(self, weights: str = "yolov8n-pose.pt") -> None:
        self.model_name = weights
        self._model: Any | None = None

    def _lazy(self) -> Any:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_name)
        return self._model

    def extract(self, image_path: str) -> np.ndarray | None:
        res = self._lazy()(image_path, verbose=False)
        kp = res[0].keypoints
        if kp is None or kp.xy.shape[1] == 0:
            return None
        return kp.xy[0].cpu().numpy()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pose.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Manual pose-model cycle**

Create `docs/experiments/pose_cycle.md` and record, for `yolov8n-pose.pt` vs `yolo11n-pose.pt` over 200 DeepFashion-InShop images: detection rate (% images with keypoints), and body-shape label agreement between the two models. Use a throwaway script `scripts/pose_compare.py` (not committed to src).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/body/pose.py tests/test_pose.py docs/experiments/pose_cycle.md
git commit -m "feat: YOLO-pose wrapper + pose-model comparison cycle"
```

---

## SPRINT 7 — Outfit Composer + Conditioning Cycles (Storymap a5-s1, a5-s2, a5-s4)

**Sprint goal:** Implement OutfitTransformer; train FITB on Polyvore; run the dataset-type cycle (disjoint vs nondisjoint) and the conditioning cycle (body/occasion on/off — Ablations 2 & 3).

### Task 7.1: OutfitTransformer model (TDD)

**Files:**
- Create: `src/outfitmatch/train/composer.py`
- Test: `tests/test_composer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_composer.py
import torch

from outfitmatch.train.composer import OutfitTransformer


def test_forward_returns_compatibility_score():
    m = OutfitTransformer(embed_dim=16, n_heads=2, n_layers=2)
    item_embeds = torch.randn(2, 5, 16)        # batch=2, 5 items
    mask = torch.ones(2, 5, dtype=torch.bool)
    score = m(item_embeds, mask)
    assert score.shape == (2,)
    assert torch.isfinite(score).all()


def test_body_occ_tokens_change_output():
    torch.manual_seed(0)
    m = OutfitTransformer(embed_dim=16, n_heads=2, n_layers=2)
    items = torch.randn(1, 3, 16)
    mask = torch.ones(1, 3, dtype=torch.bool)
    base = m(items, mask)
    cond = m(items, mask, body=torch.randn(1, 16), occ=torch.randn(1, 16))
    assert not torch.allclose(base, cond)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_composer.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/train/composer.py`**

```python
from __future__ import annotations

import torch
import torch.nn as nn


class OutfitTransformer(nn.Module):
    """OutfitTransformer (Sarkar et al. 2022, arXiv:2204.04812) — task token
    + item tokens + optional [BODY]/[OCC] conditioning tokens."""

    def __init__(self, embed_dim: int, n_heads: int = 8,
                 n_layers: int = 4) -> None:
        super().__init__()
        self.cls = nn.Parameter(torch.randn(1, 1, embed_dim))
        self.body_proj = nn.Linear(embed_dim, embed_dim)
        self.occ_proj = nn.Linear(embed_dim, embed_dim)
        layer = nn.TransformerEncoderLayer(
            d_model=embed_dim, nhead=n_heads, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Linear(embed_dim, 1)

    def forward(self, item_embeds: torch.Tensor, mask: torch.Tensor,
                body: torch.Tensor | None = None,
                occ: torch.Tensor | None = None) -> torch.Tensor:
        b = item_embeds.size(0)
        toks = [self.cls.expand(b, -1, -1), item_embeds]
        keep = [torch.ones(b, 1, dtype=torch.bool, device=mask.device), mask]
        if body is not None:
            toks.append(self.body_proj(body).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=mask.device))
        if occ is not None:
            toks.append(self.occ_proj(occ).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=mask.device))
        x = torch.cat(toks, dim=1)
        pad = ~torch.cat(keep, dim=1)
        h = self.encoder(x, src_key_padding_mask=pad)
        return self.head(h[:, 0]).squeeze(-1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_composer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/train/composer.py tests/test_composer.py
git commit -m "feat: OutfitTransformer with body/occasion conditioning tokens"
```

### Task 7.2: Composer dataset-type + conditioning cycle configs

**Files:**
- Create: `configs/composer/disjoint.yaml`, `configs/composer/nondisjoint.yaml`
- Create: `configs/composer/cond_none.yaml`, `configs/composer/cond_body.yaml`, `configs/composer/cond_body_occ.yaml`

> These configs add a `composer` section. Extend `ExperimentConfig` with an optional `composer: ComposerConfig | None` field (n_heads, n_layers, use_body, use_occ) following the exact pattern of `TrainConfig` in Task 0.2; add a TDD test in `tests/test_config.py` mirroring `test_load_minimal_config` that asserts `cfg.composer.use_body is True`. Wire a `task == "fitb"` branch in `runner.py` that builds `OutfitTransformer`, trains on `PolyvoreFITBDataset`, evaluates with `fitb_accuracy`, and `task == "compatibility"` using `PolyvoreCompatDataset` + `compatibility_auc` — each as its own TDD task identical in structure to Task 2.4 (failing test → run → implement → pass → commit).

- [ ] **Step 1: Create `configs/composer/disjoint.yaml`**

```yaml
name: composer-disjoint
seed: 42
task: fitb
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: owj0421/polyvore-outfits, config: disjoint_fill_in_the_blank, split: train, max_rows: 17000}
composer: {n_heads: 8, n_layers: 4, use_body: false, use_occ: false}
train: {epochs: 10, batch_size: 64, lr: 1.0e-4}
```

- [ ] **Step 2: Create `configs/composer/nondisjoint.yaml`** (same but)

```yaml
name: composer-nondisjoint
seed: 42
task: fitb
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: owj0421/polyvore-outfits, config: nondisjoint_fill_in_the_blank, split: train, max_rows: 53000}
composer: {n_heads: 8, n_layers: 4, use_body: false, use_occ: false}
train: {epochs: 10, batch_size: 64, lr: 1.0e-4}
```

- [ ] **Step 3: Create conditioning cycle configs**

`configs/composer/cond_none.yaml`: `composer: {use_body: false, use_occ: false}`
`configs/composer/cond_body.yaml`: `composer: {use_body: true, use_occ: false}`
`configs/composer/cond_body_occ.yaml`: `composer: {use_body: true, use_occ: true}`
(All three: same `name` prefix `composer-cond-*`, task `fitb`, dataset `nondisjoint_fill_in_the_blank`, max_rows 53000, train epochs 10.)

- [ ] **Step 4: Run both cycles (Thunder Compute)**

Run: `uv run om-exp sweep configs/composer --out-csv docs/experiments/ablation_composer.csv`
Expected: 5 W&B runs in group `composer`. Targets: FITB ≥55%, AUC ≥0.85; body conditioning improves body-conditional Precision@5 by ≥10% (Ablation 2/3).

- [ ] **Step 5: Commit**

```bash
git add configs/composer docs/experiments/ablation_composer.csv
git commit -m "feat: composer dataset-type + conditioning experiment cycles"
```

---

## SPRINT 8 — Integration, Demo, Reproducibility (Storymap a7, a8, a9-s5)

**Sprint goal:** End-to-end orchestrator + Gradio demo + `make demo` reproducibility, selecting winning configs from Sprints 3–7.

### Task 8.1: End-to-end orchestrator (TDD)

**Files:**
- Create: `src/outfitmatch/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from outfitmatch.pipeline import recommend_outfit


def test_recommend_returns_outfit_slots(monkeypatch):
    monkeypatch.setattr("outfitmatch.pipeline._classify_shape",
                        lambda img: "pear")
    monkeypatch.setattr("outfitmatch.pipeline._retrieve",
                        lambda shape, occ: {"top": "t1", "bottom": "b1",
                                            "shoes": "s1", "accessory": "a1"})
    out = recommend_outfit(image_path="x.jpg", height=170, weight=60,
                           occasion="office")
    assert set(out["outfit"]) == {"top", "bottom", "shoes", "accessory"}
    assert out["body_shape"] == "pear"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/pipeline.py`**

```python
from __future__ import annotations

from outfitmatch.body.pose import PoseExtractor, keypoints_to_measures
from outfitmatch.body.shape_rules import classify_body_shape


def _classify_shape(image_path: str) -> str:
    pe = PoseExtractor()
    kp = pe.extract(image_path)
    if kp is None:
        return "rectangle"
    m = keypoints_to_measures(kp)
    return classify_body_shape(**m)


def _retrieve(shape: str, occasion: str) -> dict[str, str]:
    raise NotImplementedError("bound to winning Qdrant index in Task 8.2")


def recommend_outfit(image_path: str, height: float, weight: float,
                     occasion: str) -> dict:
    shape = _classify_shape(image_path)
    outfit = _retrieve(shape, occasion)
    return {"body_shape": shape, "occasion": occasion, "outfit": outfit}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/pipeline.py tests/test_pipeline.py
git commit -m "feat: end-to-end recommend_outfit orchestrator"
```

### Task 8.2: Qdrant index + Gradio demo + Makefile

**Files:**
- Create: `src/outfitmatch/index.py` (encode winning model → Qdrant upsert; `_retrieve` impl)
- Create: `src/outfitmatch/ui/gradio_app.py`
- Create: `Makefile`, `docker-compose.yml`

> `index.py`: load the winning encoder (best config from `docs/experiments/scaling_rows.csv`), batch-encode DeepFashion-InShop, upsert to Qdrant collection `catalog`; implement `retrieve(shape, occasion)` doing a filtered ANN query. Replace `pipeline._retrieve` to call it. Add a TDD test `tests/test_index.py` with an in-memory `QdrantClient(":memory:")` asserting upsert+query roundtrip returns the seeded item.

- [ ] **Step 1: Create `Makefile`**

```makefile
.PHONY: install test lint demo qdrant-up
install:
	uv sync --group dev
test:
	uv run pytest tests -v --cov=src/outfitmatch --cov-report=term-missing
lint:
	uv run ruff check src tests && uv run ruff format --check src tests
qdrant-up:
	docker compose up qdrant -d
demo: qdrant-up
	uv run python src/outfitmatch/ui/gradio_app.py
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrant_storage:/qdrant/storage"]
volumes:
  qdrant_storage:
```

- [ ] **Step 3: Implement `index.py` + `gradio_app.py`** following the note above; Gradio inputs = image upload + height slider + weight slider + occasion dropdown (`casual/office/formal/sport/evening`), output = outfit grid. Wire `recommend_outfit`.

- [ ] **Step 4: Reproducibility check**

Run (fresh clone): `uv sync --group dev && make demo`
Expected: Qdrant starts, Gradio serves on `http://localhost:7860`, a sample selfie returns 4 outfit slots.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/index.py src/outfitmatch/ui/gradio_app.py Makefile docker-compose.yml tests/test_index.py
git commit -m "feat: Qdrant catalog index + Gradio demo + make demo"
```

### Task 8.3: Final ablation aggregation

**Files:**
- Create: `scripts/aggregate_ablations.py`
- Create: `docs/experiments/RESULTS.md`

- [ ] **Step 1: Implement `scripts/aggregate_ablations.py`**

Reads `docs/experiments/ablation_encoder.csv`, `ablation_dataset.csv`, `scaling_rows.csv`, `ablation_composer.csv`; emits one markdown table per axis into `docs/experiments/RESULTS.md` with the winning row bolded.

- [ ] **Step 2: Run it**

Run: `uv run python scripts/aggregate_ablations.py`
Expected: `docs/experiments/RESULTS.md` written with 4 comparison tables.

- [ ] **Step 3: Commit**

```bash
git add scripts/aggregate_ablations.py docs/experiments/RESULTS.md
git commit -m "docs: aggregate all experiment-cycle results into RESULTS.md"
```

---

## SPRINT 9 — Personalized Preference Modeling (Storymap a5-s5, a6)

**Sprint goal:** Make the composer score *personal taste*, not just generic compatibility. A user's free-text global style prompt is parsed by a Gemini **structuring layer** into a `StructuredPreference` (hard constraints + soft groups). Hard constraints become Qdrant payload filters (fallback: derived from body shape when the user specifies none). Soft groups become **N grouped `[PREF]` tokens** appended to `OutfitTransformer`. The composer is post-trained with a **conditional Bradley-Terry pairwise loss** on Gemini-generated `(instruction, preferred, rejected)` triplets that include contrastive instruction flips.

**Design decisions (locked):**
- **Hard vs soft:** *hard* = constraints the user explicitly states in the instruction prompt → Qdrant filter. If the user gives **no** hard constraints → fall back to a body-shape-derived constraint. *soft* = style/color/fit preferences from the prompt → `[PREF]` tokens.
- **Token grouping:** **N tokens by group** — one `[PREF]` token per active soft group (`style`, `color`, `fit`).
- **Train/inference-skew invariant:** training triplets MUST be produced through the *same* version-pinned structuring pipeline used at inference. `EXTRACTOR_VERSION` is part of the structuring cache key; bumping it invalidates cache and requires regenerating triplet data.

### Task 9.1: StructuredPreference schema + body-shape fallback (TDD)

**Files:**
- Create: `src/outfitmatch/preference/__init__.py` (empty)
- Create: `src/outfitmatch/preference/schema.py`
- Test: `tests/test_preference_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preference_schema.py
from outfitmatch.preference.schema import (
    HardConstraint, SoftPreference, StructuredPreference, apply_body_fallback,
)


def test_active_soft_groups_filters_empty():
    p = StructuredPreference(
        soft=SoftPreference(style="minimalist korean", color="earth tones", fit=""))
    assert p.active_soft_groups() == {
        "style": "minimalist korean", "color": "earth tones"}


def test_body_fallback_applied_when_no_user_hard():
    p = StructuredPreference()
    p = apply_body_fallback(p, "pear")
    assert p.hard.source == "body_fallback"
    assert p.hard.fit_bias == "structured_top"


def test_body_fallback_skipped_when_user_hard_present():
    p = StructuredPreference(hard=HardConstraint(colors_avoid=["bright"]))
    p = apply_body_fallback(p, "pear")
    assert p.hard.source == "user"
    assert p.hard.fit_bias is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preference_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: outfitmatch.preference`.

- [ ] **Step 3: Implement `src/outfitmatch/preference/schema.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SOFT_GROUPS = ("style", "color", "fit")

# body shape -> fallback hard constraint when the user specifies none
BODY_FALLBACK: dict[str, str] = {
    "pear": "structured_top",
    "apple": "defined_waist",
    "hourglass": "fitted",
    "rectangle": "add_curves",
    "inverted_triangle": "volume_bottom",
}


class HardConstraint(BaseModel):
    colors_avoid: list[str] = Field(default_factory=list)
    categories_exclude: list[str] = Field(default_factory=list)
    materials_require: list[str] = Field(default_factory=list)
    fit_bias: str | None = None
    source: Literal["user", "body_fallback"] = "user"

    def is_empty(self) -> bool:
        return not (self.colors_avoid or self.categories_exclude
                    or self.materials_require)


class SoftPreference(BaseModel):
    style: str = ""
    color: str = ""
    fit: str = ""


class StructuredPreference(BaseModel):
    hard: HardConstraint = Field(default_factory=HardConstraint)
    soft: SoftPreference = Field(default_factory=SoftPreference)

    def active_soft_groups(self) -> dict[str, str]:
        return {g: getattr(self.soft, g).strip()
                for g in SOFT_GROUPS if getattr(self.soft, g).strip()}


def apply_body_fallback(pref: StructuredPreference,
                        body_shape: str) -> StructuredPreference:
    """If the user gave no hard constraints, derive one from body shape."""
    if pref.hard.is_empty():
        pref.hard = HardConstraint(
            fit_bias=BODY_FALLBACK.get(body_shape),
            source="body_fallback",
        )
    return pref
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_preference_schema.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/preference/__init__.py src/outfitmatch/preference/schema.py tests/test_preference_schema.py
git commit -m "feat: StructuredPreference schema + body-shape hard-constraint fallback"
```

### Task 9.2: Gemini prompt-structuring layer (TDD)

**Files:**
- Create: `src/outfitmatch/preference/structuring.py`
- Test: `tests/test_preference_structuring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preference_structuring.py
from outfitmatch.preference.structuring import PromptStructurer


def test_structurer_parses_user_hard_and_caches(tmp_path):
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return ('{"hard":{"colors_avoid":["bright"],"categories_exclude":[],'
                '"materials_require":[]},'
                '"soft":{"style":"minimalist","color":"","fit":"oversized"}}')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p1 = s.structure("minimalist, no bright colors, oversized", "pear")
    p2 = s.structure("minimalist, no bright colors, oversized", "pear")

    assert p1.hard.colors_avoid == ["bright"]
    assert p1.hard.source == "user"          # user gave hard -> no fallback
    assert p1.soft.fit == "oversized"
    assert p2.soft.style == "minimalist"
    assert len(calls) == 1                    # second call served from cache


def test_structurer_body_fallback_when_no_hard(tmp_path):
    def fake(prompt: str) -> str:
        return ('{"hard":{"colors_avoid":[],"categories_exclude":[],'
                '"materials_require":[]},'
                '"soft":{"style":"casual","color":"","fit":""}}')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p = s.structure("just casual everyday", "apple")
    assert p.hard.source == "body_fallback"
    assert p.hard.fit_bias == "defined_waist"


def test_structurer_strips_json_fence(tmp_path):
    def fake(prompt: str) -> str:
        return ('```json\n{"hard":{"colors_avoid":[],"categories_exclude":[],'
                '"materials_require":[]},"soft":{"style":"sporty",'
                '"color":"","fit":""}}\n```')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p = s.structure("sporty", "rectangle")
    assert p.soft.style == "sporty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preference_structuring.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/preference/structuring.py`**

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

import diskcache

from outfitmatch.preference.schema import StructuredPreference, apply_body_fallback

EXTRACTOR_VERSION = "v1"

STRUCT_PROMPT = """You convert a user's fashion style instruction into JSON.
Schema: {{"hard": {{"colors_avoid": [], "categories_exclude": [],
"materials_require": []}}, "soft": {{"style": "", "color": "", "fit": ""}}}}
- hard = constraints the user explicitly demands (avoid / exclude / require).
  Use empty lists when the user states none.
- soft = short phrases (<= 6 words) for preferred style / color / fit.
  Use "" when unspecified.
User instruction: {instruction}
Reply with ONLY the JSON, no prose."""


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    return s.strip()


class PromptStructurer:
    """Free-text global prompt -> StructuredPreference (Gemini-backed, cached).

    `complete_fn` takes a prompt string and returns the model's text reply;
    inject a Gemini client at the call site and a fake in tests.
    """

    def __init__(
        self,
        complete_fn: Callable[[str], str],
        cache_dir: str = "data/raw/occasion_cache/pref_cache",
    ) -> None:
        self._complete = complete_fn
        self._cache = diskcache.Cache(cache_dir)

    def structure(self, instruction: str, body_shape: str) -> StructuredPreference:
        key = hashlib.sha256(
            f"{EXTRACTOR_VERSION}|{instruction}".encode()).hexdigest()
        if key in self._cache:
            raw = self._cache[key]
        else:
            raw = self._complete(STRUCT_PROMPT.format(instruction=instruction))
            self._cache[key] = raw
        data = json.loads(_strip_fence(raw))
        pref = StructuredPreference.model_validate(data)
        return apply_body_fallback(pref, body_shape)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_preference_structuring.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/preference/structuring.py tests/test_preference_structuring.py
git commit -m "feat: Gemini prompt-structuring layer with version-pinned cache"
```

### Task 9.3: Grouped `[PREF]` tokens in OutfitTransformer (TDD)

**Files:**
- Modify: `src/outfitmatch/train/composer.py` (extends the Task 7.1 model)
- Test: `tests/test_composer.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# tests/test_composer.py  (append)
def test_pref_tokens_change_output_and_are_optional():
    torch.manual_seed(0)
    m = OutfitTransformer(embed_dim=16, n_heads=2, n_layers=2,
                          pref_groups=("style", "color"))
    items = torch.randn(1, 3, 16)
    mask = torch.ones(1, 3, dtype=torch.bool)
    base = m(items, mask)                                  # pref=None -> unchanged path
    cond = m(items, mask, pref={"style": torch.randn(1, 16),
                                "color": torch.randn(1, 16)})
    assert base.shape == (1,)
    assert not torch.allclose(base, cond)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_composer.py::test_pref_tokens_change_output_and_are_optional -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword 'pref_groups'`.

- [ ] **Step 3: Modify `src/outfitmatch/train/composer.py`**

Add `pref_groups` to `__init__` and a `pref` dict arg to `forward` (one projected token per active group, appended exactly like `[OCC]`):

```python
    def __init__(self, embed_dim: int = 512, n_heads: int = 8,
                 n_layers: int = 4,
                 pref_groups: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.cls = nn.Parameter(torch.randn(1, 1, embed_dim))
        self.body_proj = nn.Linear(embed_dim, embed_dim)
        self.occ_proj = nn.Linear(embed_dim, embed_dim)
        self.pref_proj = nn.ModuleDict(
            {g: nn.Linear(embed_dim, embed_dim) for g in pref_groups})
        layer = nn.TransformerEncoderLayer(
            d_model=embed_dim, nhead=n_heads, batch_first=True,
            dim_feedforward=embed_dim * 4,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Linear(embed_dim, 1)

    def forward(
        self,
        item_embeds: torch.Tensor,
        mask: torch.Tensor,
        body: torch.Tensor | None = None,
        occ: torch.Tensor | None = None,
        pref: dict[str, torch.Tensor] | None = None,
    ) -> torch.Tensor:
        b = item_embeds.size(0)
        dev = item_embeds.device
        toks = [self.cls.expand(b, -1, -1), item_embeds]
        keep = [torch.ones(b, 1, dtype=torch.bool, device=dev), mask]
        if body is not None:
            toks.append(self.body_proj(body).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        if occ is not None:
            toks.append(self.occ_proj(occ).unsqueeze(1))
            keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        if pref:
            for group, vec in pref.items():
                toks.append(self.pref_proj[group](vec).unsqueeze(1))
                keep.append(torch.ones(b, 1, dtype=torch.bool, device=dev))
        x = torch.cat(toks, dim=1)
        pad = ~torch.cat(keep, dim=1)
        h = self.encoder(x, src_key_padding_mask=pad)
        return self.head(h[:, 0]).squeeze(-1)
```

- [ ] **Step 4: Run the full composer test file to verify nothing regressed**

Run: `uv run pytest tests/test_composer.py -v`
Expected: PASS (3 passed — the two Task 7.1 tests still green, new one green).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/train/composer.py tests/test_composer.py
git commit -m "feat: grouped [PREF] conditioning tokens in OutfitTransformer"
```

### Task 9.4: Conditional Bradley-Terry loss + triplet dataset (TDD)

**Files:**
- Create: `src/outfitmatch/train/preference.py`
- Create: `src/outfitmatch/data/preference.py`
- Test: `tests/test_preference_loss.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preference_loss.py
import math

import torch

from outfitmatch.train.preference import pairwise_bt_loss


def test_zero_margin_loss_is_log2():
    s = torch.zeros(4)
    assert abs(pairwise_bt_loss(s, s).item() - math.log(2)) < 1e-5


def test_loss_decreases_as_preferred_pulls_ahead():
    neg = torch.zeros(2)
    small_margin = pairwise_bt_loss(torch.full((2,), 0.5), neg)
    big_margin = pairwise_bt_loss(torch.full((2,), 3.0), neg)
    assert big_margin < small_margin


def test_loss_is_scalar_and_finite():
    loss = pairwise_bt_loss(torch.randn(8), torch.randn(8))
    assert loss.ndim == 0 and torch.isfinite(loss)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preference_loss.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/outfitmatch/train/preference.py`**

```python
from __future__ import annotations

import torch
import torch.nn.functional as F


def pairwise_bt_loss(score_pos: torch.Tensor,
                      score_neg: torch.Tensor) -> torch.Tensor:
    """Conditional Bradley-Terry: -log sigmoid(s+ - s-).

    Both inputs are (B,) composer scores computed with the SAME [PREF]
    tokens; minimising this ranks the preferred outfit above the rejected
    one *under that instruction*.
    """
    return -F.logsigmoid(score_pos - score_neg).mean()
```

- [ ] **Step 4: Implement `src/outfitmatch/data/preference.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from torch.utils.data import Dataset


class PreferenceTripletDataset(Dataset):
    """JSONL of conditional preference triplets.

    Each line:
      {"instruction": str, "body_shape": str,
       "pos_items": list[str], "neg_items": list[str]}
    """

    def __init__(self, jsonl_path: str | Path) -> None:
        self.rows = [
            json.loads(ln)
            for ln in Path(jsonl_path).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        r = self.rows[i]
        return {
            "instruction": r["instruction"],
            "body_shape": r.get("body_shape", "rectangle"),
            "pos_items": r["pos_items"],
            "neg_items": r["neg_items"],
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_preference_loss.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/train/preference.py src/outfitmatch/data/preference.py tests/test_preference_loss.py
git commit -m "feat: conditional Bradley-Terry loss + preference triplet dataset"
```

### Task 9.5: Config extension + preference trainer wired into runner (TDD)

**Files:**
- Modify: `src/outfitmatch/config.py` (extend `ComposerConfig`, add `task` literal)
- Modify: `src/outfitmatch/runner.py` (add `task == "preference"` branch)
- Create: `src/outfitmatch/train/preference_trainer.py`
- Test: `tests/test_config.py` (append), `tests/test_runner.py` (append)

- [ ] **Step 1: Append the failing config test**

```python
# tests/test_config.py  (append)
def test_preference_config_parses(tmp_path):
    from outfitmatch.config import load_config
    p = tmp_path / "pref.yaml"
    p.write_text(
        "name: pref-all\nseed: 42\ntask: preference\n"
        'model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}\n'
        "dataset: {hf_id: local, split: train}\n"
        "composer: {n_heads: 8, n_layers: 4, use_pref: true, "
        "pref_groups: [style, color, fit]}\n"
    )
    cfg = load_config(str(p))
    assert cfg.task == "preference"
    assert cfg.composer.use_pref is True
    assert cfg.composer.pref_groups == ["style", "color", "fit"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_preference_config_parses -v`
Expected: FAIL — `ValidationError` (`task` literal rejects `preference`; `ComposerConfig` has no `use_pref`).

- [ ] **Step 3: Extend `src/outfitmatch/config.py`**

In `ComposerConfig` add:
```python
    use_pref: bool = False
    pref_groups: list[str] = Field(default_factory=list)
```
In `ExperimentConfig` widen the task literal:
```python
    task: Literal["retrieval", "fitb", "compatibility", "preference"]
```

- [ ] **Step 4: Run config test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests green).

- [ ] **Step 5: Implement `src/outfitmatch/train/preference_trainer.py` and wire runner**

> Mirror the exact five-step TDD rhythm and structure of **Task 5.2 ("Wire fine-tune into runner")**. `train_preference(composer, encoder, structurer, dataset, *, epochs, batch_size, lr, device, log_fn)` must, per triplet batch: (1) `pref = structurer.structure(instruction, body_shape)`; (2) for each `group, phrase` in `pref.active_soft_groups()` compute `encoder.encode_text([phrase])` → build the `pref` dict keyed by group; (3) `encoder.encode_image` the `pos_items` and `neg_items` → `(B, N, D)` tensors with masks; (4) `s_pos = composer(pos, pos_mask, pref=pref_dict)`, `s_neg = composer(neg, neg_mask, pref=pref_dict)`; (5) `loss = pairwise_bt_loss(s_pos, s_neg)`; backprop; `log_fn({"bt_loss": ...})`. Add a `task == "preference"` branch in `runner.py` that builds the encoder via `build_encoder`, builds `OutfitTransformer(pref_groups=tuple(cfg.composer.pref_groups))`, builds `PromptStructurer` (Gemini client injected; offline test uses a fake `complete_fn`), runs `train_preference`, then evaluates with `preference_pairwise_accuracy` (Task 9.6 metric) and logs to W&B. Acceptance: a `tests/test_runner.py` case that monkeypatches encoder + structurer with fakes, runs `execute(cfg)` on a 4-line triplet JSONL, and asserts a finite `bt_loss` and a `pairwise_acc` in `[0, 1]` were logged — identical assertion style to the Task 5.2 runner test.

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/config.py src/outfitmatch/runner.py src/outfitmatch/train/preference_trainer.py tests/test_config.py tests/test_runner.py
git commit -m "feat: preference task config + conditional pairwise trainer in runner"
```

### Task 9.6: Preference metric + triplet generator script

**Files:**
- Modify: `src/outfitmatch/metrics/outfit.py` (add `preference_pairwise_accuracy`, `instruction_flip_consistency`)
- Create: `scripts/generate_preference_triplets.py`
- Test: `tests/test_metrics_outfit.py` (append)

- [ ] **Step 1: Append the failing metric test**

```python
# tests/test_metrics_outfit.py  (append)
import torch

from outfitmatch.metrics.outfit import preference_pairwise_accuracy


def test_pairwise_accuracy_counts_correct_orderings():
    s_pos = torch.tensor([1.0, 0.2, 3.0])
    s_neg = torch.tensor([0.0, 0.5, 1.0])      # row 1 is wrong (0.2 < 0.5)
    assert preference_pairwise_accuracy(s_pos, s_neg) == round(2 / 3, 6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_outfit.py::test_pairwise_accuracy_counts_correct_orderings -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Add metrics to `src/outfitmatch/metrics/outfit.py`**

```python
def preference_pairwise_accuracy(score_pos, score_neg) -> float:
    """Fraction of triplets where preferred outranks rejected."""
    correct = (score_pos > score_neg).float().mean().item()
    return round(correct, 6)


def instruction_flip_consistency(scores_a, scores_b) -> float:
    """For contrastive-flip pairs (same outfits, flipped instruction),
    fraction where the model's preferred outfit also flips."""
    flipped = (scores_a.argmax(dim=-1) != scores_b.argmax(dim=-1))
    return round(flipped.float().mean().item(), 6)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_outfit.py -v`
Expected: PASS (all outfit-metric tests green).

- [ ] **Step 5: Implement `scripts/generate_preference_triplets.py`**

> Non-TDD data script — described, mirroring the prose-spec style of Task 8.3. Inputs: `data/raw/outfits/outfits.jsonl`, `data/raw/catalog/catalog_metadata.parquet`, a YAML list of instruction prompts (`configs/preference/instructions.yaml`), and a Gemini client (reuse the `diskcache` pattern of the occasion labeler). For each instruction and each sampled outfit pair `(A, B)` it asks Gemini *"Given the style instruction `<I>`, which outfit better matches the user's taste? Reply A or B."* and writes `{"instruction", "body_shape", "pos_items", "neg_items"}` to `data/raw/preference/triplets.jsonl`. **Mandatory contrastive-flip generation:** for ≥30% of sampled pairs, emit the SAME `(A, B)` under ≥2 *opposing* instructions (e.g. *"minimalist, muted"* vs *"bold, statement"*) so the dataset contains rows where the preferred outfit flips with the instruction — without these, the composer learns to ignore `[PREF]`. Validate every emitted row against `PreferenceTripletDataset`'s schema before writing. CLI: `--n-pairs`, `--flip-ratio` (default 0.3), `--limit`.

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/metrics/outfit.py scripts/generate_preference_triplets.py tests/test_metrics_outfit.py
git commit -m "feat: preference pairwise/flip metrics + Gemini triplet generator"
```

### Task 9.7: Preference experiment cycle (ablation: `[PREF]` on/off, token grouping)

**Files:**
- Create: `configs/preference/pref_off.yaml`, `pref_style_only.yaml`, `pref_all_groups.yaml`
- Create: `configs/preference/instructions.yaml`

- [ ] **Step 1: Create `configs/preference/pref_off.yaml`** (baseline — composer ignores instruction)

```yaml
name: pref-off
seed: 42
task: preference
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: data/raw/preference/triplets.jsonl, split: train}
composer: {n_heads: 8, n_layers: 4, use_pref: false, pref_groups: []}
train: {epochs: 8, batch_size: 32, lr: 1.0e-4}
```

- [ ] **Step 2: Create `configs/preference/pref_style_only.yaml`**

```yaml
name: pref-style-only
seed: 42
task: preference
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: data/raw/preference/triplets.jsonl, split: train}
composer: {n_heads: 8, n_layers: 4, use_pref: true, pref_groups: [style]}
train: {epochs: 8, batch_size: 32, lr: 1.0e-4}
```

- [ ] **Step 3: Create `configs/preference/pref_all_groups.yaml`**

```yaml
name: pref-all-groups
seed: 42
task: preference
model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
dataset: {hf_id: data/raw/preference/triplets.jsonl, split: train}
composer: {n_heads: 8, n_layers: 4, use_pref: true, pref_groups: [style, color, fit]}
train: {epochs: 8, batch_size: 32, lr: 1.0e-4}
```

- [ ] **Step 4: Create `configs/preference/instructions.yaml`** (prompt bank for triplet generation)

```yaml
instructions:
  - "minimalist Korean street style, muted earth tones, oversized fit"
  - "bold statement pieces, bright colors, tailored fit"
  - "formal business, navy and grey, slim fit, no patterns"
  - "casual everyday, comfortable relaxed fit, neutral palette"
  - "vintage feminine, pastel colors, fitted silhouette"
```

- [ ] **Step 5: Generate data + run the cycle**

Run:
```bash
uv run python scripts/generate_preference_triplets.py --n-pairs 4000 --flip-ratio 0.3
uv run om-exp sweep configs/preference --out-csv docs/experiments/ablation_preference.csv
```
Expected: 3 W&B runs in group `preference`. Targets: `pref-all-groups` beats `pref-off` on **pairwise accuracy ≥ 0.70** AND **instruction-flip consistency ≥ 0.60** (proof the model actually attends to `[PREF]` rather than predicting generic compatibility).

- [ ] **Step 6: Commit**

```bash
git add configs/preference docs/experiments/ablation_preference.csv
git commit -m "feat: preference personalization experiment cycle (PREF on/off, grouping)"
```

---

## Self-Review

**1. Spec coverage**

| User ask | Covered by |
|---|---|
| Research optimal HF models | Research Findings section (encoder table, pose, composer, datasets, with links) |
| Analyze & pick best | Decision lines: FashionSigLIP fine-tuned (encoder); YOLO-pose cycle (body); OutfitTransformer (composer) |
| Complete Scrum/XP plan | 10 sprints, sprint goals, TDD every code task, frequent commits, CI gate |
| Cycles vary dataset *type* | Sprint 4 (DeepFashion vs Fashion200K vs Multimodal), Sprint 7 (Polyvore disjoint vs nondisjoint) |
| Cycles vary *number of rows* | `max_rows` in config from Task 1.1; Sprint 5 scaling cycle 5K/25K/100K |
| Cycles vary *models* | Sprint 3 (4 encoders), Sprint 6 (YOLOv8 vs YOLO11), Sprint 7 (conditioning variants) |
| Personalized preference modeling | Sprint 9 — Gemini structuring layer, grouped `[PREF]` tokens, conditional Bradley-Terry pairwise; hard→Qdrant filter (body-shape fallback), soft→tokens |
| Grading targets | Sprint 5 (+5% Recall@5), Sprint 7 (FITB ≥55%, AUC ≥0.85, +10% body Precision@5), Sprint 9 (pairwise acc ≥0.70, flip consistency ≥0.60) |

**2. Placeholder scan:** Sprints 0–6, 7.1, 8.1, and 9.1–9.4 / 9.7 are fully bite-sized with complete code. Five tasks delegate sub-structure via explicit `>` notes (Task 5.1 train-mode flag, Task 7.2 composer config + fitb/compat runner branches, Task 8.2 index/UI, Task 9.5 preference trainer wiring, Task 9.6 triplet generator script): each names exact files, the pattern to copy from an earlier task, and the TDD/validation acceptance — actionable, not "TBD". The executing agent expands these by replicating the cited task's five-step rhythm.

**3. Type consistency:** `BaseEncoder.encode_image/encode_text` (Task 2.1) used identically in 2.2/2.3/5.1/9.5; `ExperimentConfig` fields (`model.kind`, `model.finetune`, `dataset.max_rows`, `train.epochs/batch_size/lr`, `task` literal incl. `preference`, `composer.use_pref/pref_groups`) consistent across all configs and runner; `execute(cfg, group, job_type)` signature consistent in 2.4/3.2/runner; `OutfitTransformer(embed_dim, n_heads, n_layers, pref_groups)` and its `forward(item_embeds, mask, body, occ, pref)` signature consistent between Task 7.1, 9.3, and 9.5; `StructuredPreference` / `HardConstraint` / `SoftPreference` / `apply_body_fallback` / `PromptStructurer.structure` / `pairwise_bt_loss` / `PreferenceTripletDataset` / `preference_pairwise_accuracy` consistent across Sprint 9 tasks; metric names `recall@1/5/10`, `map`, `fitb_accuracy`, `compatibility_auc`, `pairwise_acc`/`flip_consistency` consistent between metrics modules, eval, and CSV export.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-outfitmatch-experiment-cycles.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
