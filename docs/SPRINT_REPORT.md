# OutfitMatch — Báo cáo Tiến độ Dự án (Scrum/XP)
**DPL302m · Nhóm 3 dev · Timeline mục tiêu: 7 sprint × 1 tuần**

> **Cập nhật kiến trúc:** Knowledge Base của project đã chuyển sang **graph KB**.
> Primary path hiện nay là: **catalog item nodes -> sparse compatibility graph -> Qdrant `items` seed filter -> traversal ráp outfit động**.
> Materialized `generated_outfits.parquet` / Qdrant `outfits` chỉ còn giữ cho legacy comparison.

---

## Thông tin Dự án

| Mục | Chi tiết |
|---|---|
| **Tên dự án** | OutfitMatch — AI Stylist Cá nhân hóa |
| **Môn học** | DPL302m — Deep Learning Project |
| **Nhóm** | 3 sinh viên |
| **Branch** | `Model` → merge vào `dev` theo từng sprint |
| **Repo** | github.com/vominhnhatquang/fashion_match_project |
| **Canonical docs** | `Kien_truc_v3.1.md`, `docs/ARCHITECTURE.md`, `docs/EXPERIMENT_GUIDE.md` |

---

## Kiến trúc Hệ thống (v3.1-lite, 4 tầng)

```text
Tầng 1  Graph KB Builder
        catalog -> item embedding -> pair scoring -> sparse graph -> item_edges.parquet

Tầng 2  Conversational Stylist
        Qwen3-VL-8B + LoRA nhẹ, parse intent, hỏi lại, tool-calling

Tầng 3  Retrieval Engine
        Qdrant `items` seed filter -> graph traversal -> OutfitRecord derived -> Top 30-50

Tầng 4  Personalization
        Quiz 5 câu -> rerank rule-based -> Top 3-5
```

**Stack:** Python 3.13 · uv · Qwen3-VL-8B · OutfitTransformer-labse · Qdrant · Gradio · pytest

---

## Snapshot hiện tại

### Đã hoàn thành

| Sprint | Trọng tâm | Trạng thái |
|---|---|---|
| **S1** | Foundation: vocab, schema, quiz, stylist validation, metrics scaffold | ✅ Done |
| **S2** | Catalog pipeline + graph KB construction (`pair_scoring`, `graph.py`, `graph_store.py`, `build_graph`) | ✅ Done |
| **S3** | Graph retrieval + grading (`traversal`, `assemble_record`, `retrieval.py`, `eval_graph`) | ✅ Done |

### Đang / sẽ làm tiếp

| Sprint | Trọng tâm | Trạng thái |
|---|---|---|
| **S4** | Stylist data + Qwen3-VL base/LoRA prep | Planned |
| **S5** | Pipeline E2E + tool-calling + hallucination guard | Planned |
| **S6** | UI / API / demo integration | Planned |
| **S7** | Evaluation, ablations, final report | Planned |

---

## Kết quả kỹ thuật nổi bật

### Catalog / Scrape

- `5618` catalog items
- `5618` item-store links
- `25/25` manifest batches passed
- `0` hard errors từ catalog quality gate

### Graph KB baseline

- `4694` adult item nodes (`men|women|unisex`)
- `316103` canonical edges trong `data/custom/graph/item_edges.parquet`
- build time ~`27.4s`
- degree min / median / max = `60 / 76 / 2809`

### Retrieval / grading baseline

- `catalog_coverage = 0.7069`
- `coherence_violations = 0`
- `fitb_recall@5 = 0.9813`
- `n_assembled = 7350`
- `item_reuse_p95 = 27`

---

## Sprint 1 — Foundation & Scaffolding ✅

**Goal:** Dựng nền tảng 4 tầng v3.1-lite và controlled vocabulary thống nhất.

### Deliverables chính

- `src/outfitmatch/vocab.py` — enum/source of truth
- `src/outfitmatch/kb/schema.py` — `ItemRecord`, `OutfitRecord`
- `src/outfitmatch/stylist/tools.py` — `SEARCH_OUTFITS_TOOL`
- `src/outfitmatch/stylist/validation.py` — chống hallucinate `outfit_id`
- `src/outfitmatch/quiz/schema.py`, `quiz/rerank.py`, `quiz/sizing.py`
- `src/outfitmatch/metrics/outfit.py`

### Kết quả

- test/lint/typecheck xanh cho scaffold nền
- vocabulary invariant được chốt ở `vocab.py`
- quiz rerank thay thế GNN trong MVP

---

## Sprint 2 — Catalog Pipeline & Graph KB Construction ✅

**Goal:** Chuyển KB từ materialized outfits sang **item-compatibility graph**.

### Deliverables chính

