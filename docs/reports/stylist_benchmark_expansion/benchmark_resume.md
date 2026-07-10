# Benchmark Resume — Stylist Models (T1/T2/T3/T4)

**Ngày:** 2026-07-10 · **Branch:** `feat/benchmark` · **4 Stylist Adapters**

> Bảng tổng hợp đầy đủ benchmarks đề xuất cho 4 Stylist adapters, phân 4 tầng:
> fashion downstream / tool-calling+instruction / VLM reasoning / chat.
> Mỗi benchmark: size, metric, model fit, ưu tiên (P0/P1/P2), source, cách chạy.

---

## 4 Adapters & Base Models (HF IDs verified 2026-07-10)

| ID | Label | Base Model (HF) | LoRA Adapter (HF) | Multimodal |
|----|-------|-----------------|-------------------|:----------:|
| T1 | Qwen3-VL-8B Instruct | `unsloth/Qwen3-VL-8B-Instruct-bnb-4bit` | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-instruct-lora` | Yes |
| T2 | Qwen3.5-9B BNB4 | `techwithsergiu/Qwen3.5-text-9B-bnb-4bit` | `Nhat-Quang/outfitmatch-stylist-final-qwen35-9b-bnb4-lora` | text only |
| T3 | Qwen3-VL-8B Thinking | `unsloth/Qwen3-VL-8B-Thinking-bnb-4bit` | `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora` | Yes |
| T4 | Gemma 4 12B IT | `unsloth/gemma-4-12b-it` | `Nhat-Quang/outfitmatch-stylist-final-gemma4-12b-it-lora` | Yes |

> T3 được chọn làm stylist model chính (Tool F1 cao nhất, loss thấp nhất, stability tốt nhất).
>
---

## Tier 1 — Fashion Downstream (P0)

| # | Benchmark | Year | Size | Metric | Model fit | Priority | Source |
|---|-----------|------|------|--------|-----------|:--------:|--------|
| B-fs | FashionStylist V1 | 2026-04 | 1000 outfit + 4637 item (F:500/M:300/C:200) | Task1 Grounding F1, Task2 Completion acc, Task3 Eval | T1/T2/T3/T4 | **P0** | github.com/recsys-benchmark/FashionStylist |
| B-fa | fashion-agent-benchmark | 2026 | 200 tasks x 5 evaluators x 2766 SKU | relevance, budget, inventory, citation, coherence | T1/T2/T3/T4 | **P0** | github.com/arturayupov/fashion-agent-benchmark (MIT) |
| B-po | Polyvore FITB + Compat AUC | 2018 ECCV | ~200k outfits | FITB acc >= 0.55, Compat AUC >= 0.85 | retrieval/encoder | **P0** | github.com/xthan/polyvore-dataset |
| B-iq | FashionIQ | 2021 CVPR | 47k conv-turns | R@K composed retrieval | stylist+retrieval | P2 | github.com/xuehai99/Fashion-Intelligence |

## Tier 2 — Tool-calling & Instruction Following (P0/P1)

| # | Benchmark | Year | Size | Metric | Model fit | Priority | Source |
|---|-----------|------|------|--------|-----------|:--------:|--------|
| B-bfcl | BFCL V4 | 2025+ | ~2000 cases | overall acc, AST exec, relevance | T1/T2/T3/T4 | **P0** | github.com/ShishirPatil/gorilla (berkshire-function-call) |
| B-ife | IFEval | 2023 v2 | 541 prompts | strict + loose instruction acc | T1/T2/T3/T4 | **P0** | github.com/google-research (instruction_following) |
| B-sea-ife | SEA-IFEval | 2025 |_multilingual SEA + VN subset | instruction acc (VN) | T1/T2/T3/T4 | P1 | ai-for-k12/sea-helm |
| B-stt | StableToolBench | 2024 findings-ACL | ~7k API calls | pass@1, hallucination rate | T1/T2/T3/T4 | P1 | aclanthology.org/2024.findings-acl.664 |
| B-tau | tau-bench | 2024 | 165 multi-turn tasks | task success, tool acc | T1/T2/T3/T4 | P1 | github.com/sierra-projects/tau-bench |

## Tier 3 — VLM Multimodal Reasoning (P1/P2)

| # | Benchmark | Year | Size | Metric | Model fit | Priority | Source |
|---|-----------|------|------|--------|-----------|:--------:|--------|
| B-mmmu-pro | MMMU-Pro | 2024 | ~10k questions | accuracy (college MM) | T1/T3/T4 (+T2 text) | P1 | huggingface.co/datasets/MMMU/MMMU_Pro |
| B-mv | MM-Vet | 2024 | 218 questions | integrated VLM score (GPT-4 judge) | T1/T3/T4 | P1 | github.com/yuweihao/mm-vet |
| B-seed | SEED-Bench v2 | 2024 | 19k multiple-choice | accuracy, 27 eval dims | T1/T3/T4 | P1 | github.com/SEED-Bench-v2 |
| B-mmmu | MMMU | 2024 CVPR | 11.5k college questions | accuracy (30 subjects) | T1/T3/T4 (+T2 text) | P2 | mmmu-benchmark.github.io |
| B-mathv | MathVista | 2024 ICLR | 6000 problems | accuracy + rel acc | T1/T3/T4 | P2 | mathvista.github.io |

## Tier 4 — Chat & Multilingual (P1/P2)

| # | Benchmark | Year | Size | Metric | Model fit | Priority | Source |
|---|-----------|------|------|--------|-----------|:--------:|--------|
| B-mt-vi | MT-Bench / mini-MT (VN) | 2023 | 80 / 50 prompts | GPT-4 judge score 1-10 | T1/T2/T3/T4 | P1| huggingface.co/datasets/HuggingFaceH4/mt_bench |
| B-arena | Arena-Hard-Auto | 2024 | 500 prompts | win-rate vs baseline | T1/T2/T3/T4 | P2 | github.com/lmarena/arena-hard-auto |

---

## Priority order (P0) for Sprint 9 academic deliverable

1. **B-fs** FashionStylist V1 (3 tasks) — mới nhất, match exact schema of OutfitMatch (occasion/season/gender/style).
2. **B-fa** fashion-agent-benchmark — 5 evaluators, occasion + budget logic match stylist tool contract.
3. **B-bfcl** BFCL V4 subset — tool-calling chính.
4. **B-ife** IFEval — instruction-following chính.
5. **B-po** Polyvore FITB + Compat AUC — regression guard for graph retrieval đã có code (`metrics/outfit.py`).

> Văn bản gốc (Kien_truc v3.1 §3.6): FITB acc, Compat AUC đo bằng OT-labse — đo bằng OT-labse trên Polyvore dataset.

## See also

- [`benchmark_template_per_model.md`](benchmark_template_per_model.md) — JSON schema per-model + adapter wiring.
- [`PROGRESS.md`](PROGRESS.md) — status per-benchmark.
