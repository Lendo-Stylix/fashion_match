from __future__ import annotations

from outfitmatch.config import ExperimentConfig
from outfitmatch.seeding import set_seed
from outfitmatch.tracking import start_run
from outfitmatch.train.preference import pairwise_bt_loss


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

        elif cfg.task == "preference":
            from outfitmatch.data.preference import PreferenceTripletDataset
            from outfitmatch.encoders.factory import build_encoder
            from outfitmatch.metrics.outfit import preference_pairwise_accuracy
            from outfitmatch.preference.structuring import PromptStructurer
            from outfitmatch.train.composer import OutfitTransformer
            from outfitmatch.train.preference_trainer import train_preference

            encoder = build_encoder(cfg.model)
            composer_cfg = cfg.composer or {}
            n_heads = getattr(composer_cfg, "n_heads", 8)
            n_layers = getattr(composer_cfg, "n_layers", 4)
            pref_groups = tuple(getattr(composer_cfg, "pref_groups", []))
            composer = OutfitTransformer(
                embed_dim=encoder.embed_dim,
                n_heads=n_heads,
                n_layers=n_layers,
                pref_groups=pref_groups,
            )
            # Gemini complete_fn: in real usage inject google.generativeai;
            # for offline/test, a fake is monkeypatched at the call site.
            complete_fn = getattr(cfg, "_complete_fn",
                                  lambda p: '{"hard":{"colors_avoid":[],'
                                  '"categories_exclude":[],"materials_require":[]},'
                                  '"soft":{"style":"","color":"","fit":""}}')
            structurer = PromptStructurer(complete_fn)

            ds = PreferenceTripletDataset(cfg.dataset.hf_id)

            train_preference(
                composer, encoder, structurer, ds,
                epochs=cfg.train.epochs,
                batch_size=cfg.train.batch_size,
                lr=cfg.train.lr,
                log_fn=run.log,
            )

            # Evaluate on full dataset
            s_pos_all, s_neg_all = [], []
            import torch as _torch
            for i in range(len(ds)):
                item = ds[i]
                pref = structurer.structure(item["instruction"], item["body_shape"])
                pref_dict = {g: encoder.encode_text([ph])
                             for g, ph in pref.active_soft_groups().items()}
                d = encoder.embed_dim
                pos_e = _torch.zeros(1, len(item["pos_items"]), d)
                neg_e = _torch.zeros(1, len(item["neg_items"]), d)
                pm = _torch.ones(1, len(item["pos_items"]), dtype=_torch.bool)
                nm = _torch.ones(1, len(item["neg_items"]), dtype=_torch.bool)
                s_pos_all.append(
                    composer(pos_e, pm, pref=pref_dict if pref_dict else None))
                s_neg_all.append(
                    composer(neg_e, nm, pref=pref_dict if pref_dict else None))
            s_pos = _torch.cat(s_pos_all)
            s_neg = _torch.cat(s_neg_all)
            metrics = {
                "pairwise_acc": preference_pairwise_accuracy(s_pos, s_neg),
                "bt_loss": pairwise_bt_loss(s_pos, s_neg).item(),
            }

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
