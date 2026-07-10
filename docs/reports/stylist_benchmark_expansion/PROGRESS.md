# Progress Tracker — Stylist Benchmark Expansion

**Branch:** `feat/benchmark`  
**Ngày bắt đầu:** 2026-07-09  
**Mục tiêu:** xây dựng & đề xuất benchmark cho năng lực cốt lõi của stylist (tri thức + logic thời trang) cho 4 adapter QLoRA đã fine-tune.

Trạng thái ký hiệu: ☐ todo · ⧗ đang làm · ✅ done · ⛔ blocked

---

## A. Benchmark trong-repo (rule-based) — `stylist/fashion_eval.py`

| # | Item bank / scorer | Trạng thái | Số item | Test | Coverage | Ghi chú |
|---|---|---|---|---|---|---|
| A1 | `OCCASION_FORMALITY_ITEMS` + `score_occasion_formality` | ✅ | 9 | 6 | 98% | nền `formalities_for_occasion` |
| A2 | `BODY_SHAPE_ADVICE_ITEMS` + `score_body_shape_advice` | ✅ | 5 | 4 | 98% | curated positive/negative cues |
| A3 | `SEASON_ADVICE_ITEMS` + `score_season_advice` | ✅ | 4 | 3 | 98% | curated fabric/layering cues |
| A4 | `COHERENCE_ITEMS` + `score_coherence_judgment` + `detect_verdict` | ✅ | 4 | 5 | 98% | nền `FORMALITY_TOLERANCE=1` |
| A5 | `ASK_BACK_ITEMS` + `score_ask_back` | ✅ | 3 | 4 | 98% | bắt hallucinate occasion |
| A6 | `TOOL_CALL_DERIVATION_ITEMS` + `score_tool_call_derivation` | ✅ | 3 | 4 | 98% | enum-validity gate |
| A7 | `evaluate_fashion_dataset` aggregator | ✅ | — | 2 | 98% | cùng `generate_fn` contract |

**Kết quả xác minh:** `uv run pytest tests/test_stylist_fashion_eval.py -q` → **34 passed**; `ruff check` + `ruff format --check` + `mypy` sạch; full suite `uv run pytest -q` → **365 passed**.

### Milestone A
- ✅ Thiết kế API & dataclass-style items (TDD RED).
- ✅ Implement scorer + item bank (TDD GREEN).
- ✅ Refactor: thêm body_shape/season knowledge; fix ruff/mypy.
- ✅ Runner CLI `scripts/stylist/run_fashion_benchmark.py` (--mock reproducible, --model/--adapter real).
- ✅ `Makefile bench-fashion` smoke regression guard.
- ✅ `stylist/__init__.py` exports `evaluate_fashion_dataset`.
- ✅ Docstring public functions + `docs/feature.md` entry `stylist-fashion-eval`.
- ✅ Coverage 98% (≥ target 70%).
- ✅ Full gate: ruff + mypy + 392 pytest passed.
- ✅ `eval_graph.py` --output-csv (structured CSV, 3 ablations, 4 metrics per ablation).
- ✅ `scripts/metrics_summary.py` (Markdown + JSON aggregator, 15 tests).

---

## B. Benchmark ngoài dự án — research & đề xuất

| # | Benchmark | Nhóm | Ưu tiên | Trạng thái | Model phù hợp | Nguồn |
|---|---|---|---|---|---|---|
| B1 | BFCL — Berkeley Function Calling | tool-calling | P0 | ☐ setup | T1/T2/T3/T4 | proceedings.mlr.press/v267/patil25a.html |
| B2 | IFEval — instruction following | instruction | P0 | ☐ setup | T1/T2/T3/T4 | arxiv.org/abs/2311.07911 |
| B3 | Polyvore Outfits FITB + Compat AUC | fashion downstream | P0 | ⧗ đã có code `metrics/outfit.py` | retrieval pipeline | ECCV 2018 Type-Aware |
| B4 | StableToolBench | tool-calling | P1 | ☐ setup | T1/T2/T3/T4 | aclanthology.org/2024.findings-acl.664 |
| B5 | MT-Bench / mini-MT tiếng Việt | chat | P1 | ☐ setup | T1/T2/T3/T4 | arxiv.org/abs/2306.05685 |
| B6 | MMMU | VLM reasoning | P1 | ☐ setup | T1/T3/T4 (+T2 text fallback) | CVPR 2024 |
| B7 | SEED-Bench | VLM reasoning | P1 | ☐ setup | T1/T3/T4 | CVPR 2024 |
| B8 | Marqo 7-dataset fashion retrieval suite | fashion retrieval | P1 | ☐ setup | encoder/retrieval | github.com/Marqo-AI/marqo-FashionCLIP |
| B9 | DeepFashion | fashion retrieval | P1 | ☐ setup | retrieval/VLM | CVPR 2016 |
| B10 | Arena-Hard-Auto | chat | P2 | ☐ setup | T1/T2/T3/T4 | arxiv.org/abs/2406.11939 |
| B11 | MathVista | VLM reasoning | P2 | ☐ setup | T1/T3/T4 | ICLR 2024 |
| B12 | FashionIQ | conversational retrieval | P2 | ☐ setup | stylist+retrieval | CVPR 2021 |

