# OutfitMatch — Báo cáo Trình bày (R2)

**DPL302m · Nhóm 3 dev · Kiến trúc v3.1-lite (MVP 7 tuần)**

---

## 1. Các phương pháp liên quan được dùng để giải quyết bài toán

### 1.1 Tổng quan bài toán
Xây dựng **AI Stylist cá nhân hóa** cho thị trường Việt Nam: người dùng nhập văn bản + (tùy chọn) ảnh + thông tin quiz onboarding → hệ thống recommend Top 3–5 outfit có giải thích tiếng Việt + link mua tại store VN.

### 1.2 3 Công nghệ AI cốt lõi (giảm từ 4 so với v3.0)

| Công nghệ | Vai trò | Trạng thái MVP |
|-----------|---------|----------------|
| **OutfitTransformer-labse** (frozen) | Knowledge Base Builder — sinh item embedding, chấm điểm compatibility | ✅ Đã tích hợp, dùng frozen cho KB; fine-tune nhẹ Polyvore cho grading |
| **Qwen3-VL-8B + LoRA** | Conversational Stylist — parse intent, hỏi lại, tool-calling, giải thích | 🚧 Stub implemented; LoRA dataset/model loading planned Sprint 6–7 |
| **Qdrant + Graph Traversal** | Retrieval Engine — filter seed item → ráp outfit động theo graph | ✅ Hoàn thiện (primary path) |
| ~~GNN~~ | ~~Personalization~~ | ❌ Hoãn sang Phụ lục A — MVP dùng quiz re-rank rule-based |

### 1.3 Kiến trúc 4 tầng (v3.1-lite)

```
TẦNG 1: GRAPH KB BUILDER (Offline)
  VN catalog → semantic tags + item embeddings
  → pair scoring + graph gates → item_edges.parquet (316,559 edges)

TẦNG 2: CONVERSATIONAL STYLIST
  Qwen3-VL-8B + LoRA nhẹ (3–5K hội thoại synthetic)
  Tool schema + validation guardrails đã implement

TẦNG 3: RETRIEVAL ENGINE
  Qdrant `items` seed filter (top/dress) → clique traversal → derived OutfitRecord

TẦNG 4: PERSONALIZATION
  Quiz 5 câu → PreferenceProfile → rule-based rerank → size suggestion
```

### 1.4 Quyết định kiến trúc quan trọng

| Quyết định | Lý do |
|------------|-------|
| **Graph KB thay vì materialized outfits** | Thêm item mới chỉ cần rebuild graph incrementally; không regenerate 20K outfit |
| **Qdrant chỉ làm seed filter** | Tránh lỗ hổng "query vector → outfit space" chưa định nghĩa của v3.0 |
| **Quiz re-rank thay GNN** | MVP không có user thật → GNN không học được; quiz cold-start deterministic |
| **Controlled vocabulary duy nhất (`vocab.py`)** | Sửa triệt để lỗi v3.0: LLM gán tiếng Việt, tool/Qdrant filter tiếng Anh → 0 kết quả |
| **Shoes = optional core** | Coverage giày còn thưa; outfit `top+bottom` / `dress` vẫn hợp lệ, report `missing_recommended_shoes` |

---

## 2. Hoàn thiện dữ liệu, phân tích, tiền xử lý/làm sạch dữ liệu, visualize

### 2.1 Nguồn dữ liệu (chỉ store VN có nguồn & giá rõ ràng)

| Store | Adapter type | Trạng thái |
|-------|--------------|------------|
| YODY | Sitemap + HTML OG/price fallback | ✅ |
| Canifa | Sitemap + HTML OG/price fallback | ✅ |
| Aristino / Haravan | Sitemap + per-product JSON | ✅ |
| Huelleyrose, Dirtycoins, Rubies | Shopify `/products.json` | ✅ |

**Tổng catalog hiện tại:** 5,618 items / 5,618 item-store links  
**Manifest batches:** 25/25 passed, 0 quarantined

### 2.2 Pipeline thu thập & chất lượng dữ liệu

```
scripts/data/scrape/run.py (crawl)
  → raw cache (per-store JSON/HTML)
  → normalize (category/gender/formality mapping via vocab.py)
  → batch gate (quality.check_frames per chunk)
  → manifest records outcome
  → catalog_metadata.parquet + item_store_links.parquet
  → images downloaded to data/custom/catalog/images/
```

**Quality gates (`scripts/data/scrape/quality.py`):**
- Required Parquet columns, unique `item_id`, valid `ITEM_CATEGORY`
- Non-empty titles, JSON-list colors, existing local images
- Catalog/link join integrity, registered `store_id`, absolute URLs
- Sane prices, sale-price consistency

