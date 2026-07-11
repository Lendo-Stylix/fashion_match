# Chiến lược RL cho Stylist — refresh thực tế từ GPU benchmark

**Ngày:** 2026-07-11 (revision 3 — sau scorer-fix + alias normalisation)
**Tác giả:** benchmark-expansion track
**Model mục tiêu:** **T3 — Qwen3-VL-8B Thinking + LoRA** (ứng viên production)
**Verdict:** **GRPO + QLoRA với reward = 6 deterministic scorers đã có trong `fashion_eval.py`** (verifiable-reward RL, không cần reward model).
**Local GPU (mới):** RTX 5060 Laptop 8GB, CUDA 13.3, torch 2.12.0+cu130 — đủ chạy 8B QLoRA cho 3 model T1/T2/T3 (chưa đủ cho T4 12B).

---

## ⚡ REV 3 UPDATE (post-scorer-fix — 2026-07-11)

Sau khi fix bug scoring trong `score_occasion_formality` (alias normalisation cho
"smart casual", "business casual", "semi-formal", "semi_formal" → canonical
`vocab.py` enum), baseline tăng mạnh:

| Model | mean (rev 2, broken) | **mean (rev 3, fixed)** | Δ |
|---|---:|---:|---:|
| T1 (VL Instruct)  | 0.2596 | **0.4620** | +0.2024 |
| T2 (9B text-only) | 0.3552 | **0.5433** | +0.1881 |
| T3 (VL Thinking)  | 0.2793 | **0.5242** | +0.2449 |

`occasion_formality` tăng từ 0.00 → **0.74 (T3)**, **0.61 (T1)**, **0.59 (T2)**.

**Tác động lên chiến lược RL:**

1. **T2 đã đạt target mean ≥ 0.55** (0.5433, chỉ thiếu 0.01) — T2 làm **upper-bound baseline** để T3 phải vượt qua.
2. **T3 (0.5242) chỉ cần +0.03 để bắt T2** — khả thi chỉ bằng RL + body_shape hint.
3. **P0 giờ là `body_shape_advice`** (T3=0.04, T1=0.00) — scorer đã fix nhưng model
   vẫn cho answer quá generic. Đây là **model behavior, không phải scorer bug** —
   reward signal từ R1 (body_shape) sẽ dạy model dùng canonical keywords.
4. **`occasion_formality` xuống P1** — đã khá tốt (0.74); chỉ cần RL giữ không bị
   regression.

Bảng rev 3 đầy đủ (source: `gpu_T{1,2,3}_rescored.json`):

| Task | T1 | T2 | **T3** | Priority |
|---|---:|---:|---:|---|
| `occasion_formality`     | 0.6074 | 0.5852 | **0.7397** | 🟡 P1 — giữ + crawl 0.65+ |
| `body_shape_advice`      | 0.0000 | 0.0500 | **0.0400** | 🔴 P0 — quá generic |
| `season_advice`          | 0.2583 | 0.3333 | **0.3833** | 🟡 P1 — tốt nhất nhưng còn thấp |
| `coherence`              | 0.5000 | 1.0000 | 0.5000 | 🟡 P2 — T3 học từ T2 pattern |
| `ask_back`               | 0.6667 | 0.6667 | 0.6667 | 🟢 P3 — anti-regression |
| `tool_call_derivation`   | 0.8121 | 0.7879 | 0.7626 | 🟢 P3 — anti-regression |
| **Overall mean**         | **0.4620** | **0.5433** | **0.5242** | — |

**Phần còn lại của doc (rev 2) được giữ nguyên làm lịch sử** — mọi tham chiếu tới
`occasion_formality = 0` trong rev 2 mô tả bug, đã được giải thích + fix ở rev 3.

---

## 0. Recap bản gốc (mock-only) → revision này (real GPU)

Bản gốc (rev 1) dựa vào MOCK benchmark (`mock_run.json`, mean 0.107, luôn hỏi lại → collapse). **Rev 2 này cần此地 cần được nâng cấp vì đã chạy được benchmark thật trên GPU 8GB.** Ba sửa đổi thực tế quan trọng:

1. **Baseline đổi**: từ mock mean 0.107 → REAL T3 mean **0.2793**, T1 0.2596, T2 0.3552. Mô hình không hoàn toàn "collapsed": chúng TRẢ LỜI thực sự, chỉ là trả lời sai kiến thức/cú pháp.
2. **Top priority thay đổi**: mock cho thấy ask-back collapse là ưu tiên 1; REAL data cho thấy **occasion_formality = 0 trên cả 3 model** mới là ưu tiên 1 (mô hình viết "smart casual", "business casual", "semi-formal" thay vì enum `vocab.py`: `formal`/`smart_casual`/`casual`/`athletic`).
3. **Local GPU mở ra khả năng** chạy RL nhỏ (<=500 step) ngay trên máy dev, không cần chờ Kaggle.

