# 01 — Xử lý dữ liệu Fine-tune Stylist Model

**Phạm vi:** Pipeline dữ liệu SFT cho 4 adapter QLoRA (T1/T2/T3/T4)
**Mục tiêu slide:** Giải thích cho giám khảo DL cách nhóm **thu thập → làm sạch → cân bằng → sinh grounded → merge** dữ liệu huấn luyện, và vì sao mỗi bước cần thiết.

---

## 1. Bức tranh tổng thể — 3 nguồn dữ liệu, 3 giai đoạn

```
NGUỒN 1: stylist_knowledge (CSV 40,302 rows)        NGUỒN 2: Catalog VN thật (5,618 items)
   • Kiến thức fashion tiếng Việt (QA)                 • ItemRecord: title_vi, price_vnd, colors,
   • 9 topic: color_analysis, wardrobe_capsule,          store, formality, ...
     fabric_material, body_fit, occasion, ...          • Retrieval runtime: graph traversal,
   • Tự scrape + Gemini sinh synthetic                   Qdrant items collection
            │                                              │
            ▼                                              ▼
   ╔═══════════════════════════╗           ╔═══════════════════════════════╗
   ║ G1: DISTILL               ║           ║ G2: GROUNDED                  ║
   ║ • Quality gate (drop bad) ║           ║ • Scenario bank deterministic ║
   ║ • Topic-balance (sqrt)    ║           ║ • Dialogue draft + judge      ║
   ║ • Near-dedupe family cap  ║           ║ • GPT-OSS teacher rewrite     ║
   ║ • Behavioral synth (1.6K) ║           ║ • Anti-hallucination filter   ║
   ║ → 8,800 rows              ║           ║ → 2,800 rows                  ║
   ╚═══════════════════════════╝           ╚═══════════════════════════════╝
            │                                              │
            └──────────────────┬───────────────────────────┘
                               ▼
                ╔══════════════════════════════╗
                ║ G3: MERGE                    ║
                ║ • Union 2 nguồn              ║
                ║ • Exact dedupe (hash)        ║
                ║ → 11,600 unique rows         ║
                ║ • 1,297,500 Qwen tokens      ║
                ║ • Train 11,252 / Eval 348    ║
                ║   (eval_fraction=0.03)       ║
                ╚══════════════════════════════╝
```

---

## 2. Giai đoạn G1 — Distill: Từ 40K "bẩn" → 8.8K "sắc"

### 2.1 Vấn đề trong raw dataset (40,302 rows)

| # | Vấn đề | Số liệu | Tác động nếu không xử lý |
|---|---|---|---|
| **D1** | **Topic skew nặng** | `color_analysis` 49.87% + `wardrobe_capsule` 31.93% = **81.8%** | Mode collapse về "màu gì hợp", yếu ở occasion/body/season |
| **D2** | **Prompt-style bias** | `first_person` 66.62% | Yếu ở câu how-to/definition/request → tool-call không ổn định |
| **D3** | **Overlong essay** | `long` 10.53%, max 705 từ | Model "viết essay" thay vì trả lời ngắn đúng format |
| **D4** | **Mixed-script artifact** | 1,788 rows (4.44%) có ký tự Cyrillic `серьги`, CJK `thời髦` | Tiếng Việt lẫn ký tự lạ → UX tệ, tokenization nhiễu |
| **D5** | **Prompt echo** | 167 rows (0.41%) lặp lại câu hỏi ở đầu answer | Instruction-following không sắc |
| **D6** | **Near-duplicate family** | 246 families ≥21 rows, 297 families 11–20 rows | Gradient lãng phí cho paraphrase cluster |
| **D7** | **Behavioral supervision mỏng** | Bundle cũ chỉ 12.28% behavioral | Biết kiến thức nhưng không hỏi lại / gọi tool đúng lúc |

### 2.2 Quality Gate (4 rule, thực thi trong `distill_stylist_dataset.py`)

```python
# Pseudocode quality gate
MIXED_SCRIPT_PATTERNS = {
    "cyrillic": re.compile(r"[\u0400-\u04FF]{2,}"),   # серьги, поверх
    "cjk":      re.compile(r"[\u4E00-\u9FFF]{2,}"),   # thời髦
}

for row in raw_rows:
    if has_mixed_script(row.assistant):       drop("mixed_script")
    if word_count(row.assistant) > 280:       drop("too_long")
    if overlap(prompt, first_sentence(answer)) >= 0.65:
                                              drop("question_echo")
```

