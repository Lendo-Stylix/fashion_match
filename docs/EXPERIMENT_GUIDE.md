# Experiment Guide — v3.1-lite

> Đọc [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) và [`Kien_truc_v3.1.md`](../Kien_truc_v3.1.md) trước.

Sprint 9 chạy 2 nhóm eval cho academic deliverable. Toàn bộ output đi vào
`docs/experiments/` (mỗi metric một CSV) — file `RESULTS.md` tổng hợp cuối Sprint 9.

---

## A. Product Quality — LLM-as-Judge

Gemini chấm `RecommendResult` E2E trên thang 1–5 (style, fit, occasion, overall).
Target: **mean ≥ 3.5 / 5**.

```bash
uv run python scripts/llm_judge.py \
    --results data/eval/recommend_results.jsonl \
    --out docs/experiments/llm_judge_results.csv
```

`recommend_results.jsonl` được sinh bằng cách chạy `pipeline.recommend_outfit()`
trên một bộ test prompt (cover đủ 9 OCCASION × 8 STYLE).

---

## B. Bốn Ablation bắt buộc

| # | Tầng | Mục tiêu | Script | Metric |
|---|---|---|---|---|
| 1 | Tầng 1 | Encoder variants: OT-labse zero-shot vs OT-labse fine-tuned Polyvore | `ablation_encoder.py` | FITB acc + Compat AUC |
| 2 | Tầng 3 | Body conditioning on/off | `ablation_body_filter.py` | Body-cond Precision@5 (+10pp target) |
| 3 | Tầng 3 | Occasion conditioning on/off | `ablation_occasion_filter.py` | Occasion-cond Precision@5 |
| 4 | Tầng 1 | Greedy vs Beam decoding (FITB+Beam generation) | `ablation_decoding.py` | FITB acc của KB resulting |

```bash
# 1 — Encoder (zero-shot vs fine-tuned OT-labse trên Polyvore)
uv run python scripts/ablation_encoder.py --out docs/experiments/ablation_encoder.csv

# 2 — Body filter
uv run python scripts/ablation_body_filter.py --out docs/experiments/ablation_body_filter.csv

# 3 — Occasion filter
uv run python scripts/ablation_occasion_filter.py --out docs/experiments/ablation_occasion_filter.csv

# 4 — Decoding (greedy vs beam)
uv run python scripts/ablation_decoding.py \
    --kb-greedy data/kb/kb_greedy.parquet \
    --kb-beam   data/kb/kb_beam.parquet \
    --out docs/experiments/ablation_decoding.csv
```

---

## C. E2E Latency

```bash
# Target: < 5–8s trên GPU với streaming UX
uv run python scripts/measure_latency.py \
    --n-requests 50 \
    --out docs/experiments/latency.csv
```

---

## D. FITB / Compat AUC trên Polyvore (`Kien_truc_v3.1.md` §3.6)

OT-labse dùng frozen để build KB. Để báo cáo grading metric, fine-tune nhẹ OT trên
Polyvore (FITB / compat chuẩn — KHÔNG liên quan token `[OCC]`/`[PREF]`).

```bash
uv run python scripts/ot_eval_polyvore.py \
    --checkpoint fkuyumcu/OutfitTransformer-labse \
    --split test \
    --out docs/experiments/ot_polyvore.csv
```

Metric pure-math nằm ở `src/outfitmatch/metrics/outfit.py`:
- `fitb_accuracy(preds, labels)` — top-1 trong các candidate.
- `compatibility_auc(scores, labels)` — `sklearn.metrics.roc_auc_score`.

---

## E. W&B (chỉ cho LoRA fine-tune)

Project: `outfitmatch-v3.1`. LoRA training logs:
- `train/loss` (step-level)
- `eval/loss`, `eval/perplexity` (epoch-level)
- 1 sample dialog completion mỗi 500 step (qua `WandbCallback` custom)

Eval scripts (ablation/judge/latency) ghi thẳng vào CSV, KHÔNG dùng W&B.

---

## F. Tổng hợp kết quả → RESULTS.md

```bash
uv run python scripts/aggregate_experiments.py
# writes docs/experiments/RESULTS.md
```

`RESULTS.md` là nguồn cho phần "Experiments" của báo cáo cuối kỳ — mỗi ablation
một bảng với row tốt nhất bold.

---

## G. Script structure convention

Mỗi script eval ở `scripts/` đều:
1. Nhận tham số CLI qua `typer` hoặc `argparse`.
2. Output 1 CSV duy nhất ở `docs/experiments/`.
3. Idempotent: chạy lại không phá kết quả cũ (append với header check).
4. Có docstring đầu file chỉ ra: ablation nào, target metric, expected runtime.

Sprint 9 hiện vẫn chưa có script — sẽ được implement khi Tầng 1-4 chạy thật.
Trước Sprint 9, không có script eval nào trong repo.
