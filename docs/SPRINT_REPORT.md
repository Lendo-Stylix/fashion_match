# OutfitMatch — Báo cáo Tiến độ Dự án (Scrum/XP)
**DPL302m · Nhóm 3 dev · Timeline: 7 Sprint × 1 tuần**

> **Ghi chú timeline:** Kế hoạch ban đầu là 3 tháng (10 sprint). Sau khi đánh giá lại
> phạm vi MVP và nguồn lực, nhóm rút gọn xuống **7 tuần (7 sprint)** bằng cách
> gộp các sprint KB-build (Sprint 1–2 → 1 sprint) và song song hóa Qdrant với LoRA prep.

---

## Thông tin Dự án

| Mục | Chi tiết |
|---|---|
| **Tên dự án** | OutfitMatch — AI Stylist Cá nhân hóa |
| **Môn học** | DPL302m — Deep Learning Project |
| **Nhóm** | 3 sinh viên (ML Lead + Retrieval Dev + Data/Eval Dev) |
| **Timeline** | 7 tuần (Sprint 1–7), bắt đầu tuần 3 tháng 5/2026 |
| **Branch** | `Model` (feature branch) → merge vào `dev` theo từng Sprint |
| **Repo** | github.com/vominhnhatquang/fashion_match_project |

---

## Kiến trúc Hệ thống (v3.1-lite, 4 tầng)

```
┌─────────────────────────────────────────────────────────┐
│  TẦNG 1 — KB Builder (Offline)                           │
│  OutfitTransformer-labse (frozen)                        │
│  FITB+Beam → 5–20K outfit từ store VN                   │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  TẦNG 2 — Conversational Stylist                         │
│  Qwen3-VL-8B + LoRA (3–5K hội thoại synthetic)          │
│  Parse intent · hỏi lại · tool-calling                  │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  TẦNG 3 — Retrieval Engine (Qdrant)                      │
│  Filter metadata → sort theo compatibility_score         │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  TẦNG 4 — Personalization (Quiz re-rank)                 │
│  Quiz 5 câu → PreferenceProfile → re-rank rule-based     │
└─────────────────────────────────────────────────────────┘
```

**Stack:** Python 3.13 · uv · Qwen3-VL-8B · OutfitTransformer-labse · Qdrant · Gradio · pytest

---

## Tổng quan 7 Sprint

| Sprint | Tuần | Tên | Deliverable chính | Trạng thái |
|--------|------|-----|-------------------|------------|
| 1 | W1 | Foundation & Scaffolding | vocab.py, schema, test suite 35/35 ✅ | **DONE** |
| 2 | W2 | KB Builder — Embedding & Generation | OT-labse embedding, FITB+Beam, random+scored | Planned |
| 3 | W3 | KB Builder — Scoring, Tagging & Qdrant | OT rescore, Gemini tagging, Qdrant index | Planned |
| 4 | W4 | Stylist — LoRA Data & Base Inference | Synthetic convs (3–5K), base Qwen3-VL-8B test | Planned |
| 5 | W5 | Stylist — LoRA Fine-tune & E2E Pipeline | LoRA adapter, pipeline.py E2E hoạt động | Planned |
| 6 | W6 | UI, API & Integration | Gradio demo, /recommend endpoint, E2E smoke test | Planned |
| 7 | W7 | Evaluation, Ablations & Final Report | 4 ablations, LLM-judge, metrics đạt target | Planned |

---

## Sprint 1 — Foundation & Scaffolding ✅ COMPLETED

**Thời gian:** Tuần 1 (W1, 19–24/05/2026)
**Goal:** Xây dựng nền tảng kiến trúc v3.1-lite — controlled vocabulary, schema,
module scaffolding, test suite xanh — để mọi sprint tiếp theo có base sạch.

### User Stories

| ID | Story | Story Points | Trạng thái |
|----|-------|-------------|------------|
| S1-1 | As a dev, I need a single vocab.py as source of truth cho tất cả enum | 3 | ✅ Done |
| S1-2 | As a dev, I need OutfitRecord + ItemRecord schema với to_qdrant_payload() | 3 | ✅ Done |
| S1-3 | As a dev, I need stylist/tools.py với SEARCH_OUTFITS_TOOL dùng vocab enum | 2 | ✅ Done |
| S1-4 | As a dev, I need validation.py chống hallucinate outfit_id | 2 | ✅ Done |
| S1-5 | As a dev, I need quiz/schema.py + rerank.py (QuizAnswers → PreferenceProfile → re-rank) | 3 | ✅ Done |
| S1-6 | As a dev, I need metrics/outfit.py (fitb_accuracy, compatibility_auc) | 1 | ✅ Done |
| S1-7 | As a dev, CI/CD GitHub Actions phải xanh trên mọi push | 2 | ✅ Done |

