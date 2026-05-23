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
    p.write_text(
        "name: x\nseed: 1\ntask: NOPE\n"
        "model:\n  kind: hf_clip\n  checkpoint: a\n"
        "dataset:\n  hf_id: a\ntrain: {}\n"
    )
    with pytest.raises((ValueError, Exception)):
        load_config(p)


def test_composer_config_parsed(tmp_path: Path):
    yaml_text = textwrap.dedent("""
        name: composer-body
        seed: 42
        task: fitb
        model: {kind: open_clip, checkpoint: "hf-hub:Marqo/marqo-fashionSigLIP"}
        dataset: {hf_id: owj0421/polyvore-outfits, config: disjoint_fill_in_the_blank, split: train}
        composer: {n_heads: 8, n_layers: 4, use_body: true, use_occ: false}
        train: {epochs: 10, batch_size: 64, lr: 1.0e-4}
    """)
    p = tmp_path / "comp.yaml"
    p.write_text(yaml_text)
    cfg = load_config(p)
    assert cfg.composer is not None
    assert cfg.composer.use_body is True
    assert cfg.composer.use_occ is False


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
