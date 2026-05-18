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