**Total:** 16 SP · **Velocity Sprint 1:** 16 SP

### Kết quả kỹ thuật

```
Tests:   35 passed / 35 total  (coverage target: ≥70% — đạt)
CI:      GitHub Actions green
Lint:    ruff check + ruff format + mypy — 0 error
```

**Modules fully implemented:**
- `src/outfitmatch/vocab.py` — 7 enum tuples + frozensets + VI labels + `validate_enum_values()`
- `src/outfitmatch/kb/schema.py` — `ItemRecord`, `OutfitRecord`, `to_qdrant_payload()`
- `src/outfitmatch/stylist/tools.py` — `SEARCH_OUTFITS_TOOL` (enum-typed, vocab-synced)
- `src/outfitmatch/stylist/validation.py` — `extract_outfit_ids()`, `validate_response()`
- `src/outfitmatch/quiz/schema.py` — `QuizAnswers`, `PreferenceProfile`, `quiz_to_profile()`
- `src/outfitmatch/quiz/rerank.py` — `score_outfit_for_preference()`, `rerank_by_preference()`
- `src/outfitmatch/metrics/outfit.py` — `fitb_accuracy()`, `compatibility_auc()`

**Modules stubbed (NotImplementedError + Sprint reference):**
- `kb/embedding.py` → Sprint 2
- `kb/generation.py`, `kb/scoring.py`, `kb/tagging.py` → Sprint 2–3
- `kb/qdrant_index.py` → Sprint 3
- `stylist/model.py`, `stylist/data.py` → Sprint 4–5
- `pipeline.py` → Sprint 5

### Retrospective Sprint 1

**Went well:**
- TDD workflow (test → fail → implement → green) giữ scope rõ ràng.
- Codegraph index hoạt động ngay từ đầu, tăng tốc navigation.
- Quyết định dùng `dataclass` thay Pydantic model cho schema — giảm overhead.

**Improvements:**
- Cần thống nhất convention đặt tên outfit_id sớm hơn (`OF_XXXXX` vs `outfit_XXXXX`).
- Thiếu mock Qdrant client trong test setup — cần thêm vào conftest.py Sprint 3.

---

## Sprint 2 — KB Builder: Embedding & Generation

**Thời gian:** Tuần 2 (W2, 26–31/05/2026)
**Goal:** Implement Tầng 1 phần đầu — trích xuất item embedding bằng OT-labse và
sinh outfit candidates bằng FITB+Beam (70%) + random+scored (30%).

### User Stories

| ID | Story | SP |
|----|-------|----|
| S2-1 | As a dev, OT-labse model loads với `trust_remote_code=True`, encode 1 item batch | 5 |
| S2-2 | As a dev, `extract_item_embeddings()` xử lý batch 32 items, trả về list[ItemRecord] với embedding | 5 |
| S2-3 | As a dev, `generate_fitb_beam()` sinh ≥100 outfit candidates từ 50 item mẫu | 8 |
| S2-4 | As a dev, `generate_random_scored()` sinh thêm 30% candidates với OT pre-filter | 5 |
| S2-5 | As a dev, test FITB accuracy ≥ 55% trên Polyvore mini (30 items) | 3 |

**Total:** 26 SP · **Sprint Goal:** Item embedding + outfit generation chạy được trên GPU/CPU

### Definition of Done Sprint 2

- [ ] `kb/embedding.py`: `extract_item_embeddings()` implemented, test coverage ≥70%
- [ ] `kb/generation.py`: cả hai functions implemented, test với 50 item mẫu
- [ ] FITB accuracy ≥ 55% đo được trên tập test nhỏ
- [ ] `uv run make test` xanh
- [ ] PR merged vào `dev` với ≥1 peer review

---

## Sprint 3 — KB Builder: Scoring, Tagging & Qdrant

**Thời gian:** Tuần 3 (W3, 02–07/06/2026)
**Goal:** Hoàn thiện Tầng 1 (OT re-scoring + Gemini tagging) và Tầng 3 (Qdrant indexing).
Sau Sprint này KB VN đầu tiên (100–500 outfit) phải nằm trong Qdrant.