**Kết quả gate:** loại **4,308 rows (10.69%)**, clean pool còn **35,994 rows**.
- `mixed_script`: 1,788 (41.5% dropped)
- `too_long`: 2,593 (60.2% dropped)
- `question_echo`: 167 (3.9% dropped)

### 2.3 Topic-Balanced Selection (sqrt weighting)

**Vấn đề:** Random sampling → tiếp tục nuôi topic lớn. Hard-balance → ép phân bố thiếu tự nhiên.

**Giải pháp:** chọn quota theo **`sqrt(count)`**:
```python
target_count[topic] = int(K * sqrt(clean_count[topic]))
```
- Topic lớn (color_analysis 18,863) vẫn nhiều mẫu nhưng không áp đảo.
- Topic nhỏ (layering_season 20) được nâng lên đáng kể.

**Kết quả phân phối distilled (7,200 rows):**

| Topic | Raw | Clean pool | **Distilled** | Tỷ lệ distilled/clean |
|---|---:|---:|---:|---:|
| `color_analysis` | 20,100 | 18,863 | **2,723** | 14.4% |
| `wardrobe_capsule` | 12,869 | 10,325 | **1,882** | 18.2% |
| `fabric_material` | 5,102 | 4,729 | **1,458** | 30.8% |
| `body_fit` | 1,727 | 1,616 | **842** | 52.1% |
| `occasion_styling` | 203 | 194 | **134** | 69.1% |
| `general_styling` | 132 | 112 | **71** | 63.4% |
| `shoes_accessories` | 122 | 109 | **58** | 53.2% |
| `care_maintenance` | 26 | 26 | **21** | 80.8% |
| `layering_season` | 21 | 20 | **11** | 55.0% |

→ Topic nhỏ được **oversample** (care_maintenance 80.8%), topic lớn **undersample** (color_analysis 14.4%). Phân bố cân bằng hơn hẳn.

### 2.4 Near-Duplicate Family Cap

**Family key:** 3 content token đầu sau stopword filtering.
**`max_per_family = 3`** → giữ coverage, giảm template repetition.

| Family size | Số family (raw) | Tác động |
|---|---:|---|
| 21+ | 246 | Bị cap mạnh → giảm template lock |
| 11–20 | 297 | Bị cap vừa |
| 6–10 | 567 | Ít ảnh hưởng |
| 1–5 | phần lớn | Giữ nguyên |

### 2.5 Behavioral Synthetic (1,600 rows)

Bundle distilled chỉ có knowledge là chưa đủ — model cần học **hành vi assistant**. Thêm 1,600 rows synthetic phân theo 7 task type:

| Task | Rows | Vai trò dạy model |
|---|---:|---|
| `tool_calling` | 350 | Gọi `<tool_call>search_outfits(...)</tool_call>` đúng schema |
| `recommend_explain` | 300 | Giải thích outfit dựa trên context |
| `ask_missing_info` | 250 | **Hỏi lại** khi thiếu occasion/budget — anti-hallucinate |
| `body_analysis` | 200 | Tư vấn theo dáng người |
| `multi_turn` | 200 | Giữ context hội thoại nhiều lượt |
| `edge_case` | 150 | Tình huống khó (conflict constraint) |
| `polite_decline` | 150 | **Từ chối lịch sự** khi ngoài scope — anti-bịa |

### 2.6 Validation — 5 lớp kiểm tra

| Lớp | Kiểm tra | Kết quả |
|---|---|---|
| **Cấu trúc** | JSONL parse được, `messages` ≥3, manifest khớp line count | ✅ pass |
| **Packaging** | `collect_examples(yaml)` trả đúng `combined_examples` | ✅ 8,800/8,800 |
| **Quality leak** | Final set không còn mixed_script/too_long/echo | ✅ 0/8,800 flagged |
| **Exact dedupe** | Hash full `messages` → 0 duplicate | ✅ 0 dup |
| **Coverage** | Topic coverage 9/9 | ✅ |

**Artifact output:**
```
data/stylist/fine_tune/runs/stylist_distilled_qwen35_under10k/
  ├── knowledge_distilled.jsonl    (7,200 rows)
  ├── behavioral_synthetic.jsonl   (1,600 rows)
  ├── train.jsonl                  (8,800 rows)
  ├── manifest.json
  └── summary.json                 (full stats)
```

---

## 3. Giai đoạn G2 — Grounded: Sinh data từ runtime thật

