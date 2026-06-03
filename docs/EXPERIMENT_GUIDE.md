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
| 2 | Tầng 3 | Body conditioning on/off | _pending item semantic tagging_ | Body-cond Precision@5 (+10pp target) |
| 3 | Tầng 3 | Occasion conditioning on/off | `scripts.data.kb.eval_graph --occasion ...` | coverage + FITB recall của graph |
| 4 | Tầng 3 | Greedy vs Beam traversal (`beam=1` vs `beam=3`) | `scripts.data.kb.eval_graph` | coverage + FITB recall của graph |

```bash
# 1 — Encoder (zero-shot vs fine-tuned OT-labse trên Polyvore)
uv run python scripts/ablation_encoder.py --out docs/experiments/ablation_encoder.csv

# 2 — Body filter
# BLOCKED: cần item body-fit tagging trước khi bật ablation graph

# 3 + 4 — Occasion filter + traversal beam ablation
uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office
# full-sweep grading baseline:
uv run python -m scripts.data.kb.eval_graph --seeds 0 --occasion office
```

## Graph KB eval (v3.1 graph)

Dùng `scripts.data.kb.eval_graph` để đọc trực tiếp graph hiện tại:

```bash
uv run python -m scripts.data.kb.eval_graph --seeds 300
uv run python -m scripts.data.kb.eval_graph --seeds 0 --occasion office
```

Đọc các số sau:
- `catalog_coverage` — diversity chính của graph KB
- `coherence_violations` — **phải bằng 0**
- `fitb_recall@5` — self-consistency Recall@5 của graph
- `ablation occasion` — seed filter có/không `formalities_for_occasion`
- `ablation decoding` — `beam=1` vs `beam=3`

`body_shape` ablation vẫn chờ item-tagging follow-up.

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

Mỗi script eval cuối kỳ ở `scripts/` đều:
1. Nhận tham số CLI qua `typer` hoặc `argparse`.
2. Output 1 CSV duy nhất ở `docs/experiments/`.
3. Idempotent: chạy lại không phá kết quả cũ (append với header check).
4. Có docstring đầu file chỉ ra: ablation nào, target metric, expected runtime.

Ngoại lệ hiện tại: `scripts.data.kb.eval_graph` là harness vận hành cho graph KB,
log thẳng ra stdout để sanity-check coverage / coherence / FITB recall trước Sprint 9.