### User Stories

| ID | Story | SP |
|----|-------|----|
| S3-1 | As a dev, `rescore_outfits()` cập nhật compatibility_score cho tất cả candidates | 5 |
| S3-2 | As a dev, score threshold được xác định từ histogram distribution | 3 |
| S3-3 | As a dev, `tag_outfits()` gọi Gemini Flash, validate enum bằng vocab.py, cache với diskcache | 8 |
| S3-4 | As a dev, `create_outfits_collection()` tạo Qdrant collection với payload indexes | 5 |
| S3-5 | As a dev, `upsert_outfits()` index 100+ outfit VN vào Qdrant | 5 |
| S3-6 | As a dev, filter query: occasion=office + body_shape=pear trả về ≥5 kết quả | 3 |

**Total:** 29 SP · **Sprint Goal:** KB 100+ outfit VN có thể query được từ Qdrant

### Milestone: Compatibility AUC ≥ 0.85 (đo lần đầu Sprint 3)

---

## Sprint 4 — Stylist: LoRA Data & Base Inference

**Thời gian:** Tuần 4 (W4, 09–14/06/2026)
**Goal:** Sinh 3–5K hội thoại synthetic bằng Gemini, kiểm tra Qwen3-VL-8B base inference,
chuẩn bị pipeline training.

### User Stories

| ID | Story | SP |
|----|-------|----|
| S4-1 | As a dev, Gemini sinh 3K hội thoại cover 7 conversation types | 8 |
| S4-2 | As a dev, spot-check 5% hội thoại (150 samples) — human review pass | 3 |
| S4-3 | As a dev, `load_conversation_dataset()` tokenize JSONL, trả về HF Dataset | 5 |
| S4-4 | As a dev, Qwen3-VL-8B base model load được trên GPU 8GB (4-bit quantize) | 5 |
| S4-5 | As a dev, base model gọi `search_outfits` tool đúng format trong ≥60% test cases | 5 |

**Total:** 26 SP · **Sprint Goal:** Training data sẵn sàng, base model chạy được

### XP Practice Sprint 4: Pair Programming

Hai dev ngồi cùng nhau khi viết Gemini prompt engineering (S4-1) —
output quality của synthetic data ảnh hưởng trực tiếp đến Sprint 5.

---

## Sprint 5 — Stylist: LoRA Fine-tune & E2E Pipeline

**Thời gian:** Tuần 5 (W5, 16–21/06/2026)
**Goal:** Fine-tune LoRA adapter, wire pipeline.py E2E từ request đến Top-5 outfit
với giải thích tiếng Việt.

### User Stories

| ID | Story | SP |
|----|-------|----|
| S5-1 | As a dev, LoRA fine-tune chạy xong trên GPU, training loss giảm | 8 |
| S5-2 | As a dev, LoRA model gọi `search_outfits` tool đúng ≥80% test cases | 5 |
| S5-3 | As a dev, `pipeline.py` wire: RecommendRequest → Stylist → Qdrant → Quiz re-rank → RecommendResult | 8 |
| S5-4 | As a dev, E2E latency < 8s (GPU) cho 1 request hoàn chỉnh | 5 |
| S5-5 | As a dev, hallucination rate (outfit_id không tồn tại) < 5% | 3 |

**Total:** 29 SP · **Sprint Goal:** E2E pipeline chạy được từ đầu đến cuối

### Milestone: E2E demo lần đầu (internal)

---

## Sprint 6 — UI, API & Integration

**Thời gian:** Tuần 6 (W6, 23–28/06/2026)
**Goal:** Gradio UI chạy được (`make demo`), FastAPI endpoint `/recommend`,
integration testing smoke test toàn bộ luồng.

### User Stories

| ID | Story | SP |
|----|-------|----|
| S6-1 | As a user, tôi có thể nhập text + upload ảnh trên Gradio, thấy Top-3 outfit | 8 |
| S6-2 | As a user, quiz 5 câu hiển thị trước lần recommend đầu tiên | 5 |
| S6-3 | As a dev, `POST /recommend` nhận JSON, trả về RecommendResult trong < 8s | 5 |
| S6-4 | As a dev, Gradio hiển thị giải thích tiếng Việt + link mua kèm theo mỗi outfit | 3 |
| S6-5 | As a dev, smoke test E2E: 10 request ngẫu nhiên, 0 crash | 5 |

**Total:** 26 SP · **Sprint Goal:** Demo được trước giảng viên

---

