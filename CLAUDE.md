# CLAUDE.md

Hướng dẫn cho Claude Code (claude.ai/code) khi làm việc trong repo này.

## Critical: Đọc trước khi viết code

- **[`Kien_truc_v3.1.md`](Kien_truc_v3.1.md)** — kế hoạch canonical v3.1-lite (4 tầng MVP).
  Đây là nguồn sự thật duy nhất về scope, schema, controlled vocabulary, roadmap 7 tuần.
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — module boundaries, data flow, dataclass schema.
  Đọc trước khi sửa bất kỳ file nào trong `src/`.
- **[`docs/EXPERIMENT_GUIDE.md`](docs/EXPERIMENT_GUIDE.md)** — workflow eval Sprint 7
  (LLM-judge, body-filter ablation, decoding ablation, latency).
- **[`docs/superpowers/plans/`](docs/superpowers/plans/)** — task plans hiện hành cho v3.1.

## Codebase Search — Ưu tiên dùng Codegraph

**Trước khi dùng Grep / Glob / Read để khám phá code, hãy dùng Codegraph trước:**

| Mục tiêu | Tool ưu tiên |
|---|---|
| Khám phá cấu trúc file/folder | `codegraph_files` (thay thế Glob/ls) |
| Tìm symbol, function, class | `codegraph_search` (thay thế Grep) |
| Hiểu flow / "làm thế nào X hoạt động?" | `codegraph_context` (call đầu tiên) |
| Trace call path từ A đến B | `codegraph_trace` |
| Xem caller / callee của function | `codegraph_callers` / `codegraph_callees` |
| Đánh giá tác động khi sửa code | `codegraph_impact` |
| Xem source của 1 symbol | `codegraph_node` |
| Survey nhiều symbol liên quan | `codegraph_explore` |

**Quy tắc:** Dùng `codegraph_context` làm bước đầu tiên cho mọi câu hỏi về kiến trúc
hoặc bug. Chỉ fallback sang Grep/Read khi codegraph không đủ chi tiết cho một đoạn code cụ thể.

> **Không còn kiến trúc 6 layer.** Repo trước đây có Layer 0–5 (Preference / Body / Encoder /
> Vector / Composer / Customization). Toàn bộ scaffolding đó đã bị xóa. Chỉ tồn tại
> 4 tầng v3.1-lite (KB → Stylist → Retrieval → Quiz).

---

## Project Overview

**OutfitMatch** — Body & Occasion-Aware Fashion Recommender (DPL302m, 7 tuần, 3 dev).

Hệ thống multimodal: user gửi text + (tùy chọn) ảnh + thông tin quiz onboarding →
Qwen3-VL parse intent → Qdrant filter seed item → graph traversal ráp outfit →
quiz re-rank → hiển thị Top 3-5 outfit kèm giải thích tiếng Việt + link mua tại store VN.

## Python & Package Manager

- **Python 3.13** (xem `.python-version`)
- **Package manager: `uv`** (không dùng pip trực tiếp)

## Commands

```bash
# Setup
uv sync                          # cài deps production
uv sync --group dev              # + dev deps + pre-commit

# Development
make demo                        # Gradio UI (Sprint 8 trở đi)
make qdrant-up                   # khởi động Qdrant container

# Quality
make test                        # pytest + coverage
make lint                        # ruff check + ruff format --check + mypy
make format                      # ruff format + ruff check --fix

# Chạy 1 test file
uv run pytest tests/test_vocab.py -v

# Chạy 1 test function
uv run pytest tests/test_quiz.py::test_quiz_to_profile -v
```

## Source Layout

```
src/outfitmatch/
  vocab.py            # Controlled vocabulary — single source of truth for ALL enums
  kb/                 # Graph KB + legacy materialized generators
    schema.py           # ItemRecord + OutfitRecord (schema_version="3.1")
    catalog.py          # Load scraped catalog rows thành ItemRecord
    embedding.py        # OT-labse item embedding extraction (Sprint 1-2)
    graph.py            # Sparse item-compatibility graph builder
    graph_store.py      # item_edges.parquet + Qdrant `items` node index
    traversal.py        # Clique-safe outfit assembly from seed items
    assemble_record.py  # Derive OutfitRecord tags from assembled graph items
    graph_eval.py       # GraphReport (coverage/coherence/reuse)
    generation.py       # Legacy materialized outfit generation helpers
    scoring.py          # Heuristic/OT scoring helpers
    tagging.py          # Gemini Flash metadata tagging với enum validation
    qdrant_index.py     # Legacy `outfits` collection indexer for materialized outfits
  stylist/            # Tầng 2: Qwen3-VL-8B + LoRA conversational stylist
    tools.py            # SEARCH_OUTFITS_TOOL với enum-typed params (vocab.py)
    validation.py       # extract_outfit_ids + validate_response (chống hallucination)
    model.py            # Qwen3VLForConditionalGeneration + LoRA loading (Sprint 6-7)
    data.py             # Conversation dataset cho LoRA fine-tune (Sprint 6-7)
  quiz/               # Tầng 4: Onboarding quiz + preference re-rank
    schema.py           # QuizAnswers + PreferenceProfile + quiz_to_profile
    rerank.py           # score_outfit_for_preference + rerank_by_preference
  metrics/
    outfit.py           # FITB accuracy + Compatibility AUC trên Polyvore
    retrieval.py        # Recall@K + graph-native FITB recall@K
  retrieval.py       # Tầng 3 seed filter + traversal + post-filter
  pipeline.py        # E2E RecommendRequest → RecommendResult
  seeding.py
  ui/                # Gradio demo (Sprint 8)

tests/               # Mirror cấu trúc src/, mỗi v3.1 module một file test
docs/                # ARCHITECTURE.md, EXPERIMENT_GUIDE.md, datasets/, superpowers/plans/
```