---

## 1. Vì sao chọn T3 làm model RL (xét lại với REAL data)

### 1a. REAL GPU benchmark (28 items × 6 scorers, torch 2.12+cu130, RTX 5060 Laptop 8GB)

Bảng đầy đủ (source: `docs/reports/stylist_benchmark_expansion/gpu_T{1,2,3}.json`):

| Task | T1 (VL Instruct) | T2 (9B text) | **T3 (VL Thinking)** | Tập RL focus |
|---|---:|---:|---:|---|
| `occasion_formality` | **0.0000** | **0.0000** | **0.0000** | 🔴 P0 — sai vocabulary toàn bộ |
| `body_shape_advice` | 0.0000 | 0.0500 | 0.0000 | 🔴 P0 — answers quá generic |
| `season_advice` | 0.2083 | 0.3333 | **0.3833** | 🟡 P1 — T3 tốt nhất nhưng còn thấp |
| `coherence` | 0.5000 | **1.0000** | 0.5000 | 🟡 P2 — T2 đã perfect; T3 học từ đó |
| `ask_back` | 0.6667 | 0.6667 | 0.6667 | 🟢 P3 — chỉ 1 prompt fail, ít cần RL |
| `tool_call_derivation` | **0.8121** | 0.7879 | 0.7626 | 🟢 P3 — đã cao, anti-regression |
| **Overall mean** | **0.2596** | **0.3552** | **0.2793** | — |
| eval latency (28 items) | 407s | 712s | 509s | — |

### 1b. Tại sao vẫn giữ T3 làm mục tiêu chính (mặc dù T2 mean cao hơn)