**Kết quả:** 0 hard errors; 556 rows `empty_description` warning (acceptable — downstream Gemini tagging dùng title/image).

### 2.3 Semantic Item Tagging (Gemini Flash)

`src/outfitmatch/kb/tagging.py` + `scripts/data/kb/tag_items.py`:
- Enum-constrained: `body_shapes_fit` ⊆ `BODY_SHAPE`, `season` ⊆ `SEASON`
- Free-form: `colors`, `stylist_notes_vi`
- `diskcache` để cache LLM calls
- Stage-gate: reject incomplete main-garment payloads, retry note-only outputs

**Audit kết quả (`data/reports/tagging_quality/summary.json`):**
- 5,618/5,618 items tagged/non-empty
- 0 pending empty, 0 invalid rows

### 2.4 Graph KB Construction

```
ItemRecord (5,618) 
  → PairScorer (heuristic + OT adapter) 
  → Graph gates: category + gender + formality (tolerance 1 bậc)
  → Top-K=15 per partner category
  → item_edges.parquet (316,559 canonical edges)
  → Qdrant `items` index (payload: category, gender, formality, price_tier, has_vn_store, in_stock, store_id)
```

**Graph artifact:** 4,694 adult nodes (`men|women|unisex`), 316,559 edges

### 2.5 Visualization / Audit Reports

| Audit | Output | Kết quả |
|-------|--------|---------|
| Item tagging quality | `data/reports/tagging_quality/summary.json` | 5,618 tagged, 0 invalid |
| Outfit tag quality (derived) | `data/reports/outfit_tagging_quality/summary.json` | 824/824 valid cores, 816 complete-with-shoes, 8 shoeless valid, 0 high-severity |
| Graph grading | `scripts.data.kb.eval_graph` stdout | `catalog_coverage=0.7069`, `coherence_violations=0`, `fitb_recall@5=0.9813` |

---

## 3. Chi tiết về kiến trúc mô hình/phương pháp đã sử dụng

### 3.1 Tầng 1: OutfitTransformer-labse (Knowledge Base Builder)

**Checkpoint:** `fkuyumcu/OutfitTransformer-labse` (Hugging Face, `trust_remote_code=True`, kiến trúc `outfit-cir-transformer`)

**Capabilities:** Tag `complementary-item-retrieval` → hỗ trợ FITB/CIR (xác minh Sprint 1)

**Domain shift risk:** Train trên Polyvore (thời trang Tây, en/tr) → điểm compatibility trên item VN mang "gu Tây". **Chấp nhận cho MVP**, ghi nhận hạn chế (Phụ lục A).

**Item Embedding:** Trích xuất 1 lần offline → Parquet. Dimension đọc từ checkpoint config (KHÔNG hardcode 768).

### 3.2 Tầng 1: Graph KB — Pair Scoring & Gating

**PairScorer Protocol** (`kb/pair_scoring.py`): pluggable, hiện dùng `HeuristicPairScorer` (deterministic), sau gắn OT-labse scorer.

**Graph Gates** (`kb/graph.py`):
- Category compatibility: chỉ các cặp hợp lệ (top-bottom, top-shoes, dress-shoes, outerwear-top, ...)
- Gender: cùng gender hoặc unisex
- Formality: span ≤ 1 bậc (`athletic < casual < smart_casual < formal`)

**Sparsification:** Top-K=15 neighbors per partner category → sparse graph.

### 3.3 Tầng 2: Qwen3-VL-8B + LoRA (Conversational Stylist)

**Model:** `Qwen/Qwen3-VL-8B-Instruct` (kiến trúc `qwen3_vl`)

**4 Vai trò:**
1. **Intent Parser:** "Em cao 1m60 nặng 55kg" → `{height:160, weight:55}`
2. **Body Analyzer:** Ảnh → ước lượng `body_shape` thận trọng (ưu tiên height/weight/quiz)
3. **Conversational Agent:** Hỏi lại khi thiếu occasion/budget/style
4. **Outfit Explainer:** Giải thích lý do recommend, cá nhân hóa

**LoRA Fine-tune (Sprint 6–7):**
- 3–5K hội thoại synthetic từ Gemini (7 loại mẫu)
- `r=16, alpha=32, target_modules=[q,k,v,o]_proj, dropout=0.05`
- `Qwen3VLForConditionalGeneration` + `BitsAndBytesConfig` 4-bit (nf4) → ~8GB VRAM

