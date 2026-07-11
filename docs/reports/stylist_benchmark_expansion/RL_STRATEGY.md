# Chiến lược RL cho Stylist — Verifiable-Reward GRPO trên T3 Qwen3-VL-8B Thinking

**Ngày:** 2026-07-11
**Tác giả:** benchmark-expansion track
**Model mục tiêu:** **T3 — Qwen3-VL-8B Thinking + LoRA** (ứng viên production)
**Verdict:** **GRPO + QLoRA với reward = 6 deterministic scorers đã có trong `fashion_eval.py`** (verifiable-reward RL, không cần reward model / không cần human pairwise preferences).

---

## 1. Vì sao chọn T3 làm model RL

Từ `docs/reports/stylist_final_qlora_benchmark/DETAILED_REPORT.md` §6 (kết quả SFT QLoRA):

| Model | Tool F1 | Text sim | Format | Error | Eval loss |
|---|---:|---:|---:|---:|---:|
| **T3 Qwen3-VL-8B Thinking** | **0.8980** | **0.5519** | **1.0000** | 0 | **0.5943** |
| T2 Qwen3.5-9B BNB4 | 0.8776 | 0.4877 | 1.0000 | 0 | — |
| T1 Qwen3-VL-8B Instruct | 0.8571 | 0.5437 | 1.0000 | 0 | — |
| T4 Gemma 4 12B IT | 0.6531 | 0.5354 | 0.9714 | 0 | — |

T3 thắng trên 3/4 metric chính, có eval loss thấp nhất, tool validity = 1.0. T3 là multimodal (Qwen3-VL) → RL trên T3 cải thiện trực tiếp đường production (có thể nhận ảnh người dùng). T2 (text-only) là fallback nhanh nhưng không có vision → không tận dụng được tính năng cốt lõi của stylist.

**Gap cần RL đóng:** mock benchmark (`mock_run.json`, §9 DETAILED_REPORT) cho thấy với câu hỏi **knowledge/logic** (không phải tool-call), T3 hiện trả lời an toàn ("Bạn muốn mặc cho dịp nào ạ?") cho **tất cả 25 mục knowledge/coherence/season/body-shape** → mean 0.107. Đây là **hành vi SFT collapse** (mô hình quá thiên về ask-back an toàn). RL có thể trực tiếp tối ưu 6 hành vi này mà không cần nhãn người dùng.

---

## 2. So sánh thuật toán — chọn GRPO verifiable-reward

| Thuật toán | Dữ liệu cần | Reward model? | Ref model? | Critic? | GPU (8B) | Fit tool-call + 8B LoRA |
|---|---|---|---|---|---|---|
| **PPO (RLHF cổ điển)** | prompt + RM | **có** | có | **có** | ~4 model tải RAM — **rất nặng** | ❌ quá nặng cho Kaggle T4 |
| **DPO** | **pairs** (yw, yl) | không | có | không | 2 model | ⚠️ cần sinh pairs; offline dễ overfit |
| **IPO** | pairs | không | có | không | 2 model | ⚠️ như DPO, chống overfit |
| **KTO** | **unpaired** (desirable/undesirable) | không | có | không | 2 model | ✅ nếu chỉ có nhãn binary |
| **SimPO** | pairs | không | **không** | không | 1 model | ✅ nhẹ nhất, nhưng cần pairs |
| **GRPO (verifiable reward)** | **prompt only** | **không (rule-based!)** | có (KL, optional β=0) | **không** | 1–2 model | ✅ **tối ưu** cho verifiable |

### Tại sao GRPO thắng cho OutfitMatch