- `scripts/data/scrape/` pipeline hoạt động: scrape, manifest, quarantine, quality gate
- `src/outfitmatch/kb/catalog.py` load catalog chuẩn hoá thành `ItemRecord`
- `src/outfitmatch/kb/embedding.py` / `outfit_transformer.py` scaffold OT-labse item embedding
- `src/outfitmatch/kb/pair_scoring.py` — pair scorer
- `src/outfitmatch/kb/graph.py` — build sparse graph theo category/gender/formality
- `src/outfitmatch/kb/graph_store.py` — persist `item_edges.parquet` + Qdrant `items`
- `scripts/data/kb/build_graph.py` — full / incremental graph build CLI

### Kết quả

- graph KB trở thành **primary artifact** của project
- thêm item mới chỉ cần rebuild/incremental edges thay vì tái materialize toàn bộ outfit
- Qdrant dùng cho **item node filtering**, không còn là nơi lưu KB outfit canonical

---

## Sprint 3 — Graph Retrieval & Grading ✅

**Goal:** Biến graph KB thành Tầng 3 retrieval chạy được và có metric guard.

### Deliverables chính

- `src/outfitmatch/kb/traversal.py` — clique-safe outfit assembly
- `src/outfitmatch/kb/assemble_record.py` — assembled items -> `OutfitRecord`
- `src/outfitmatch/retrieval.py` — seed filter (`items`) + traversal + post-filter
- `src/outfitmatch/metrics/retrieval.py` — graph FITB recall
- `src/outfitmatch/kb/graph_eval.py` + `scripts/data/kb/eval_graph.py`

### Kết quả

- retrieval không còn phụ thuộc `outfits` collection materialized
- `occasion` conditioning đo qua **formality-based seed filter**
- diversity đo bằng `catalog_coverage` thay vì đếm outfit materialized
- `coherence_violations = 0` trở thành hard regression guard

---

## Sprint 4–7 — Roadmap còn lại

| Sprint | Goal | Deliverable chính |
|---|---|---|
| **S4** | Stylist data + base inference | synthetic conversations, Qwen3-VL base test, LoRA dataset |
| **S5** | Pipeline E2E | `RecommendRequest -> search_outfits -> rerank -> validation` |
| **S6** | Demo / API | Gradio UI, `POST /recommend`, smoke test |
| **S7** | Evaluation | LLM-judge + 4 ablations + final report |

### Ghi chú quan trọng cho roadmap

- **Body conditioning ablation** vẫn **pending item semantic tagging**.
- **Encoder ablation** và **Compatibility AUC / FITB accuracy** vẫn đo trên Polyvore, tách khỏi graph build path.
- **Legacy materialized outfits** chỉ giữ để so sánh, không phải deliverable chính.

---

## Evaluation Targets

| Metric | Target | Phương pháp đo |
|---|---|---|
| Recall@5 (graph FITB) | regression guard (baseline full-sweep ≈ 0.98) | `fitb_recall_at_k` |
| Catalog coverage | ≥ 0.60 full-sweep | `GraphReport.catalog_coverage` |
| Coherence violations | = 0 | `GraphReport` |
| FITB Accuracy | ≥ 55% | OT-labse trên Polyvore |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore |
| Body-cond. Precision@5 | PENDING item semantic tagging | follow-up |
| E2E Latency | < 5–8s GPU / cloud | runtime benchmark |
| LLM-as-judge | Mean ≥ 3.5/5 | Gemini judge |

---

## XP Practices Áp dụng

| Practice | Cách áp dụng |
|---|---|
| **Test-Driven Development** | Viết test trước cho graph store / traversal / retrieval / eval harness |
| **Continuous Integration** | GitHub Actions CI trên mọi push |
| **Small Releases** | Tách graph build, retrieval, grading thành các increment độc lập |
| **Refactoring** | Giữ materialized path ở trạng thái legacy, tránh xoá quá sớm trước khi graph ổn định |
| **Collective Ownership** | Module nào cũng có test, artifact/CLI rõ ràng |
| **Coding Standards** | `ruff` + `mypy` + `pytest` |

---

## Rủi ro còn lại

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| Qwen3-VL-8B latency/VRAM cao | Cao | 4-bit quantize, GPU/cloud, streaming |
| Body-conditioning chưa bật được | Trung bình | item semantic tagging follow-up |
| Catalog shoes ít -> traversal reuse cao | Trung bình | tiếp tục mở rộng catalog / incremental graph build |
| Giá/stock stale | Trung bình | scrape quality + collected_date + re-run trước demo |
| Legacy docs / thuyết trình lệch kiến trúc | Thấp | đồng bộ theo graph KB như file này |

---

*Lần cập nhật này phản ánh kiến trúc graph KB hiện tại của repo.*
