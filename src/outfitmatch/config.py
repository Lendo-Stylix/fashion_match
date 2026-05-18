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


class ComposerConfig(BaseModel):
    n_heads: int = 8
    n_layers: int = 4
    embed_dim: int = 512
    use_body: bool = False
    use_occ: bool = False


class ExperimentConfig(BaseModel):
    name: str
    seed: int = 42
    task: Literal["retrieval", "fitb", "compatibility"]
    model: ModelConfig
    dataset: DatasetConfig
    train: TrainConfig = Field(default_factory=TrainConfig)
    composer: ComposerConfig | None = None
    wandb_project: str = "outfitmatch-grading"


def load_config(path: str | Path) -> ExperimentConfig:
    data = yaml.safe_load(Path(path).read_text())
    return ExperimentConfig.model_validate(data)
