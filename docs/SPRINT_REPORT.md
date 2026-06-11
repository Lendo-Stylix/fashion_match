# OutfitMatch — Báo cáo Tiến độ Dự án (Scrum/XP)

**DPL302m · Nhóm 3 dev · Timeline mục tiêu: 7 sprint × 1 tuần**

> Cập nhật hiện tại: project đã chuyển sang **graph KB primary path**. Đường dẫn chính là
> `catalog item nodes -> semantic item tags -> sparse compatibility graph -> Qdrant items seed filter -> traversal ráp outfit động`.
> Materialized `generated_outfits.parquet` / Qdrant `outfits` chỉ còn là legacy comparison.

---

## 1. Thông tin Dự án

| Mục | Chi tiết |
|---|---|
| Tên dự án | OutfitMatch — AI Stylist Cá nhân hóa |
| Môn học | DPL302m — Deep Learning Project |
| Nhóm | 3 sinh viên |
| Branch hiện tại | `Model` → merge vào `dev` theo từng sprint |
| Repo | github.com/vominhnhatquang/fashion_match_project |
| Canonical docs | `Kien_truc_v3.1.md`, `docs/ARCHITECTURE.md`, `docs/EXPERIMENT_GUIDE.md` |

---

## 2. Kiến trúc Hệ thống (v3.1-lite, 4 tầng)

```text
Tầng 1  Graph KB Builder
        scrape VN catalog -> semantic item tags -> embeddings/pair scoring -> item_edges.parquet

Tầng 2  Conversational Stylist
        Qwen3-VL-8B + LoRA planned; tool schema + validation guardrails implemented

Tầng 3  Retrieval Engine
        Qdrant `items` seed filter or graph scan fallback -> traversal -> derived OutfitRecord

Tầng 4  Personalization
        Quiz 5 câu -> rerank rule-based -> size suggestion -> Top 3-5
```

**Stack:** Python 3.13 · uv · Qdrant · OutfitTransformer-labse · Qwen3-VL target · Gradio target · pytest/ruff/mypy

---

## 3. Snapshot hiện tại

### 3.1 Trạng thái theo mảng

| Mảng | Trạng thái | Ghi chú |
|---|---|---|
| Foundation/vocab/schema | ✅ Done | `vocab.py`, `ItemRecord`, `OutfitRecord` ổn định |
| VN catalog scraper | ✅ Done | adapters + batch gate + manifest + quality checks |
| Item semantic tagging | ✅ Done/usable | 5,618/5,618 item có tag hoặc payload non-empty; audit invalid = 0 |
| Graph KB construction | ✅ Done | `item_edges.parquet` là artifact chính |
| Graph retrieval | ✅ Done | seed item filter + clique traversal + post-filter |
| Quiz rerank/sizing | ✅ Done | deterministic MVP personalization |
| Pipeline deterministic path | ✅ Done | retrieval/rerank/size path implemented |
| Stylist Qwen model/data | 🚧 Planned/stub | `model.py`, `data.py` raise `NotImplementedError` |
| UI/API demo | 🚧 Planned/stub | Gradio entry point placeholder |
| Final experiments | 🚧 Pending | LLM judge, latency, final ablations |

### 3.2 Artifact/metric snapshot

| Artifact / metric | Giá trị hiện tại |
|---|---:|
| `catalog_metadata.parquet` rows | 5,618 |
| `item_store_links.parquet` rows | 5,618 |
| Manifest batches passed | 25/25 |
| Adult graph nodes (`men|women|unisex`) | 4,694 |
| Canonical graph edges | 316,559 |
| Legacy materialized outfits | 1,000 |
| Item-tag audit invalid rows | 0 |
| Item-tag audit pending empty | 0 |
| Outfit-tag audit valid core outfits | 824/824 |
| Outfit-tag audit complete-with-shoes | 816/824 |
| Outfit-tag audit high-severity flags | 0 |

Historical graph grading baseline kept as regression target:

- `catalog_coverage = 0.7069`
- `coherence_violations = 0`
- `fitb_recall@5 = 0.9813`
- `n_assembled = 7350`
- `item_reuse_p95 = 27`