### 3.1 Vì sao cần Grounded?

**Vấn đề G1:** Knowledge data là fashion advice chung chung → model học "biết thời trang" nhưng chưa học "giống assistant thật" (parse intent → tool params → trả lời dựa trên outfit thật).

**Nguyên tắc (từ `Improving_distilled_dataset_plan.md`):**
> "Model học đúng distribution inference-time. Đây thường là khác biệt lớn nhất giữa 'finetune có vẻ ổn' và 'finetune dùng được'."

### 3.2 Pipeline 4 pha (từ plan `2026-06-23-grounded-stylist-dataset.md`)

#### Phase A — Lock tool-call contract (TRƯỚC TIÊN)
Freeze wire format trong code để training data + inference parsing không drift:
```python
# src/outfitmatch/stylist/tools.py
TOOL_CALL_OPEN  = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
# Rules:
#   - exactly one JSON object inside
#   - name must == "search_outfits"
#   - arguments keys ⊆ schema (occasion required)
#   - enum values ⊆ vocab.py only
#   - price_max: integer VND only
#   - exclude_colors: array of strings only
```

Helper functions: `render_search_outfits_tool_call()`, `parse_tool_call_text()`, `validate_tool_call_payload()`. **Test:** 100% tool-call rows parse đúng, 100% dùng `search_outfits`, 0 unsupported keys.

#### Phase B — Deterministic scenario bank (KHÔNG dùng LLM)
`build_grounded_scenario_bank.py` convert catalog thật → scenario metadata:
```python
def _occasion_seed_items(items, occasion):
    allowed_formalities = formalities_for_occasion(occasion)  # từ vocab.py
    return [it for it in items
            if it.category in {"top","dress"}
            and it.formality in allowed_formalities
            and it.store.get("in_stock")
            and it.store.get("product_url")]
```
→ Sinh **7 task type** với target counts:

| Task | Target | Mô tả |
|---|---:|---|
| `tool_calling_grounded` | 900 | User prompt → tool call đúng field/enum |
| `recommend_explain_grounded` | 700 | Tool trả outfit thật → answer chọn + giải thích |
| `ask_missing_info_grounded` | 350 | Thiếu occasion → hỏi lại |
| `no_result_or_relax_constraints` | 250 | Tool trả 0 outfit → fallback/relax |
| `polite_decline_anti_hallucination` | 150 | User đòi outfit_id giả → decline |
| `multi_turn_grounded` | 150 | Multi-turn với tool |
| `body_fit_grounded` | 300 | Body shape → recommendation |

#### Phase C — Draft + teacher
- Local draft (llama-cpp) hoặc teacher (GPT-OSS / Nemotron) rewrite scenario → ChatML.
- **Luôn import canonical tool rendering từ `tools.py`** → không drift.

#### Phase D — Judge + filter + package
- Deterministic check trước (schema, enum, hallucination).
- GLM Flash bulk judge sau.
- Stratify accepted rows → `train.jsonl` / `eval.jsonl`.

### 3.3 Ưu điểm Grounded vs Knowledge thuần

| Tiêu chí | Knowledge (G1) | Grounded (G2) |
|---|---|---|
| Nguồn | CSV ngoại (scrape/synth) | Catalog + retrieval runtime thật |
| Distribution | Fashion advice chung | Đúng inference-time flow |
| Hallucination risk | Cao (bịa item) | Thấp (item thật có product_url) |
| Tool-call dạy đúng | Yếu | Mạnh (gắn OutfitRecord thật) |
| Reproducibility | Phụ thuộc CSV | Deterministic từ vocab.py + catalog |

---

## 4. Giai đoạn G3 — Merge: 11.6K final dataset

### 4.1 Config merge (`stylist_finetune_kaggle_final_merged.yaml`)
```yaml
dataset:
  source_mode: grounded_bundle
  stylist_knowledge_dir: data/stylist/fine_tune/runs/stylist_grounded_v2/
                          merged_source_gptoss_2800_core8800
  eval_fraction: 0.03
  max_eval_records: 512
  seed: 42
```

### 4.2 System prompt chuẩn (freeze cho cả 4 model)
```
Bạn là AI stylist tiếng Việt của OutfitMatch cho thị trường Việt Nam.
Trả lời ngắn gọn, thực tế, bám catalog thật, hỏi lại khi thiếu thông tin
quan trọng, gọi đúng search_outfits khi cần, không bịa outfit_id, sản phẩm,
giá, size hoặc tình trạng tồn kho.
```