**Tool-calling Schema** (`stylist/tools.py`):
```python
SEARCH_OUTFITS_TOOL = {
  "parameters": {
    "occasion": {"enum": OCCASION},      # từ vocab.py
    "style": {"enum": STYLE},
    "body_shape": {"enum": BODY_SHAPE},
    "skin_tone": {"enum": SKIN_TONE},
    "price_max": {"type": "integer"},
    "exclude_colors": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["occasion"]
}
```

**Validation Layer** (`stylist/validation.py`):
- `extract_outfit_ids()`: regex `OF_\d{5,}`
- `validate_response()`: block hallucinated IDs
- `extract_size_mentions()` + `validate_sizes()`: block size không có trong `sizes_in_stock`

### 3.4 Tầng 3: Retrieval Engine (Graph Traversal)

**`retrieval.py::search_outfits()` flow:**
1. `occasion` → allowed formalities via `formalities_for_occasion()` (vocab.py)
2. Qdrant `items` filter: `category IN (top, dress)`, gender, formality, `in_stock=true`, `has_vn_store=true`
3. Fallback: direct graph scan nếu Qdrant unavailable / test không có seed_ids
4. `traversal.assemble_outfits()`: clique-safe assembly
   - Core hợp lệ: `dress` (+ optional) HOẶC `top + bottom` (+ optional)
   - `shoes/outerwear/bag/accessory`: optional-but-preferred
5. `assemble_record.to_outfit_record()`: derive occasion/style/body/season/color/price
6. Post-filter: style, body_shape, price_max, exclude_colors
7. Sort/dedupe by score → Top-K

### 3.5 Tầng 4: Personalization (Quiz Re-rank)

**Quiz 5 câu** (`quiz/schema.py`):
1. Style yêu thích (multi-select từ `STYLE`)
2. Dịp mặc thường xuyên (multi-select từ `OCCASION`)
3. 3 màu ưa thích (free text → map to vocab colors)
4. Ngân sách (`PRICE_TIER`: budget/mid/premium)
5. Chiều cao + cân nặng → BMI → alpha size suggestion

**Re-rank scoring** (`quiz/rerank.py`):
- Style match: +0.10/hit
- Occasion match: +0.10/hit
- Color match: +0.05/hit
- Wrong price_tier: −0.10

**Size suggestion** (`quiz/sizing.py`):
- Deterministic: `(height_cm, weight_kg, gender)` → alpha size cho top/dress/outerwear
- Intersect với `available_sizes` / `sizes_in_stock` thực tế của item

---

## 4. Chi tiết về quá trình fine-tune/evaluate trên dữ liệu

### 4.1 OutfitTransformer Fine-tune (Polyvore — cho grading metric)

**Mục đích:** Báo cáo FITB Accuracy ≥ 55% & Compatibility AUC ≥ 0.85 (rubric grading)

**Dataset:** Polyvore (public benchmark) — **tách biệt hoàn toàn** với VN catalog

**Protocol:**
```bash
uv run python scripts/ot_eval_polyvore.py \
    --checkpoint fkuyumcu/OutfitTransformer-labse \
    --split test \
    --out docs/experiments/ot_polyvore.csv
```

**Metrics** (`metrics/outfit.py`):
- `fitb_accuracy(preds, labels)`: top-1 accuracy trong candidate set
- `compatibility_auc(scores, labels)`: `sklearn.metrics.roc_auc_score`

**Zero-shot baseline** → nếu chưa đạt target → fine-tune nhẹ trên Polyvore FITB/compat (KHÔNG token `[OCC]`/`[PREF]`).

### 4.2 Qwen3-VL LoRA Fine-tune (Sprint 6–7)

**Data:** 3–5K hội thoại synthetic từ Gemini
- 7 loại mẫu: hỏi lại / phân tích ảnh / recommend+giải thích / từ chối lịch sự / multi-turn / edge case / tool-calling
- Spot-check ~5% thủ công

**Training:**
```python
TrainingArguments(
    eval_strategy="steps",  # KHÔNG dùng evaluation_strategy (deprecated)
    ...
)
```

**W&B Logging** (project: `outfitmatch-v3.1`):
- `train/loss` (step), `eval/loss`, `eval/perplexity` (epoch)
- 1 sample dialog completion mỗi 500 steps

### 4.3 Graph KB Evaluation (Canonical Retrieval Path)

**`scripts.data.kb.eval_graph`** — grading harness cho graph KB:

```bash
# Quick sanity (300 seeds)
uv run python -m scripts.data.kb.eval_graph --seeds 300

# Full-sweep grading baseline
uv run python -m scripts.data.kb.eval_graph --seeds 0 --occasion office
```