### Milestone B (kế hoạch)
- ☐ B3 Polyvore: tích hợp `src/outfitmatch/metrics/outfit.py` (FITB acc + Compat AUC) làm regression guard cho graph retrieval.
- ☐ B1+B2: chuẩn hóa `StylistModelAdapter.generate_fn` cho 4 adapter, chạy BFCL subset + IFEval.
- ☐ B5..B9: hội thoại + VLM + fashion retrieval (P1), dùng testmini khi nặng.
- ☐ B10..B12: nice-to-have (P2).

---

## C. Thiết kế harness chung (dùng cho cả A và B)

| # | Việc | Trạng thái |
|---|---|---|
| C1 | `StylistModelAdapter` interface (generate_text / _with_images / _tool_call) | ⧗ mock done, real-gpu adapter todo |
| C2 | Cấu hình chạy công bằng (temperature, decoding, judge) | ✅ (cho A: deterministic) |
| C3 | Định dạng output `reports/benchmarks/<bench>/<run_id>/` | ✅ JSON report via `run_fashion_benchmark --output-json` |
| C4 | Bảng metrics tổng hợp `model, benchmark, split, metric, value, n, date, commit_sha` | ✅ `scripts/metrics_summary.py` + 15 tests |

---

## D. Xác minh chất lượng

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Test fashion-eval | `uv run pytest tests/test_stylist_fashion_eval.py -q` | ✅ 34 passed |
| Test runner mock | `uv run pytest tests/test_run_fashion_benchmark.py -q` | ✅ 7 passed |
| Test eval_graph CSV | `uv run pytest tests/kb/test_eval_graph.py -q` | ✅ 5 passed |
| Test metrics_summary | `uv run pytest tests/test_metrics_summary.py -q` | ✅ 17 passed |
| Test setup_models | `uv run pytest tests/test_setup_models.py -q` | ✅ 13 passed |
| Test toàn repo | `uv run pytest -q` | ✅ 407 passed |
| Ruff lint | `uv run ruff check src tests scripts` | ✅ All checks passed |
| Ruff format | `uv run ruff format --check src tests scripts` | ✅ All files formatted |
| Mypy | `uv run mypy src scripts/data/kb/eval_graph.py` | ✅ no issues |
| Smoke mock | `uv run python -m scripts.stylist.run_fashion_benchmark --mock` | ✅ valid JSON report |
| Smoke eval_graph CSV | `uv run python -m scripts.data.kb.eval_graph --seeds 50 --output-csv docs/experiments/eval_graph_test.csv` | ✅ 12 rows, 3 ablations |
| Smoke setup_models | `uv run python scripts/setup_models.py --adapters --models T3` | ✅ T3 adapter → D:/Models/adapters |

---

## F. Model pulling về D:/Models (KHÔNG ổ C)

| # | Việc | Trạng thái |
|---|---|---|
| F1 | `scripts/setup_models.py` — pull 4 base + 4 adapter về D:/Models | ✅ 13 tests |
| F2 | `Makefile setup-models` target | ✅ |
| F3 | `.env.example` — HF_HOME/HF_HUB_CACHE → D:/Models | ✅ (tracked) |
| F4 | 4 LoRA adapters downloaded → `D:/Models/adapters/` | ✅ T1/T2/T3/T4 |
| F5 | Base models T1/T3 downloaded → `D:/Models/hf_hub/` (6.9GB/cái) | ✅ |
| F6 | Base models T2/T4 | ⧗ downloading |

> `make setup-models` hoặc `uv run python scripts/setup_models.py --base --adapters` để pull tất cả.
> Adapters nhỏ (~200MB/cái), base 4-bit ~5–7GB/cái.

---

## E. Lịch sử thay đổi

- 2026-07-10: research mở rộng benchmark (FashionStylist V1, fashion-agent-benchmark, SEA-IFEval, MMMU-Pro, MM-Vet, τ-bench); `scripts/setup_models.py` pull models về D:/Models; `.env.example` HF cache config; `benchmark_resume.md` + `benchmark_template_per_model.md`.
- 2026-07-09: tạo branch `feat/benchmark`; triển khai `stylist/fashion_eval.py` (6 item bank + 6 scorer + aggregator) với 34 test; cập nhật `docs/feature.md` + báo cáo này.
