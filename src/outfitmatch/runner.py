from __future__ import annotations

from outfitmatch.config import ExperimentConfig
from outfitmatch.seeding import set_seed
from outfitmatch.tracking import start_run


def execute(cfg: ExperimentConfig, group: str = "default",
            job_type: str = "run") -> dict[str, float]:
    set_seed(cfg.seed)
    run = start_run(cfg, group=group, job_type=job_type)
    try:
        if cfg.task == "retrieval":
            from outfitmatch.data.retrieval import RetrievalDataset
            from outfitmatch.encoders.factory import build_encoder
            from outfitmatch.eval.retrieval_eval import evaluate_retrieval

            encoder = build_encoder(cfg.model)
            ds = RetrievalDataset(
                cfg.dataset.hf_id, cfg.dataset.config,
                cfg.dataset.split, cfg.dataset.max_rows,
            )
            if cfg.model.finetune and cfg.train.epochs > 0:
                from outfitmatch.train.contrastive import finetune_encoder

                finetune_encoder(
                    encoder, ds,
                    epochs=cfg.train.epochs,
                    batch_size=cfg.train.batch_size,
                    lr=cfg.train.lr,
                    log_fn=run.log,
                )
            metrics = evaluate_retrieval(encoder, ds,
                                         batch_size=cfg.train.batch_size)

        elif cfg.task in ("fitb", "compatibility"):
            raise NotImplementedError(
                f"task '{cfg.task}' implemented in Sprint 7 — "
                "see docs/superpowers/plans/2026-05-18-outfitmatch-experiment-cycles.md"
            )
        else:
            raise ValueError(f"unknown task: {cfg.task}")

        run.log(metrics)
        return metrics
    finally:
        run.finish()