1. **Verifiable reward có sẵn.** `fashion_eval.py` đã triển khai 6 scorer deterministic dựa trên `vocab.py` (occasion→formality F1, body-shape/season keyword recall, coherence verdict, ask-back gate, tool-call F1 × enum-valid). Đây chính là *verifiable reward* theo nghĩa DeepSeek-R1 — không cần reward model, không cần pairwise preferences, không cần RLAIF. Mỗi prompt có ground-truth objectivity.
2. **Không cần Critic.** GRPO bỏ critic (theo DeepSeekMath / DeepSeek-R1), dùng group baseline (mean/std của G completion). Tiết kiệm ~1 model trong RAM → chạy được 8B QLoRA trên T4/Kaggle (~9.2 GB VRAM, theo notebook chính thức `grpo_trl_lora_qlora.ipynb` của HF).
3. **On-policy.** GRPO sinh completion tại mỗi step → mô hình học đúng phân phối của chính nó, tránh distribution mismatch của DPO offline (vấn đề chính khi SFT đã collapse sang ask-back an toàn).
4. **Tính toán được trên phần cứng của ta.** Kaggle P100 16GB / T4×2 15GB mỗi GPU là đủ cho GRPO+QLoRA 8B.

### Backup: KTO (nếu GRPO quá nặng hoặc không ổn định)
Nếu GRPO chạy không ổn định trên Kaggle, **KTO** là fallback vì chỉ cần nhãn unpaired (mỗi sample chỉ cần `desirable`/`undesirable` từ 6 scorer) và TRL có `KTOTrainer` hỗ trợ QLoRA.

---

## 3. Reward design — 6 verifiable reward functions

Reward functions được implement trong `scripts/stylist/grpo_rewards.py`, mỗi function có chữ ký:
```python
def reward_fn(completions: list[list[dict[str,str]]], **kwargs) -> list[float]
```
(theo chuẩn `trl.GRPOTrainer`). Mỗi completion group được chấm bởi **pool item của task đó** (đưa prompt vào `reward_funcs` + dataset `prompt` chứa trường `item_type` để router chọn scorer).

| # | Reward | Nguời chấm | Thang | Mục tiêu tối ưu |
|---|---|---|---|---|
| R1 | `occasion_formality_reward` | `score_occasion_formality` | F1 ∈ [0,1] | Nêu đúng formality band cho occasion |
| R2 | `body_shape_advice_reward` | `score_body_shape_advice` | recall−½·neg ∈ [0,1] | Tư vấn body-shape đúng, né sai |
| R3 | `season_advice_reward` | `score_season_advice` | recall−½·neg ∈ [0,1] | Tư vấn vải/mùa đúng |
| R4 | `coherence_reward` | `score_coherence_judgment` | binary {0,1} | Phán đoán outfit coherent/incoherent |
| R5 | `ask_back_reward` | `score_ask_back` | binary {0,1} | Hỏi lại khi thiếu occasion, KHÔNG hallucinate |
| R6 | `tool_call_reward` | `score_tool_call_derivation` | F1×enum_valid ∈ [0,1] | search_outfits call đúng schema + enum |

**Reward tổng:** Mỗi prompt chỉ kích hoạt 1 reward (theo `item_type`) — tránh reward conflict. Có thể thêm **format bonus** (+0.1 nếu output có `<tool_call>` đúng khi task yêu cầu) và **length penalty** (−0.05 nếu completion > 256 token, để tránh gibberish dài).

### Anti-reward-hacking
- `score_ask_back` **trừ điểm** nếu hallucinate occasion (R5 đã tích hợp).
- `score_tool_call_derivation` **zero** nếu enum invalid (R6 đã tích hợp).
- Drift KL (`β>0`) giữ mô hình gần SFT ref → chống reward hack (xem HF blog "guide-to-llm-post-training-algorithms" §KL pitfalls: K1-in-reward > K3-in-loss > K3-in-reward).

---

## 4. Data — Prompt pool từ fashion_eval (zero new annotation)

GRPO chỉ cần **prompts** (không cần completions). `fashion_eval.py` đã có 28 prompts trên 6 task types (9 occasion×formality + 5 body-shape + 4 season + 4 coherence + 3 ask-back + 3 tool-call). Để RL hiệu quả, **mở rộng prompt pool lên ~500–1000**:

1. **Cartesian expansion occasion×style×body×season** → ~9×8×5×4 = 1440 mix profile, mỗi profile 1 prompt kiểu "Tôi dáng pear, phong cách korean, mùa hè, đi làm — gợi ý formality và 2 outfit?". Ground-truth formality từ `formalities_for_occasion`, body/season cue từ curated banks.
2. **Adversarial ask-back:** 50 prompt thiếu occasion cố ý (đã có pattern 3, cần 50 biến thể).
3. **Tool-call profile:** 50 profile đầy đủ slot → reference tool-call auto-sinh từ schema.

Tất cả ground-truth **tính từ `vocab.py`** → reproducible 100%, không annotation người dùng. Module `_build_*_items()` trong `fashion_eval.py` đã có pattern này — chỉ cần mở rộng bank.

---

## 5. Training recipe — Kaggle

**Script:** `scripts/stylist/train_grpo_kaggle.py` (push qua Kaggle kernel, mô hình về D:/Models + HF Hub).

```python
# Cốt lõi (xem file đầy đủ)
from trl import GRPOConfig, GRPOTrainer
from scripts.stylist.grpo_rewards import FASHION_REWARD_FUNCS, select_reward

trainer = GRPOTrainer(
    model="unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",   # T3 base (đã có ở D:/Models/hf_hub)
    reward_funcs=FASHION_REWARD_FUNCS,                # 6 verifiable scorers
    args=GRPOConfig(
        per_device_train_batch_size=8,
        num_generations=8,            # G — group size cho advantage baseline
        max_completion_length=256,
        learning_rate=1e-5,           # thấp hơn SFT (1e-4) vì RL nhạy
        max_steps=500,                # ~3-5h trên T4; mở rộng nếu ổn định
        beta=0.04,                    # drift KL, chống reward hack
        optim="paged_adamw_8bit",
        scale_rewards="batch",        # HF 2508.08221: ổn định hơn group-std
        loss_type="dr_grpo",          # bỏ length bias (2503.20783)
        bf16=False, fp16=True,        # T4 không có bf16
        gradient_checkpointing=True,
    ),
    train_dataset=fashion_prompt_pool,   # 500-1000 prompts (item_type để router)
    peft_config=LoraConfig(r=32, alpha=32, target_modules=[...]),
    # quantization_config=BitsAndBytesConfig(load_in_4bit=True, nf4, double_quant)
)
trainer.train()
```

### Hyperparameter justification
| Param | Giá trị | Lý do / nguồn |
|---|---|---|
| `num_generations` G | 8 | Group baseline cần ≥4; T4 RAM giới hạn. HF notebook dùng 8. |
| `learning_rate` | 1e-5 | RL nhạy hơn SFT 10×; DeepSeek-R1 dùng 1e-6 cho 671B, scale lên cho 8B. |
| `beta` (KL) | 0.04 | DeepSeekMath default; nếu hack tăng lên 0.1. |
| `max_completion_length` | 256 | Stylist trả lời ngắn; tiết kiệm gen time. |
| `loss_type` | `dr_grpo` | Bỏ length bias — 2503.20783 chứng minh GRPO gốc thiên answer dài. |
| `scale_rewards` | `batch` | HF 2508.08221: group-std gây difficulty bias. |
| LoRA r | 32 | Match SFT adapter sẵn có (cùng rank để có thể merge/inject). |

### Compute budget
- **Kaggle T4 (15GB) ≈ 13h cho 500 steps** (HF notebook benchmark). T4×2 = ~7h.
- **Kaggle P100 (16GB)** tương đương T4.
- **GPU PC local**: KHÔNG có (CUDA=False, CPU-only). Bắt buộc Kaggle/Colab.
- vLLM **TẮT** với QLoRA (HF warning: weight sync精度 issue) — dùng transformers generate.

---

## 6. Đánh giá — đo trước/sau RL

Chạy `scripts/stylist/run_fashion_benchmark.py --model <t3-rl-adapter>` và so với `mock_run.json` (baseline SFT). **Mục tiêu:**