**Metrics** (`kb/graph_eval.py::GraphReport`):
- `catalog_coverage`: % item dùng trong ≥1 outfit ráp (target ≥ 0.60)
- `coherence_violations`: edge vi phạm category/gender/formality (**hard = 0**)
- `fitb_recall@5`: mask 1 item, traversal recover top-5 (regression guard ≈ 0.98)
- Degree stats, item reuse p95

**Ablations tích hợp sẵn:**
- Occasion on/off: `--occasion office` vs không
- Greedy vs Beam: `AssemblyConfig(beam=1)` vs `beam=3`

### 4.4 Body Conditioning Ablation (Pending)

**Status:** Item semantic tags (`body_shapes_fit`) đã available (Sprint 3.5), final benchmark chưa chạy. Unblocked — chạy theo `EXPERIMENT_GUIDE.md` Sprint 9.

---

## 5. Các kết quả ban đầu trên tập dữ liệu

### 5.1 Data Artifacts Snapshot

| Artifact | Giá trị |
|----------|---------|
| `catalog_metadata.parquet` | 5,618 rows |
| `item_store_links.parquet` | 5,618 rows |
| `item_edges.parquet` (graph KB) | 316,559 canonical edges |
| Adult graph nodes | 4,694 |
| Legacy `generated_outfits.parquet` | 1,000 materialized outfits |

### 5.2 Graph KB Grading Baseline (Historical Full-Sweep)

| Metric | Giá trị | Target | Status |
|--------|---------|--------|--------|
| `catalog_coverage` | **0.7069** | ≥ 0.60 | ✅ Pass |
| `coherence_violations` | **0** | = 0 (hard) | ✅ Pass |
| `fitb_recall@5` | **0.9813** | Regression guard | ✅ Baseline |
| `n_assembled` | 7,350 | — | — |
| `item_reuse_p95` | 27 | — | — |

### 5.3 Ablation Results (Graph)

| Ablation | `catalog_coverage` | `fitb_recall@5` | Note |
|----------|-------------------|-----------------|------|
| Baseline (beam=3, full) | 0.7069 | 0.9813 | — |
| Occasion filter (office) | 0.3613 | — | Drop ~49% coverage |
| Greedy traversal (beam=1) | 0.6451 | — | Drop ~9% coverage |

### 5.4 Item & Outfit Tagging Quality

| Audit | Total | Valid | Invalid | High-severity |
|-------|-------|-------|---------|---------------|
| Item tagging | 5,618 | 5,618 | 0 | 0 |
| Outfit tagging (derived) | 824 | 824 | 0 | 0 |
| Complete-with-shoes | 824 | 816 | 8 (shoeless valid) | 0 |

### 5.5 Legacy Materialized KB (Comparison)

- 1,000 outfits: 700 FITB-beam / 300 random-scored
- Score range: 0.60–0.98
- 100% valid category rules, 0 mixed-gender, 0 formality-clash
- Price-tier balancing: budget=0.20, mid=0.50, premium=0.30 (hit exact)

### 5.6 Pending Final Evaluations (Sprint 9)

| Metric | Target | Method | Status |
|--------|--------|--------|--------|
| FITB Accuracy (Polyvore) | ≥ 55% | OT-labse eval | ⏳ Pending |
| Compatibility AUC (Polyvore) | ≥ 0.85 | OT-labse eval | ⏳ Pending |
| Body-cond. Precision@5 | +10pp | Graph retrieval ± body tags | ⏳ Unblocked, pending run |
| E2E Latency | < 5–8s GPU/cloud | Runtime benchmark | ⏳ Pending Qwen/UI |
| LLM-as-Judge (Gemini) | Mean ≥ 3.5/5 | E2E output chấm | ⏳ Pending final outputs |

---

## Phụ lục: Mapping vào Rubric Chấm Điểm (R2)

| Tiêu chí R2 | Địa chỉ trong báo cáo |
|-------------|----------------------|
| 1. Các phương pháp liên quan | Phần 1 |
| 2. Hoàn thiện dữ liệu, phân tích, tiền xử lý, visualize | Phần 2 |
| 3. Chi tiết kiến trúc mô hình/phương pháp | Phần 3 |
| 4. Chi tiết fine-tune/evaluate | Phần 4 |
| 5. Các kết quả ban đầu | Phần 5 |

---

*Hết — Báo cáo R2 dựa trên kiến trúc v3.1-lite canonical (`Kien_truc_v3.1.md`, `docs/ARCHITECTURE.md`, `docs/EXPERIMENT_GUIDE.md`, `docs/SPRINT_REPORT.md`, `docs/feature.md`).*