### 4.3 Thống kê final bundle

| Metric | Giá trị |
|---|---|
| Total unique examples | **11,600** |
| Train / Eval split | 11,252 / 348 |
| Tool-call rows (train/eval) | 1,360 / 40 |
| Approx tokens (Qwen) | 1,297,500 |
| Mean assistant words | 94.98 |
| Median assistant words | 81 |
| p90 assistant words | 151 |
| Max assistant words | 280 (capped) |

### 4.4 Task mix final (sau merge)

| Task block | Nguồn | Vai trò |
|---|---|---|
| `stylist_knowledge` | G1 (7,200) | Kiến thức nền thời trang VN |
| `tool_calling` + `tool_calling_grounded` | G1 (350) + G2 (900) | **Core production skill** |
| `recommend_explain` + `_grounded` | G1 (300) + G2 (700) | Giải thích outfit thật |
| `ask_missing_info` + `_grounded` | G1 (250) + G2 (350) | Anti-hallucinate occasion |
| `body_fit_grounded` + `body_analysis` | G2 (300) + G1 (200) | Tư vấn dáng người |
| `polite_decline_anti_hallucination` | G2 (150) | Anti-bịa outfit_id |
| `no_result_or_relax_constraints` | G2 (250) | Fallback khi 0 kết quả |
| `multi_turn` + `_grounded` | G1 (200) + G2 (150) | Hội thoại nhiều lượt |
| `edge_case` | G1 (150) | Tình huống conflict |

---

## 5. ChatML Format chuẩn (training contract)

```json
{
  "messages": [
    {"role": "system", "content": "Bạn là AI stylist tiếng Việt của OutfitMatch..."},
    {"role": "user", "content": "Mình cao 1m60 nặng 55kg, đi đám cưới mùa hè, ngân sách 1 triệu"},
    {"role": "assistant", "content": "<tool_call>{\"name\":\"search_outfits\",\"arguments\":{\"occasion\":\"wedding_guest\",\"body_shape\":\"pear\",\"price_max\":1000000}}</tool_call>"}
  ],
  "task_type": "tool_calling_grounded",
  "source_set": "grounded_bundle"
}
```

**Quy tắc format:**
- ChatML-like, `messages` có ≥3 phần tử (system/user/assistant).
- Tool-call luôn dùng `<tool_call>{JSON}</tool_call>` (KHÔNG markdown fence).
- Enum trong arguments **luôn** từ `vocab.py` (English snake_case nội bộ).
- Tiếng Việt chỉ trong `content` prose, không trong enum value.

---

## 6. Trực quan hóa (Visualization) — đã có sẵn

Trong `docs/reports/stylist_knowledge_qwen35_under10k/` có 5 PNG chart:
1. `topic_distribution_raw_vs_distilled.png` — so sánh phân bố topic trước/sau distill
2. `prompt_style_raw_vs_distilled.png` — prompt style balance
3. `answer_length_hist_raw_vs_distilled.png` — histogram độ dài answer
4. `quality_gate_drops.png` — breakdown rows bị drop
5. `family_size_buckets_raw_vs_distilled.png` — near-dedupe family cap effect

**Gợi ý slide:** dùng các chart này để minh họa trực quan cho giám khảo DL — đặc biệt chart topic distribution (thấy rõ cân bằng) và quality_gate_drops (thấy rõ data cleaning).

---

## 7. Tóm tắt — Vì sao pipeline này tốt cho DL?

| Điểm nhấn DL | Giải thích |
|---|---|
| **Data-centric AI** | Thay vì đổi model, nhóm đầu tư pipeline làm sạch + cân bằng + grounding → đúng triết lý "data quality > model quantity" (Andrew Ng.) |
| **Curriculum implicit** | Merge knowledge (nền) + behavioral (kỹ năng) + grounded (runtime) → 3 tầng học tăng dần |
| **Reproducibility** | Tất cả bước deterministic (seed=42), scenario bank không LLM → chạy lại cho cùng kết quả |
| **Anti-hallucination by design** | Tool-call contract freeze + negative samples `polite_decline` + validation code |
| **Distribution match** | Grounded data sinh từ runtime thật → giảm distribution mismatch (vấn đề kinh điển của SFT) |

---

*Hết báo cáo dữ liệu. Đọc tiếp `02_MODEL_COMPARISON.md`.*