---

## 4. Sprint 1 — Foundation & Scaffolding ✅

**Goal:** Dựng nền tảng 4 tầng v3.1-lite và controlled vocabulary thống nhất.

### Deliverables chính

- `src/outfitmatch/vocab.py` — enum/source of truth.
- `src/outfitmatch/kb/schema.py` — `ItemRecord`, `OutfitRecord`.
- `src/outfitmatch/stylist/tools.py` — `SEARCH_OUTFITS_TOOL`.
- `src/outfitmatch/stylist/validation.py` — chống hallucinate `outfit_id` + explicit size validation.
- `src/outfitmatch/quiz/schema.py`, `quiz/rerank.py`, `quiz/sizing.py`.
- `src/outfitmatch/metrics/outfit.py`, `metrics/retrieval.py`.

### Kết quả

- Vocabulary invariant được chốt ở `vocab.py`.
- Quiz rerank thay thế GNN trong MVP để giảm rủi ro.
- Stylist guardrails có trước khi model chat hoàn thiện.

---

## 5. Sprint 2 — Catalog Pipeline & Graph KB Construction ✅

**Goal:** Chuyển KB từ materialized outfits sang **item-compatibility graph**.

### Deliverables chính

- `scripts/data/scrape/` pipeline: registry, adapters, raw cache, normalization, batch gate, manifest, quality checks.
- `src/outfitmatch/kb/catalog.py` load catalog chuẩn hoá thành `ItemRecord`.
- `src/outfitmatch/kb/embedding.py` / `outfit_transformer.py` scaffold OT-labse item embedding.
- `src/outfitmatch/kb/pair_scoring.py` — pair scorer.
- `src/outfitmatch/kb/graph.py` — sparse graph theo category/gender/formality gates.
- `src/outfitmatch/kb/graph_store.py` — persist `item_edges.parquet` + Qdrant `items`.
- `scripts/data/kb/build_graph.py` — graph build CLI.

### Kết quả

- Graph KB trở thành artifact chính.
- Thêm item mới có thể rebuild/incremental graph thay vì regenerate mọi outfit materialized.
- Qdrant dùng cho item seed filtering, không phải source-of-truth outfit KB.

---

## 6. Sprint 3 — Graph Retrieval & Grading ✅

**Goal:** Biến graph KB thành Tầng 3 retrieval chạy được và có metric guard.

### Deliverables chính

- `src/outfitmatch/kb/traversal.py` — clique-safe outfit assembly.
- `src/outfitmatch/kb/assemble_record.py` — assembled items → `OutfitRecord`.
- `src/outfitmatch/retrieval.py` — seed filter (`items`) + traversal + post-filter.
- `src/outfitmatch/metrics/retrieval.py` — graph FITB recall.
- `src/outfitmatch/kb/graph_eval.py` + `scripts/data/kb/eval_graph.py`.

### Kết quả

- Retrieval không còn phụ thuộc `outfits` collection materialized.
- `occasion` conditioning đo qua formality-based seed filter.
- `coherence_violations = 0` là hard regression guard.
- `dress` và `top+bottom` được xem là core hợp lệ; shoes là optional-but-preferred do coverage còn thưa.

---

## 7. Sprint 3.5 / Data Quality Follow-up — Semantic Tagging & Audits ✅

**Goal:** Bổ sung semantic item metadata để graph retrieval có body/season/color conditioning thực tế.

### Deliverables chính

- `src/outfitmatch/kb/tagging.py` — semantic tagging backend, JSON parsing, enum validation, cache.
- `scripts/data/kb/tag_items.py` — CLI writeback vào `catalog_metadata.parquet`.
- `scripts/data/kb/audit_tagging_quality.py` — read-only item tag audit.
- `scripts/data/kb/audit_outfit_tags.py` — read-only derived outfit tag audit.
- `scripts/data/kb/eval_tagging_models.py` và `eval_turboquant_tagging_large.py` — model/backend evaluation tooling.

### Kết quả hiện tại