## Sprint 7 — Evaluation, Ablations & Final Report

**Thời gian:** Tuần 7 (W7, 30/06–05/07/2026)
**Goal:** Chạy đủ 4 ablations bắt buộc, đo tất cả metrics grading, viết báo cáo cuối.

### User Stories

| ID | Story | SP |
|----|-------|----|
| S7-1 | As a researcher, chạy ablation (1): OT-labse zero-shot vs fine-tuned Polyvore | 5 |
| S7-2 | As a researcher, chạy ablation (2): body conditioning on/off (Qdrant filter) | 3 |
| S7-3 | As a researcher, chạy ablation (3): occasion conditioning on/off | 3 |
| S7-4 | As a researcher, chạy ablation (4): greedy vs beam decoding (KB build) | 3 |
| S7-5 | As a researcher, LLM-as-judge (Gemini) chấm 30 conversation → Mean ≥ 3.5/5 | 5 |
| S7-6 | As a team, viết final report PDF nộp giảng viên | 5 |

**Total:** 24 SP · **Sprint Goal:** Tất cả metrics grading đạt target

### Evaluation Targets (Sprint 7)

| Metric | Target | Phương pháp đo |
|--------|--------|----------------|
| FITB Accuracy | ≥ 55% | OT-labse trên Polyvore mini |
| Compatibility AUC | ≥ 0.85 | OT-labse trên Polyvore |
| Recall@5 (Qdrant) | encoder baseline + 5pp | Filter+sort query |
| Body-cond. Precision@5 | +10pp vs non-conditional | Ablation body_shape filter |
| E2E Latency | < 5–8s GPU | Đo trên GPU / cloud |
| LLM-as-judge (Gemini) | Mean ≥ 3.5/5 | Gemini chấm 30 E2E outputs |

---

## Burndown Chart (Kế hoạch)

```
Sprint:  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |
SP Done: | 16  | 26  | 29  | 26  | 29  | 26  | 24  |
Cum SP:  | 16  | 42  | 71  | 97  | 126 | 152 | 176 |
Status:  | ✅  |  ⬜  |  ⬜  |  ⬜  |  ⬜  |  ⬜  |  ⬜  |
```

---

## Phân công Nhóm

| Thành viên | Vai trò | Sprint chủ đạo |
|---|---|---|
| Vo Minh Nhat Quang | ML Lead — Architecture, Stylist, Pipeline | S1, S4, S5, S7 |
| [Dev 2] | Retrieval Dev — KB Builder, Qdrant, Scoring | S2, S3 |
| [Dev 3] | Data/Eval Dev — Dataset, Synthetic convs, Eval | S3, S4, S7 |

---

## XP Practices Áp dụng

| Practice | Cách áp dụng |
|---|---|
| **Test-Driven Development** | Viết test trước (failing), implement đến khi pass — áp dụng mọi sprint |
| **Continuous Integration** | GitHub Actions CI trên mọi push to `Model` branch |
| **Pair Programming** | Sprint 4 (Gemini prompt engineering), Sprint 5 (pipeline wiring) |
| **Small Releases** | Mỗi sprint có deliverable chạy được; không để tích lũy debt |
| **Refactoring** | Sau mỗi sprint review code với `simplify` skill trước khi merge |
| **Collective Ownership** | Mọi module có test — ai cũng có thể sửa nếu test vẫn xanh |
| **Coding Standards** | `ruff` + `mypy` enforce tự động qua pre-commit hook |

---

## Rủi ro & Giảm thiểu

| Rủi ro | Mức độ | Giảm thiểu |
|--------|--------|------------|
| GPU không đủ cho Qwen3-VL-8B | Cao | 4-bit quantize (BnB), fallback Colab A100 free tier |
| Gemini API rate-limit khi sinh 5K hội thoại | Trung bình | diskcache + batch 50 convs/call, retry với backoff |
| Polyvore dataset không có công khai | Thấp | Dùng Polyvore-U (available on HuggingFace) |
| Timeline quá gấp (7 tuần vs 3 tháng) | Cao | Scope MVP cứng: 5–20K outfit VN, 3–5K LoRA convs, no GNN |
| Qdrant Docker không chạy được trên máy dev | Thấp | `docker-compose.yml` đã config, fallback Qdrant Cloud free |

---

*Báo cáo được cập nhật cuối mỗi Sprint Review.*
*Lần cập nhật gần nhất: 24/05/2026 — Sprint 1 COMPLETED.*
