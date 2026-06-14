# OutfitMatch — AI Stylist v3.1-lite

AI Stylist cá nhân hoá phong cách châu Á cho thị trường Việt Nam. Kiến trúc hiện tại là **v3.1-lite 4 tầng**, trong đó **graph KB là đường dẫn chính**: catalog item nodes → sparse compatibility graph → Qdrant `items` seed filter → graph traversal ráp outfit động.

```text
Tầng 1: Graph KB Builder  catalog → item tags/embeddings → sparse item-compat graph
Tầng 2: Stylist           Qwen3-VL-8B + LoRA nhẹ + tool-calling (đang planned/stub)
Tầng 3: Retrieval         Qdrant `items` seed filter + graph traversal + post-filter
Tầng 4: Personalization   Quiz 5 câu → preference rerank + size suggestion
```

> Canonical plan: [`Kien_truc_v3.1.md`](Kien_truc_v3.1.md).
> Implementation map + folder report: [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md).

## Trạng thái hiện tại

| Mảng | Trạng thái |
|---|---|
| VN catalog scraper + quality gate | ✅ Hoạt động; 5,618 item/link rows, 25/25 manifest batches passed |
| Item semantic tagging | ✅ Hoạt động; 5,618/5,618 item có tag/non-empty payload; audit có 0 invalid rows |
| Graph KB | ✅ Hoạt động; 4,694 adult nodes, 316,559 canonical edges trong `data/custom/graph/item_edges.parquet` |
| Graph retrieval | ✅ Hoạt động; seed `top/dress` → clique traversal → derived `OutfitRecord` |
| Quiz rerank + size suggestion | ✅ Hoạt động rule-based |
| Pipeline request/result | ✅ Retrieval/rerank path chạy được; phần Qwen explanation còn deferred |
| Qwen3-VL model/data fine-tune | 🚧 Stub/planned trong `src/outfitmatch/stylist/model.py`, `data.py` |
| Gradio demo | 🚧 Placeholder Sprint 8 trong `src/outfitmatch/ui/gradio_app.py` |
| Legacy materialized outfits | 🟡 Giữ để so sánh: `data/custom/outfits/generated_outfits.parquet`, Qdrant `outfits` |

## Quick Start

```bash
# 1. Cài đặt (Python 3.13 + uv)
uv sync --group dev

# 2. Chạy test/lint
make test-fast
make lint

# 3. Khởi động Qdrant khi cần index/filter bằng Qdrant
make qdrant-up

# 4. Demo Gradio (hiện còn placeholder/integration target)
make demo
```

## Data / KB commands hay dùng

```bash
# Scrape smoke test, không ghi parquet/images
uv run python -m scripts.data.scrape.run --store yody_vn --limit 20 --no-images --dry-run

# Build graph KB chính
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.build_graph --no-qdrant

# Đánh giá graph retrieval / ablation nhanh
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office

# Tag semantic item metadata vào catalog parquet
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.tag_items --limit 50

# Audit chất lượng item tags và outfit tags
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.audit_tagging_quality
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.audit_outfit_tags
```

## Tài liệu chính

| File | Nội dung |
|---|---|
| [`Kien_truc_v3.1.md`](Kien_truc_v3.1.md) | Kiến trúc/roadmap canonical v3.1-lite |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Boundaries, data flow, schema, status triển khai |
| [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) | Báo cáo chi tiết folder/project + cách đọc repo |
| [`docs/SPRINT_REPORT.md`](docs/SPRINT_REPORT.md) | Báo cáo tiến độ Scrum/XP và metric snapshot |
| [`docs/EXPERIMENT_GUIDE.md`](docs/EXPERIMENT_GUIDE.md) | Workflow eval Sprint 7/9, LLM-judge, ablations |
| [`docs/datasets/STORE_CATALOG_VN.md`](docs/datasets/STORE_CATALOG_VN.md) | Contract dataset VN catalog |
| [`scripts/data/scrape/README.md`](scripts/data/scrape/README.md) | Hướng dẫn vận hành scraper |

## Cấu trúc source rút gọn

```text
src/outfitmatch/
  vocab.py          # Controlled vocabulary — single source of truth
  kb/               # Tầng 1: catalog/schema/tagging/graph/traversal/eval
  retrieval.py      # Tầng 3: seed filter + traversal + post-filter
  stylist/          # Tầng 2: tool schema + validation implemented; model/data stubs
  quiz/             # Tầng 4: onboarding quiz + rerank + size suggestion
  metrics/          # FITB/Compat AUC + graph FITB recall
  pipeline.py       # RecommendRequest → retrieval/rerank/size suggestion
  ui/               # Gradio demo placeholder
scripts/data/
  scrape/           # VN store scraping + quality gate
  kb/               # Build/tag/audit/eval KB CLIs
tests/              # Mirrors src/scripts domains
```

## Team / ownership

| Vai trò | Owner |
|---|---|
| Dev A — Data/KB (Tầng 1) | Nhật Quang |
| Dev B — Model/Stylist (Tầng 2) | Đình Lộc |
| Dev C — Retrieval / Quiz / UI / API (Tầng 3-4) | Hữu Hoàng |