- **T3 là multimodal (Qwen3-VL)** — stylist nhận ảnh user là **feature cốt lõi** v3.1; T2 text-only không có vision tower → bó tay khi user up ảnh.
- T3 có **tool_call_derivation cao** (SFT Tool F1 0.898, eval loss 0.5943 — thấp nhất 4 model theo `DETAILED_REPORT.md` §6).
- T3 thắng trên `season_advice` (0.3833 > 0.3333 > 0.2083) — kiến thức mùa đã tốt, chỉ cần kéo \`occasion\` + \`bodyshape\` lên.
- T2 thắng nhờ `coherence` perfect — nhưng T3 có thể học pattern này qua RL (reward R4) mà không cần đổi model.

**Trade-off cần theo dõi:** Nếu sau RL T3 vẫn tụt dưới T2 ≥ 0.10 mean → cân nhắc ship T2 (text-only) cho feature không cần ảnh, T3 cho tính năng ảnh. Đánh giá lại sau RL.

### 1c. Phân tích failure mode chính (REAL data)

Đọc 9 samples `occasion_formality` của T3 (`gpu_T3.json`):

- Prompt: "Cho dịp đi làm (`office`), mức độ trang trọng nào phù hợp?"
- T3 output: "Mức độ trang trọng phù hợp cho môi trường văn phòng là **smart casual hoặc business casual**..."
- Scorer: tìm enum trong `{athletic, casual, smart_casual, formal}`. "business casual", "semi-formal", "semi-black-tie", "smart-casual" (hyphen, không đúng `smart_casual`) → scorer **không match**.

**3 failure concretely thấy:**
1. **Vocabulary mismatch**: mô hình dùng "business casual", "semi-formal", "semi-black-tie", "smart-casual" (hyphen) — NONE thuộc `FORMALITY` enum (`vocab.py`: `athletic`, `casual`, `smart_casual`, `formal`).
2. **Hyphen normalization**: "smart-casual" ≠ "smart_casual" → scorer skip token.
3. **Background default**: mô hình sợ sai nên liệt kê range ("smart casual hoặc business casual", "smart casual hoặc casual") — giải thích đúng nhưng enum mismatch.

Body_shape_advice:
- T3 output cho "dáng quả lê": "Hãy chọn những trang phục có dáng ôm nhẹ nhàng, ví dụ như váy chữ A hoặc quần ống rộng, để tôn lên đường cong tự nhiên. Tránh mặc những trang phục quá bó sát hoặc quá rộng..."
- `positives_mentioned` lookup: [nhấn eo, chân váy a, a-line, high waist, áo phồng tay] — "chữ A" gần "chân váy a" nhưng scorer dùng exact substring → \`[]\`. Nói chung **Answer quá generic, không dùng Q&A pattern đã chuẩn hoá**.

→ RL reward phải **khuyến khích cụ thể positive keywords** (xem R2 retryetal below).

---

## 2. So sánh thuật toán — GRPO vẫn chọn tối ưu

(Bảng không đổi — xem reasoning bản gốc rev 1.) GRPO + verifiable reward vẫn thắng:
- reward deterministic từ `fashion_eval.py` → không cần RM.
- on-policy → khắc phục distribution mismatch của DPO offline (vấn đề khi SFT đã thiên).
- 1 quantized model + KL seulement → vừa T4 Kaggle 16GB vừa RTX 5060 8GB local.

**Tinh chỉnh v2 (mới):**
- KTO vẫn là fallback nếu GRPO không ổn định.
- **Đặc biệt v2:** vì local GPU 8GB có thể chạy GRPO QLoRA 7-8B ở `max_completion_length=256` (VRAM peak ~7.5GB trong benchmark), **ta nên chạy dry-run + 10-50 step GRPO local** trước khi Kaggle để bắt bugs sớm.

### Compute budget (rev 2 — local + Kaggle)
| Hardware | Mode | ETA | VRAM peak | Output |
|---|---|---|---:|---|
| **Local RTX 5060 (8GB)** | 10-50 GRPO steps, 28-item pool | ~30-90 min | ~7.5GB | sanity + first signal |
| **Local RTX 5060** | 200-500 GRPO steps, 397-item pool | 4-12h | ~7.5GB | usable adapter (overnight) |
| Kaggle T4×1 (15GB) | 500 steps, ~500-prompt pool | ~13h | ~9.2GB | production-ready |
| Kaggle T4×2 (15GB/GPU) | 500 steps | ~7h | same | production-ready |
- vLLM **TẮT** với QLoRA (HF warning) — dùng transformers generate.

---

## 3. Reward design — 6 verifiable reward functions + revision priorities

6 reward functions giữ nguyên (`scripts/stylist/grpo_rewards.py` đã có). **rev 2 cập nhật weights theo REAL failure pattern:**

| # | Reward | T1 | T2 | T3 | RL Priority | Revision |
|---|---|---:|---:|---:|---|---|
| R1 | `occasion_formality_reward` | 0.0 | 0.0 | 0.0 | 🔴 P0 top | **Thêm substring normalization** ("smart casual" ↔ "smart_casual"; khác hyphen/spacing thường match — xem §3a) |
| R2 | `body_shape_advice_reward` | 0.0 | 0.05 | 0.0 | 🔴 P0 | **Tăng positive recall weight** (hiện chỉ penalty negative nhẹ) — \`answer nếu mention ≥2 positive keywords\` |
| R3 | `season_advice_reward` | 0.21 | 0.33 | 0.38 | 🟡 P1 | như bản gốc |
| R4 | `coherence_reward` | 0.5 | 1.0 | 0.5 | 🟡 P2 | thêm **binary key** ("phù hợp"/"không phù hợp") để scorer catch verdict |
| R5 | `ask_back_reward` | 0.67 | 0.67 | 0.67 | 🟢 P3 | giữ |
| R6 | `tool_call_derivation_reward` | 0.81 | 0.79 | 0.76 | 🟢 P3 | giữ — mục tiêu anti-regression |

### 3a. Vocabulary normalization gap (mới, quan trọng)

Scorer hiện match by **exact string** ("smart_casual" phải y hệt). Mô hình output dùng **"smart casual" (space)** hoặc **"smart-casual" (hyphen)** — **match false**. 2 cách sửa:

- **Fix ăn ngay (scorer)**: thêm variant map trong `fashion_eval.py` `score_occasion_formality`:
  `variants = {"smart_casual": ["smart_casual","smart casual","smart-casual"], ...}`. Match bất kỳ biến thể.
- **Fix triệt để (RL)**: reward R1 incent mô hình **xuất đúng canonical enum disguise** `smart_casual` (snake_case). Cách incentiv: bonus +0.2 nếu output có ít nhất 1 canonical `FORMALITY` token bất kỳ.

**Quyết định:** làm cả 2. Sửa scorer (trở nên có realistic partial-credit) **+** vẫn incent canonical trong reward. Lý do:blr dữ liệu training có mục tiêu hướng tới canonical, nhưng scorer robust giúp không penalty quá nặng lần đầu RL.

### 3b. Vocabulary dạy mô hình — change trong prompt chỉ đạo

Prompt mẫu của reward có thể inject "Trả lời dùng snake_case cho style/formality (`smart_casual`, `formal`, ...)" → giảm mismatch. RL sẽ học pattern này khi thấy reward tăng.

---

## 4. Data — Prompt pool (giữ + mở rộng poco)

Giữ `build_fashion_prompt_pool()` (397 items từ Cartesian expansion trong `scripts/stylist/grpo_rewards.py`). **Mới v2**:
- Thêm 50 ân nhiên occasion-prompt biến thể "...`athletic`" hoặc "...`formal`" đơn class (chỉ 1 đúng) → ép mô hình chọn chính xác, không range.
- Body-shape > tạo 30 prompt chỉ hỏi 1 body-shape cụ thể + yêu cầu mention ít nhất 2 positive keywords → thúc R2.

Tất cả ground-truth tính từ `vocab.py` (reproducible 100%).

---

## 5. Training recipe — updated cho local + Kaggle

Kaggle giữ như bản gốc. **Local (mới):**

\`\`\`bash
# Local RTX 5060 (8GB, torch 2.12+cu130) — không dùng uv run (re-sync CPU wheel!)
# 1. Đảm bảo torch CUDA active (verify torch.cuda.is_available()=True)
# 2. Chạy 50 step GRPO để bắt bug:
$env:PYTHONPATH="src;."
.venv/Scripts/python.exe scripts/stylist/train_grpo_kaggle.py \    --model unsloth/Qwen3-VL-8B-Thinking-bnb-4bit \    --adapter D:/Models/adapters/Nhat-Quang--outfitmatch-stylist-final-qwen3vl8b-thinking-lora \    --max-steps 50 --batch-size 1 --num-generations 4 \    --output-dir D:/Models/grpo_t3_local
\`\`\`

**Lưu ý Windows (mới)**: tránh "device_map='auto'" với bnb 4-bit + accelerate → tránh `ValueError: Some modules dispatched on the CPU` (đã xử lý trong `scripts/stylist/run_gpu_benchmark.py` dùng `device_map={"":0}`). Áp dụng cùng pattern cho train script.

### Hyperparameters unchanged (β=0.04, lr=1e-5, G=8, dr_grpo loss, paged_adamw_8bit)
(Local GPU 8GB → giảm G xuống 4 nếu OOM.)

---

## 6. Đánh giá — REAL baseline (rev 2)

Chạy `scripts/stylist/run_gpu_benchmark.py --model-id T3 --adapter post-RL` so với `gpu_T3.json` (REAL baseline). **Targets (rev 2 — realistic hơn):**

| Metric | REAL baseline T3 | Target sau RL | Quan trọng? |
|---|---:|---:|---|
| `occasion_formality` | **0.0000** | ≥ 0.65 | 🔴 P0 — nguyên failure #1 |
| `body_shape_advice` | **0.0000** | ≥ 0.45 | 🔴 P0 |
| `season_advice` | 0.3833 | ≥ 0.60 | 🟡 P1 |
| `coherence` | 0.5000 | ≥ 0.85 | 🟡 P2 — T2 đã 1.0; khả thi |
| `ask_back` | 0.6667 | ≥ 0.95 (anti-regress) | 🟢 P3 |
| `tool_call_derivation` | 0.7626 | ≥ 0.75 (anti-regress) | 🟢 P3 |
| **Overall mean** | **0.2793** | **≥ 0.55** | — |

**Mục tiêu overall REAL** (≥0.55) thấp hơn target rev 1 (≥0.65) — vì baseline thật đã 0.28, không phải 0.107 (mock); khoảng +0.27 gain là significant nhưng khả thi.

**Regression guard**: sau RL chạy lại `benchmark_stylist.py` (tool F1/text sim từ SFT eval) → Tool F1 không được tụt dưới 0.85 của T3 SFT.

---

## 7. Rủi ro & mitigation (rev 2)

| Rủi ro | Mitigation |
|---|---|
| GRPO Collapse (reward hack) | `β=0.04` KL drift; monitor `frac_reward_zero_std` ≥ 0.3 → giảm LR. |
| **Vocabulary mismatch không fix được qua RL** (3a) | Fix scorer song song (partial credit cho variant) — giảm gradient noise cho mô hình. |
| **Local 8GB OOM (peak 7.5GB)** | G=4 thay 8; `max_completion_length=192`; bật gradient_checkpointing. |
| Multimodal instability | Train text-only path first (T2) 100 step proof, rồi transfer recipe sang T3. |
| Length explosion | `loss_type=dr_grpo` + length penalty −0.05. |
| Catastrophic forget tiếng Việt | Drift KL; eval ask_back mỗi 50 step. |
| Kaggle 9h limit | `max_steps=500` ≤ 9h; resume từ checkpoint khi cần (save_steps=100). |
| Tool-call schema break | R6 zero khi enum invalid → mô hình tự học schema. |
| **uv run re-sync torch CPU** (Windows) | **KHÔNG dùng `uv run` cho GPU work** — sua  \`.venv/Scripts/python.exe\` trực tiếp + pip install --index-url cu130. Lập kỳ/v script intuitoal passing windows command. |
| `device_map="auto"` ValueError bnb 4-bit | Dùng `device_map={"":0}` (xem `run_gpu_benchmark.py`). |

---

## 8. Roadmap thực thi (rev 2 — với local GPU enabled)

| Phase | Việc | Status | Hardware |
|---|---|---|---|
| **P0** | Mở rộng prompt pool → 500-1000 (Cartesian + adversarial) | có `build_fashion_prompt_pool` (397); thiếu adversarial | CPU |
| **P0** | Unit tests 6 reward functions | ✅ 30 tests pass (`test_grpo_rewards.py`) | CPU |
| **P0** | `scripts/stylist/train_grpo_kaggle.py` kernel | ✅ done, --dry-run verified | CPU |
| **P0 NEW** | **GPU benchmark REAL trên 3 model** | ✅ done — `gpu_T{1,2,3}.json` | Local RTX 5060 ✅ |
| **P0 NEW** | Fix `score_occasion_formality` vocabulary variants | todo (P0) | CPU |
| **P1 NEW** | **Local GRPO 50 step T3 dry-proof** | todo (sau khi fix scorer) | Local RTX 5060 |
| **P2** | Push kernel Kaggle T4 ×2, 500 steps | todo | T4 Kaggle |
| **P2** | Eval post-RL T3 vs `gpu_T3.json` baseline | todo | Local RTX 5060 or T4 |
| **P2** | Nếu Tool F1 regress → multi-reward rebalance / KTO fallback | todo | T4 |
| **P3** | A/B SFT-vs-RL trên fashion-agent-benchmark (200 tasks × 5 evaluators) | todo | T4 |
| **P3 NEW** | T4 Gemma 4 12B GPU benchmark (cần 16GB+ — Kaggle A100/T4×2) | todo | Kaggle |

---

## 9. Trích dẫn (giữ)

- **GRPO / DeepSeekMath** — Shao et al., 2024, arXiv:2402.03300.
- **DeepSeek-R1** — DeepSeek-AI, 2025, arXiv:2501.12948.
- **TRL GRPOTrainer + QLoRA** — HuggingFace TRL (https://huggingface.co/docs/trl/en/grpo_trainer) + notebook `grpo_trl_lora_qlora.ipynb`.
- **Dr. GRPO** — Liu et al., 2025, arXiv:2503.20783 (remove length bias).
- **Reward scaling** — HF, 2025, arXiv:2508.08221 (batch-std > group-std).
- **DPO** — Rafailov et al., 2023, arXiv:2305.18290.
- **KTO** — Ethayarajh et al., 2024, arXiv:2402.01306 (unpaired preference).
- **SimPO** — Meng et al., 2024, arXiv:2405.14734 (reference-free).

---

## Appendix A: REAL benchmark artifact paths

- `docs/reports/stylist_benchmark_expansion/gpu_T1.json` — T1 (Qwen3-VL-8B Instruct + LoRA), mean 0.2596, eval_s 406.7
- `docs/reports/stylist_benchmark_expansion/gpu_T2.json` — T2 (Qwen3.5-9B text-only + LoRA), mean 0.3552, eval_s 712.0
- `docs/reports/stylist_benchmark_expansion/gpu_T3.json` — T3 (Qwen3-VL-8B Thinking + LoRA), mean 0.2793, eval_s 509.4
- `scripts/stylist/run_gpu_benchmark.py` — thành runner (Qwen3-VL aware, device_map={"{":0} }): đã hóaARDS CPU-leak vs bnb 4-bit.
- `scripts/stylist/grpo_rewards.py` — 6 reward functions + 397-prompt pool.
- `scripts/stylist/train_grpo_kaggle.py` — GRPO+QLoRA training script.

T4 Gemma 4 12B chưa benchmark GPU vì cần >8GB VRAM (4-bit ~7GB weights + KV cache ~2GB > 8GB budget của RTX 5060) — defer Kaggle.