- `data/reports/tagging_quality/summary.json`: 5,618 total items, 5,618 tagged/non-empty, 0 pending empty, 0 invalid rows.
- `data/reports/outfit_tagging_quality/summary.json`: 824 generated traversal samples, 824 valid cores, 816 complete-with-shoes, 8 shoeless valid cores, 0 invalid rows, 0 high-severity flags.
- Body-conditioning evaluation không còn bị block bởi thiếu item tags; final metric vẫn cần chạy theo `EXPERIMENT_GUIDE.md`.

---

## 8. Roadmap còn lại

| Work item | Trạng thái | Deliverable kỳ vọng |
|---|---|---|
| Qwen3-VL base inference | Planned | implement `stylist/model.py` loading/inference |
| LoRA dataset/training | Planned | implement `stylist/data.py`, synthetic conversation JSONL |
| Tool-calling chat loop | Planned | Qwen calls `search_outfits`, validates IDs/sizes |
| Gradio demo | Planned | product cards, images, prices, store links, feedback |
| API endpoint | Planned | `POST /recommend` if needed for demo/service mode |
| Final eval | Planned | LLM judge, latency, encoder/body/occasion/beam ablations |

---

## 9. Evaluation Targets

| Metric | Target | Phương pháp đo | Status |
|---|---|---|---|
| Recall@5 graph FITB | regression guard ≈ 0.98 | `fitb_recall_at_k` | baseline available |
| Catalog coverage | ≥ 0.60 full-sweep | `GraphReport.catalog_coverage` | baseline available |
| Coherence violations | = 0 | `GraphReport` | baseline available |
| FITB Accuracy | ≥ 55% | OT-labse trên Polyvore | pending final run |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore | pending final run |
| Body-cond. Precision@5 | pending target | graph retrieval with/without body tags | unblocked, pending run |
| E2E Latency | < 5–8s GPU/cloud | runtime benchmark | pending Qwen/UI |
| LLM-as-judge | Mean ≥ 3.5/5 | Gemini judge | pending final outputs |

Required ablations:

1. Encoder variants — OT-labse zero-shot vs fine-tuned Polyvore.
2. Body conditioning on/off — now possible after semantic item tagging.
3. Occasion conditioning on/off — seed filter with/without `formalities_for_occasion`.
4. Greedy vs beam — `AssemblyConfig(beam=1)` vs `beam=3`.

---

## 10. XP Practices Áp dụng

| Practice | Cách áp dụng |
|---|---|
| Test-Driven Development | Unit tests mirror graph/store/retrieval/tagging/scrape modules |
| Continuous Integration | Intended via GitHub Actions on push/PR |
| Small Releases | Scraper, graph build, retrieval, tagging/audits separated into increments |
| Refactoring | Legacy materialized path retained but labeled non-primary |
| Collective Ownership | Docs and feature log define module contracts |
| Coding Standards | `ruff` + `mypy` + `pytest` |

---

## 11. Rủi ro còn lại

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| Qwen3-VL-8B latency/VRAM cao | Cao | 4-bit quantization, GPU/cloud, streaming, fallback deterministic retrieval |
| Chat loop chưa implement | Cao | Tool schema/validation đã sẵn; implement `model.py`/`data.py` theo boundary |
| Shoe coverage thấp | Trung bình | Treat as completion gap; expand catalog/incremental graph |
| Giá/stock stale | Trung bình | Re-run scraper/quality before demo; keep collected dates |
| Body evaluation chưa chốt số | Trung bình | Item tags now available; run ablation per `EXPERIMENT_GUIDE.md` |
| Docs lệch code | Thấp | This update aligns README/ARCHITECTURE/PROJECT_STRUCTURE/SPRINT_REPORT with source state |

---

## 12. Kết luận

Project hiện đã có nền tảng data/graph/retrieval khá hoàn chỉnh cho MVP. Phần còn thiếu lớn nhất
không nằm ở graph KB nữa mà ở **Tầng 2 conversational stylist** và **UI/API demo integration**.
Khi triển khai tiếp, cần giữ nguyên invariant: `vocab.py` là source-of-truth, graph KB là primary
retrieval path, Qdrant `outfits`/materialized outfits chỉ là legacy comparison.