## Architecture (v3.1-lite, 4 tầng) — xem `docs/ARCHITECTURE.md`

1. **Tầng 1 — KB Builder.** OT-labse (frozen) sinh embedding & chấm điểm compatibility.
   FITB+Beam tạo outfit "chuẩn mực" (70%); random+score tạo outfit "phá cách" (30%).
   Gemini Flash gán nhãn `occasion` / `style` / `body_shapes_fit` / `season` —
   PHẢI validate giá trị enum bằng `vocab.py` trước khi ghi vào KB.

2. **Tầng 2 — Stylist.** Qwen3-VL-8B + LoRA nhẹ (3-5K hội thoại synthetic). Parse intent,
   hỏi lại khi thiếu info, gọi `search_outfits` tool (enum-typed params từ `vocab.py`),
   validate `outfit_id` trước khi hiển thị (chống hallucinate).

3. **Tầng 3 — Retrieval.** Qdrant `items` collection filter **seed item** (`top` / `dress`)
   theo gender / formality(→occasion) / in_stock / has_vn_store, rồi graph traversal ráp
   outfit là clique; `style`, `price_max`, `exclude_colors` được post-filter trên
   `OutfitRecord` đã dẫn xuất — **không vector search mơ hồ**.

4. **Tầng 4 — Personalization.** Quiz 5 câu (style / occasions / colors / budget /
   height-weight) → `PreferenceProfile` → re-rank rule-based:
   style/color/occasion match → boost, sai price_tier → penalty.

## Controlled Vocabulary — invariant cốt lõi

`src/outfitmatch/vocab.py` là nguồn enum duy nhất cho cả 3 nơi:
1. Gemini LLM-tagging prompt khi build KB.
2. `search_outfits` tool parameters của Qwen3-VL.
3. Qdrant payload index field values.

Giá trị nội bộ **luôn là English snake_case**. Tiếng Việt chỉ xuất hiện trong
`*_LABELS_VI` (UI) và `*_vi` field (schema display). Tuyệt đối không đổi tên
một enum value đã dùng — sẽ vỡ KB cũ.

## API Endpoints (Sprint 8 trở đi)

- `POST /recommend` — `{occasion, height_cm?, weight_kg?, style?, image_path?, quiz_answers?, …}`
  → `RecommendResult` (outfits + Vietnamese explanation + latency).

## Python 3.13 Compatibility Constraints

| Không dùng | Dùng thay |
|---|---|
| `mediapipe` (không có cp313 wheel) | _(không cần — v3.1 không pose-extract)_ |
| `faiss-cpu` pip (không có cp313 wheel) | `qdrant-client` + Docker |
| `black` / `flake8` / `isort` | `ruff` |
| `flask` | `fastapi` + `uvicorn` |
| `streamlit` | `gradio` |
| `AutoModelForCausalLM` cho Qwen3-VL | `Qwen3VLForConditionalGeneration` |
| `evaluation_strategy` trong TrainingArguments | `eval_strategy` (tên mới) |

## Tooling

- **Linter/formatter:** `ruff` (`py313`, line-length 100, rules E/F/I/UP/B/SIM)
- **Type checker:** `mypy` (non-strict, `ignore_missing_imports=true`)
- **Tests:** `pytest` + `pytest-asyncio`; coverage target ≥ 70%
- **Experiment tracking:** Weights & Biases (`wandb`) — chỉ dùng cho LoRA fine-tune logs
- **LLM tagging:** Gemini Flash via `google-generativeai` + `diskcache` để cache call

## Dataset

Dataset catalog VN sẽ được **scrape thủ công** từ các store local VN có nguồn & giá rõ ràng
(YODY, Canifa, Format, The Blues, Libé, Elise, Owen, HNOSS, Uniqlo VN, Zara VN, H&M VN).
Schema: `docs/datasets/STORE_CATALOG_VN.md`.

