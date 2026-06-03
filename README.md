# OutfitMatch — AI Stylist v3.1-lite

AI Stylist cá nhân hoá phong cách châu Á cho thị trường Việt Nam.
MVP 3 tháng / 3 dev — kiến trúc 4 tầng được mô tả đầy đủ trong [`Kien_truc_v3.1.md`](Kien_truc_v3.1.md).

```
Tầng 1: Graph KB Builder  OutfitTransformer-labse (frozen) → item embedding → sparse compat graph
Tầng 2: Stylist          Qwen3-VL-8B + LoRA nhẹ (~3-5K hội thoại)
Tầng 3: Retrieval        Qdrant items seed filter + graph traversal ráp clique
Tầng 4: Personalization  Quiz 5 câu → re-rank rule-based
```

## Quick Start

```bash
# 1. Cài đặt (yêu cầu Python 3.13 + uv)
uv sync --group dev

# 2. Khởi động Qdrant
make qdrant-up

# 3. Chạy demo (Sprint 8 trở đi)
make demo
```

## Tài liệu chính

| File | Nội dung |
|---|---|
| [`Kien_truc_v3.1.md`](Kien_truc_v3.1.md) | **Kiến trúc canonical v3.1-lite** — đọc trước khi code |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Module boundaries, schema, interfaces |
| [`docs/EXPERIMENT_GUIDE.md`](docs/EXPERIMENT_GUIDE.md) | Workflow eval cho Sprint 9 (LLM-judge + 4 ablations) |
| [`docs/datasets/STORE_CATALOG_VN.md`](docs/datasets/STORE_CATALOG_VN.md) | Schema catalog VN (scrape thủ công từ store local) |
| [`CLAUDE.md`](CLAUDE.md) | Hướng dẫn cho Claude Code |

## Cấu trúc source

```
src/outfitmatch/
  vocab.py          # Controlled vocabulary — single source of truth
  kb/               # Tầng 1: graph KB (catalog → embedding → graph → traversal)
  retrieval.py      # Tầng 3: seed filter + traversal + post-filter
  stylist/          # Tầng 2: Qwen3-VL-8B + LoRA + tool-calling + validation
  quiz/             # Tầng 4: Onboarding quiz + preference re-rank
  metrics/          # FITB/Compat AUC (Polyvore) + graph FITB recall
  pipeline.py       # E2E orchestrator (RecommendRequest → RecommendResult)
  seeding.py
  ui/               # Gradio demo (Sprint 8)
```

## Team (Sprint 0-9, 10 tuần)

| Vai trò | Owner |
|---|---|
| Dev A — Data/KB (Tầng 1) | Nhật Quang |
| Dev B — Model/Stylist (Tầng 2) | TBD |
| Dev C — Retrieval / Quiz / UI / API (Tầng 3-4) | TBD |