| Metric | Baseline (mock) | Target sau RL |
|---|---:|---:|
| `occasion_formality` mean | 0.0 | ≥ 0.70 |
| `body_shape_advice` mean | 0.0 | ≥ 0.50 |
| `season_advice` mean | 0.0 | ≥ 0.50 |
| `coherence` mean | 0.0 | ≥ 0.75 |
| `ask_back` mean | 1.0 | ≥ 0.95 (không regress!) |
| `tool_call_derivation` mean | 0.0 | ≥ 0.70 |
| **Overall mean** | **0.107** | **≥ 0.65** |

**Regression guard:** chạy lại `benchmark_stylist.py` (tool F1/text sim) để đảm bảo Tool F1 không tụt dưới 0.85 (RL có thể trade-off tool-call vs free-text → phải đo cả hai).

---

## 7. Rủi ro & mitigation

| Rủi ro | Mitigation |
|---|---|
| GRPO Collapse (reward hack) | `β=0.04` KL drift; monitor `frac_reward_zero_std` ≥ 0.3 → giảm LR. |
| Multimodal instability | Train **text-only path trước** (T2 Qwen3.5-9B) 200 steps proof-of-concept, rồi transfer recipe sang T3 VLM. |
| Length explosion | `loss_type=dr_grpo` + length penalty −0.05. |
| Catastrophic forget tiếng Việt | Drift KL giữ gần SFT ref; eval `ask_back` (tiếng Việt) mỗi 50 step. |
| Kaggle 9h limit | `max_steps=500` ≤ 9h; nếu chưa converge, resume từ checkpoint (save_steps=100). |
| Tool-call schema break | R6 zero khi enum invalid → mô hình tự học schema. |

---

## 8. Roadmap thực thi

| Phase | Việc | Status | GPU? |
|---|---|---|---|
| **P0** | Mở rộng prompt pool → 500-1000 (Cartesian vocab) | `grpo_rewards.py` + pool builder | CPU |
| **P0** | Unit test 6 reward functions (deterministic) | `tests/test_grpo_rewards.py` | CPU |
| **P0** | Viết `train_grpo_kaggle.py` kernel | done | — |
| **P1** | Dry-run GRPO 10 steps CPU (sanity check reward shaping) | todo | CPU (slow) |
| **P1** | Push kernel Kaggle T4, 500 steps | todo | T4 |
| **P2** | Eval RL adapter vs SFT baseline trên 6 task + tool F1 | todo | T4 |
| **P2** | Nếu Tool F1 regress → multi-reward rebalance hoặc KTO fallback | todo | T4 |
| **P3** | A/B SFT-vs-RL trên fashion-agent-benchmark (200 tasks × 5 evaluators) | todo | T4 |

---

## 9. Trích dẫn

- **GRPO / DeepSeekMath** — Shao et al., 2024, arXiv:2402.03300, "Pushing the Limits of Mathematical Reasoning in Open Language Models".
- **DeepSeek-R1** — DeepSeek-AI, 2025, arXiv:2501.12948, "Incentivizing Reasoning Capability in LLMs via RL" (R1-Zero pure RL with verifiable rewards).
- **TRL GRPOTrainer + QLoRA** — HuggingFace TRL docs (https://huggingface.co/docs/trl/en/grpo_trainer) + official notebook `examples/notebooks/grpo_trl_lora_qlora.ipynb` (7B QLoRA trên T4 free, 9.2GB VRAM).
- **DPO** — Rafailov et al., 2023, arXiv:2305.18290.
- **KTO** — Ethayarajh et al., 2024, arXiv:2402.01306 (unpaired preference).
- **SimPO** — Meng et al., 2024, arXiv:2405.14734 (reference-free).
- **Dr. GRPO** — Liu et al., 2025, arXiv:2503.20783 (remove length bias).
- **Lite PPO / reward scaling** — HF, 2025, arXiv:2508.08221 (batch-std > group-std).
- **KL estimator pitfalls** — Shah et al., 2026, arXiv:2512.21852 ("A Comedy of Estimators").
- **Post-training algorithm guide** — Zadorozhny, HF Blog, 2025 (https://huggingface.co/blog/karina-zadorozhny/guide-to-llm-post-training-algorithms).