Ba luồng data **độc lập** (`Kien_truc_v3.1.md` §3.3):
- **KB catalog**: chỉ store VN — phục vụ recommendation cuối cùng.
- **OT grading eval**: Polyvore (public benchmark) — chỉ dùng để báo cáo FITB acc + Compat AUC.
- **Stylist LoRA training**: hội thoại synthetic sinh bằng Gemini.

Mỗi lần thay đổi dataset trong folder `@data`, cần cập nhật lại hf repo Nhat-Quang/VN_Fashion_data

## Git Workflow — COMMIT & PUSH SAU MỖI THAY ĐỔI

**SAU MỖI LẦN SỬA FILE, PHẢI THỰC HIỆN ĐẦY ĐỦ CÁC BƯỚC SAU:**

```bash
# 1. Kiểm tra trạng thái
git status

# 2. Stage tất cả thay đổi (code + docs + data)
git add -A

# 3. Commit với message tiếng Việt ngắn gọn (≤72 ký tự)
git commit -m "feat: mô tả ngắn gọn thay đổi"
# hoặc: git commit -m "fix: sửa lỗi X"
# hoặc: git commit -m "docs: cập nhật document Y"

# 4. Push lên GitHub remote
git push origin Model
```

**Quy tắc commit:**
- Prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Message tiếng Việt, ngắn gọn, mô tả đúng thay đổi
- Mỗi task hoàn thành = 1 commit riêng
- Push ngay sau commit để tránh mất code

## Hugging Face Dataset Sync

**Mỗi lần thay đổi dataset trong thư mục `data/`, cần push lên HF repo `Nhat-Quang/VN_Fashion_data`:**

> **Lưu ý:** CLI đã đổi từ `huggingface-cli` → `hf`. Dùng `hf` cho mọi thao tác.

```bash
# 1. Login nếu chưa đăng nhập
hf auth login

# 2. Download dataset hiện tại từ HF (để sync)
hf download Nhat-Quang/VN_Fashion_data --repo-type dataset --local-dir data/hf_sync/

# 3. Copy data mới vào folder HF sync
cp data/custom/catalog/*.parquet data/hf_sync/catalog/
cp data/custom/outfits/*.parquet data/hf_sync/outfits/ 2>/dev/null || true

# 4. Upload lên HF
hf upload Nhat-Quang/VN_Fashion_data data/hf_sync --repo-type dataset --commit-message "$(date +%Y-%m-%d): mô tả thay đổi"
```

**Khi code trong `src/` hoặc `scripts/` thay đổi:** không cần push HF dataset (chỉ push HF dataset khi data thay đổi).

## Branch & Definition of Done

Branch hiện tại: `main` (đang phát triển v3.1-lite).
Branch policy: `main` (protected) → `dev` → `feature/<name>`.

Feature **done** khi:
1. `git add -A && git commit -m "..." && git push origin Model` đã chạy.
2. PR merged to `dev` với ≥ 1 peer review.
3. `pytest` coverage ≥ 70% cho module đụng tới, CI (GitHub Actions) xanh.
4. Có docstring trên public functions + entry trong `docs/feature.md`.
5. Reproducible E2E qua `make demo`.
6. Nếu data thay đổi: đã push lên HF repo `Nhat-Quang/VN_Fashion_data`.

## Evaluation Targets (Sprint 9 grading)

| Metric | Target | Cách đo |
|---|---|---|
| Recall@5 (graph FITB) | baseline full-sweep hiện tại ≈ 0.98; dùng làm regression guard | `fitb_recall_at_k` mask 1 item, traversal recover top-5 |
| Catalog coverage (diversity) | ≥ 0.60 full-sweep (`--seeds 0`) | `GraphReport.catalog_coverage` — % item dùng trong ≥1 outfit ráp |
| Coherence violations | = 0 (hard) | `GraphReport` — edge vi phạm category/gender/formality |
| FITB accuracy | ≥ 55% | OT-labse trên Polyvore (`Kien_truc_v3.1.md` §3.6) |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore |
| Body-cond. Precision@5 | PENDING item semantic tagging | Chưa đo được cho graph MVP vì node chưa có body-fit tag |
| E2E latency | < 5–8s GPU / cloud (streaming) | Đo trên GPU — chốt số mục tiêu Sprint 0 |
| LLM-as-judge (Gemini) | Mean ≥ 3.5 / 5 | Gemini chấm output E2E |

4 ablations bắt buộc (`Kien_truc_v3.1.md` §8):
(1) encoder variants — OT-labse zero-shot vs OT-labse fine-tuned Polyvore;
(2) body conditioning on/off — **PENDING item semantic tagging**;
(3) occasion conditioning on/off — seed-filter có/không `formalities_for_occasion` (`eval_graph`);
(4) greedy vs beam — `AssemblyConfig(beam=1)` vs `beam=3` (`eval_graph`).
