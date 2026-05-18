# Body & Occasion-Aware Fashion Recommendation
## PHASE 1 — GRADING VERSION (Tuần 1 → Tuần 10)

> **Mục tiêu phase này**: Hoàn thành MVP có chiều sâu DL đủ để lấy điểm cao môn Deep Learning, kèm final report + demo working.
> **Output cuối**: Báo cáo (~15–20 trang), slide thuyết trình, demo Gradio chạy được, mã nguồn trên GitHub có CI.

---

## 1. Thông tin dự án

| Field | Value |
|---|---|
| **Tên dự án** | OutfitMatch — Body & Occasion-Aware Fashion Recommender |
| **Domain** | Multimodal Deep Learning, Recommendation Systems, Computer Vision |
| **Team size** | 3 developers |
| **Methodology** | Scrum (1-week sprint) + XP practices (pair programming, CI/CD, TDD) |
| **Repo strategy** | Monorepo: `/data`, `/models`, `/api`, `/ui`, `/notebooks`, `/docs` |
| **Branch policy** | `main` (protected) — `dev` — `feature/<name>` |

---

## 2. Cấu trúc team & phân vai (3 devs)

Phân vai theo skill, nhưng XP yêu cầu **pair programming** — mọi component quan trọng phải có 2 người hiểu. Mỗi sprint rotate pair 1 lần để tránh siloed knowledge.

| Vai trò | Owner chính | Phụ trách |
|---|---|---|
| **Dev A — ML Lead** | Nhật Quang | Backbone model (Fashion-SigLIP), training loop, contrastive loss, evaluation framework, ablation experiments |
| **Dev B — Data & Backend** | TBD | Data collection pipeline, attribute extractor, vector DB (FAISS/Qdrant), inference API (FastAPI), CI/CD |
| **Dev C — Vision & Frontend** | TBD | Body shape pipeline (MediaPipe + classifier), Gradio demo, integration testing, user study coordinator |

**Vai trò luân phiên (theo sprint)**:
- **Scrum Master**: rotate weekly (đảm bảo tất cả đều hiểu process pain).
- **Sprint Reviewer**: rotate, người viết retrospective notes.

**Daily standup**: 15 phút, online, 3 câu hỏi chuẩn (hôm qua / hôm nay / blocker).
**Sprint review**: Thứ 7 cuối mỗi sprint, 30 phút, demo + retro.

---

## 3. MVP Scope — chốt cứng

### 3.1 IN-SCOPE (phải có trong tuần 10)

- [x] Body shape classifier (5 classes: hourglass, pear, apple, rectangle, inverted triangle) từ ảnh + (h, w).
- [x] Occasion encoder qua CLIP-text (5 classes: casual, office, formal, sport, evening).
- [x] Fashion item encoder (Fashion-SigLIP fine-tuned hoặc zero-shot baseline + finetuned).
- [x] Outfit composer Transformer-based với body+occasion tokens, output set {top, bottom, shoes, accessory}.
- [x] Attribute-based item customization (filter + re-rank trong catalog).
- [x] Vector DB index (FAISS) cho retrieval.
- [x] Gradio demo: upload selfie + nhập (h, w) + chọn occasion → trả về outfit suggestion.
- [x] Evaluation: FITB accuracy, compatibility AUC, body-conditional Precision@K, ablation đầy đủ.
- [x] User study mini: 10–15 người, mỗi người đánh giá 5 cases.

### 3.2 OUT-OF-SCOPE phase 1

- Generative item synthesis (Stable Diffusion / FLUX inpainting).
- Virtual try-on (CP-VTON / IDM-VTON).
- SMPL parameter regression (chỉ rule-based body classifier).
- Mobile app, scaling, production-grade monitoring.
- Real e-commerce catalog integration.

### 3.3 Definition of Done (DoD) — XP rule

Một feature chỉ DONE khi:
1. Code merged vào `dev` qua PR có review từ ít nhất 1 đồng đội.
2. Unit test cover ≥70% với pytest, CI pass (GitHub Actions).
3. Có docstring + 1 entry trong `docs/feature.md`.
4. Reproducible: notebook hoặc script chạy được từ scratch với `make demo`.

---

## 4. Tech stack chính

Trong file Tech stack riêng.

---

## 5. Datasets — Nguồn mở, đa dạng, chống bias

### 5.1 Catalog datasets (item images + text)

| Dataset | Size | License | Vai trò trong project |
|---|---|---|---|
| **DeepFashion (In-shop)** | 52K items, 7K identities | Research-only | Visual search backbone training |
| **DeepFashion-Multimodal** | 44K items + rich attribute | Research-only | Attribute extractor training |
| **Fashion200K** | 200K items + title | Research-only | Pre-training fine-tune signal |
| **Polyvore Outfits (Vasileva 2018)** | 68K outfits, 365K items | Research-only | Outfit compatibility ground truth |
| **Marqo/deepfashion-multimodal** (HF) | Curated subset | Apache 2.0 | Quick eval, đã có chuẩn |
| **iMaterialist Fashion** (Kaggle) | 1M+ images, multi-label attrs | Kaggle | Pre-training |
| **H&M Personalized Fashion Rec** (Kaggle) | 1M+ products | Kaggle | Bổ sung diversity, ảnh production-grade |

### 5.2 Body diversity datasets (chống bias body-thin)

| Dataset | Vai trò |
|---|---|
| **ViBE dataset** (Hsiao 2020) | Body shape diversity + flattering labels — email tác giả |
| **DeepFashion2** | Multi-pose, multi-view, có annotated landmarks |
| **SHHQ-1.0** | 40K high-quality full-body images, body diverse |
| **Fashionpedia** | Detailed garment segmentation + body context |

### 5.3 Strategy chống bias

1. **Audit dataset trước khi train**: dùng MediaPipe estimate body proportions trên 5K samples mỗi dataset → vẽ distribution histogram → identify gap.
2. **Re-sampling**: weighted sampler đảm bảo mỗi body shape class chiếm ≥15% mỗi batch.
3. **Augmentation diversity**: skin tone augmentation (HSV shift) để tránh bias về một skin range.
4. **Documentation**: trong report có section **Dataset Card** + **Model Card** kiểu Hugging Face — fairness section là bắt buộc.

### 5.4 Occasion labeling (weak supervision)

Polyvore không có occasion labels. Quy trình tạo:

```
For each outfit in Polyvore:
  outfit_text = concat(item.name for item in outfit.items)
  prompt = f"Classify this outfit into one of: 
            [casual, office, formal, sport, evening]. 
            Outfit: {outfit_text}"
  label = call_gemini(prompt)  # hoặc GPT-4o-mini
  cache(label)
```

**Budget**: Gemini free tier đủ cho ~30K outfits/day. Total ~70K outfits → 3 ngày.
**Quality check**: random 200 outfits, human verify → expect ≥80% agreement.

---

## 6. Sprint Plan (10 tuần — deadline cố định)

### Sprint Map

| Sprint | Tuần | Goal | Milestone cố định |
|---|---|---|---|
| **S0** | 1 | Research & exploration | ✅ Research done |
| **S1** | 2 | Architecture design + data pipeline draft | Proposal draft |
| **S2** | 3 | Proposal finalization + presentation | ✅ Proposal trình bày |
| **S3** | 4 | Data collection + body shape pipeline | Pipeline body alpha |
| **S4** | 5 | Catalog encoder (Fashion-SigLIP) + attribute extractor | Encoder v1 |
| **S5** | 6 | Outfit composer Transformer | Composer alpha |
| **S6** | 7 | Body-aware compatibility + occasion conditioning | Full pipeline alpha |
| **S7** | 8 | Item customization (attribute swap) + integration | E2E alpha |
| **S8** | 9 | Gradio demo + quick deploy + user study | Demo public |
| **S9** | 10 | Polish, ablation, report writing | ✅ MVP + Report |

---

### Sprint 0 — Tuần 1: Research

**Sprint Goal**: Mọi thành viên hiểu rõ problem space, models, datasets, đã chạy được baseline CLIP retrieval.

**Backlog**:
| ID | Task | Owner | Estimate | DoD |
|---|---|---|---|---|
| R-01 | Đọc 5 paper bắt buộc: CLIP, SigLIP, FashionCLIP, ViBE, Outfit-Transformer (Kalashi 2025) | All | 2d | 1-page summary mỗi paper |
| R-02 | Survey datasets: download + EDA notebook cho 3 dataset chính | Dev B | 2d | EDA notebook trên repo |
| R-03 | Chạy CLIP zero-shot retrieval trên DeepFashion → baseline metric | Dev A | 1d | Notebook + Recall@1/5/10 |
| R-04 | Survey body shape classification approaches | Dev C | 1d | Slide + chọn approach |
| R-05 | Setup repo: monorepo skeleton, CI, lint, pre-commit, dev container | Dev B | 1d | Repo green |
| R-06 | Setup experiment tracking (W&B / MLflow) | Dev A | 0.5d | Project created |

**Pair programming**: Dev A + Dev C on R-03 (baseline notebook).

**Ceremony**:
- Sprint planning: Thứ 2, 1h.
- Daily standup: 15 phút.
- Sprint review + retro: Chủ nhật, 1.5h.

**Risk**: Datasets có thể tốn vài ngày để approve (DeepFashion). Apply ngay từ ngày 1.

---

### Sprint 1 — Tuần 2: Architecture & Pipeline Draft

**Sprint Goal**: Có kiến trúc 5 tầng rõ ràng trên giấy. Data pipeline đã chạy được trên subset 5K samples.

**Backlog**:
| ID | Task | Owner | Estimate |
|---|---|---|---|
| A-01 | Vẽ system architecture diagram (Mermaid + Excalidraw) | Dev A | 1d |
| A-02 | Define interface contracts giữa các module (Python ABC) | All (pair) | 1d |
| A-03 | Build data ingestion pipeline cho Polyvore + DeepFashion | Dev B | 2d |
| A-04 | Body shape rule-based classifier v0 với MediaPipe | Dev C | 2d |
| A-05 | Occasion labeling pipeline với Gemini, test trên 500 outfits | Dev B | 1d |
| A-06 | Viết proposal draft (10 trang) | Dev A | 2d |
| A-07 | Risk register + mitigation plan | All | 0.5d |

**Pair**: Dev B + Dev C on A-03/A-04 (data side).

**Output cuối sprint**:
- `docs/architecture.md` với diagrams.
- Data pipeline chạy được, có ~5K outfits đã có occasion labels.
- Body classifier accuracy >70% trên 100 samples test manual.

---

### Sprint 2 — Tuần 3: PROPOSAL ⚡ (Milestone cứng)

**Sprint Goal**: Proposal finalized, thuyết trình thành công, có feedback từ thầy cô.

**Backlog**:
| ID | Task | Owner | Estimate |
|---|---|---|---|
| P-01 | Hoàn thiện proposal (15 trang) | Dev A | 3d |
| P-02 | Slide thuyết trình (15 slides) | Dev A + C | 2d |
| P-03 | Rehearsal 2 lần | All | 1d |
| P-04 | Tiếp tục data pipeline (đạt 30K outfits có labels) | Dev B | 3d |
| P-05 | Body classifier ML version (CNN, replace rule-based) | Dev C | 3d |
| P-06 | Đăng ký GPU resources (Colab Pro / Kaggle / Lab) | All | 0.5d |

**Proposal structure** (template chuẩn):
1. Problem & motivation
2. Related work (5-6 paper key)
3. Approach: 5-tầng architecture
4. Datasets & weak supervision strategy
5. Evaluation plan (metrics, baselines, ablation)
6. Risk & mitigation
7. Timeline (Gantt 10 tuần)
8. Team & responsibilities

**Deliverable cứng end-of-week**: `proposal_v1.pdf` + slide + recording rehearsal.

---

### Sprint 3 — Tuần 4: Data + Body Pipeline

**Sprint Goal**: Có training data v1 hoàn chỉnh. Body shape classifier production-ready.

| ID | Task | Owner |
|---|---|---|
| D-01 | Hoàn tất occasion labels cho 100% Polyvore (~70K) | Dev B |
| D-02 | Attribute extractor: train classifier multi-label (color, fit, style) trên DeepFashion-Multimodal | Dev A |
| D-03 | Body shape CNN v1 + augmentation pipeline | Dev C |
| D-04 | Train/val/test split (stratified theo body shape + occasion) | Dev B |
| D-05 | Unit tests cho data loaders | Dev C |
| D-06 | Bias audit notebook (distribution by body, skin tone) | All |

**Pair rotation**: Dev A + Dev B on D-02.

**Exit criteria**:
- Dataset v1 trên DVC, có schema documented.
- Body classifier accuracy ≥85% trên held-out test (5-class).
- Bias audit report cho thấy distribution acceptable.

---

### Sprint 4 — Tuần 5: Catalog Encoder

**Sprint Goal**: Fashion-SigLIP fine-tuned vượt baseline CLIP zero-shot.

| ID | Task | Owner |
|---|---|---|
| E-01 | Setup contrastive training loop với SigLIP loss | Dev A |
| E-02 | Fine-tune Fashion-SigLIP trên DeepFashion + Fashion200K | Dev A |
| E-03 | Build FAISS index, retrieval pipeline | Dev B |
| E-04 | Evaluation: Recall@1/5/10, mAP trên test set | Dev A + B |
| E-05 | Ablation 1: CLIP vs Fashion-SigLIP vs DINOv2 | Dev A |
| E-06 | Demo notebook: text → top-K items, image → top-K items | Dev C |

**Pair**: Dev A + Dev C trên E-06 (Dev C cần học encoder API).

**Exit criteria**:
- Fine-tuned model vượt zero-shot CLIP ≥5% Recall@5.
- Ablation table có 3 encoders so sánh.

---

### Sprint 5 — Tuần 6: Outfit Composer

**Sprint Goal**: Transformer composer chạy được, FITB accuracy >55%.

| ID | Task | Owner |
|---|---|---|
| C-01 | Implement Transformer composer (body_token, occ_token, outfit_token) | Dev A |
| C-02 | FITB training trên Polyvore | Dev A |
| C-03 | Beam search decoding | Dev A |
| C-04 | Catalog filter integration (hard constraint by category) | Dev B |
| C-05 | Eval: FITB acc, AUC, diversity | Dev A |
| C-06 | UI mockup cho final demo | Dev C |

**XP practice**: TDD cho C-04 (filter logic dễ regression).

**Exit criteria**: FITB ≥55%, compatibility AUC ≥0.85.

---

### Sprint 6 — Tuần 7: Body-Aware + Occasion Conditioning

**Sprint Goal**: ViBE-style body-aware embedding integrated. Pipeline end-to-end cho body+occasion.

| ID | Task | Owner |
|---|---|---|
| B-01 | Implement ViBE-style contrastive loss (body, item flattering) | Dev A |
| B-02 | Train body-aware embedding | Dev A |
| B-03 | Integrate vào composer | Dev A + B |
| B-04 | Ablation 2: w/ vs w/o body conditioning | Dev A |
| B-05 | Ablation 3: w/ vs w/o occasion conditioning | Dev A |
| B-06 | Catalog metadata enrichment (occasion tag per item) | Dev B |

**Exit criteria**: Body-conditional Precision@5 cải thiện ≥10% so với non-conditional baseline.

---

### Sprint 7 — Tuần 8: Customization + E2E Integration

**Sprint Goal**: Có full pipeline E2E. Đã có item customization theo attribute swap.

| ID | Task | Owner |
|---|---|---|
| I-01 | Attribute-conditioned retrieval module (filter + rerank) | Dev A + B |
| I-02 | Integration layer: orchestrator script | Dev B |
| I-03 | FastAPI inference endpoint | Dev B |
| I-04 | Latency profiling | Dev B |
| I-05 | Gradio prototype | Dev C |
| I-06 | E2E integration test | All |

**Pair**: Dev A + Dev B trên I-01.

**Exit criteria**: E2E latency <3s/query trên CPU, demo callable từ Gradio.

---

### Sprint 8 — Tuần 9: Demo Deploy + User Study

**Sprint Goal**: Demo public, có feedback từ ≥10 người, có data cho final report.

| ID | Task | Owner |
|---|---|---|
| U-01 | Polish Gradio UI (responsive, error handling) | Dev C |
| U-02 | Deploy lên Hugging Face Spaces hoặc Render | Dev B |
| U-03 | User study form (Google Form, 5 cases) | Dev C |
| U-04 | Recruit testers (10–15 người, ưu tiên đa dạng body type) | All |
| U-05 | Collect feedback, analyze | Dev C |
| U-06 | LLM-as-judge eval (Gemini score outfits) | Dev A |
| U-07 | Bug fix từ user feedback | All |

**Exit criteria**:
- Demo URL live.
- ≥10 responses collected.
- LLM-as-judge mean score ≥3.5/5.

---

### Sprint 9 — Tuần 10: REPORT ⚡ (Milestone cứng)

**Sprint Goal**: Final report + slide thuyết trình + demo bulletproof.

| ID | Task | Owner |
|---|---|---|
| F-01 | Final report 18–20 trang | Dev A |
| F-02 | Final slide 25–30 slides | Dev A + C |
| F-03 | Run final ablation suite | Dev A |
| F-04 | Reproducibility check: clone repo trên máy mới → chạy `make demo` | Dev B |
| F-05 | Record demo video 3 phút | Dev C |
| F-06 | Rehearsal final 2 lần | All |
| F-07 | Dataset card + Model card | All |
| F-08 | Code cleanup, README, LICENSE | Dev B |

**Final report structure** (chuẩn academic):

```
1. Introduction (1.5p)
2. Related Work (2p)
3. Method
   3.1 Problem formulation
   3.2 System architecture
   3.3 Body shape pipeline
   3.4 Catalog encoder
   3.5 Body+occasion-aware composer
   3.6 Item customization
4. Datasets & Weak Supervision (2p)
5. Experiments
   5.1 Setup
   5.2 Baselines
   5.3 Main results
   5.4 Ablation studies
   5.5 User study
   5.6 LLM-as-judge
6. Discussion
   6.1 Limitations
   6.2 Bias & fairness analysis
   6.3 Future work
7. Conclusion (1p)
8. References
Appendix: dataset card, model card, hyperparameters
```

---

## 7. Evaluation Framework — chốt từ Sprint 1

### 7.1 Quantitative metrics

| Metric | Tầng | Baseline | Target MVP |
|---|---|---|---|
| Recall@5 (catalog retrieval) | Encoder | CLIP zero-shot | +5% so với baseline |
| FITB accuracy | Composer | Random | ≥55% |
| Compatibility AUC | Composer | Bi-LSTM (Han 2017) | ≥0.85 |
| Body-conditional Precision@5 | Body-aware | Non-conditional | +10% |
| Diversity (intra-list distance) | Composer | — | ≥0.4 |

### 7.2 Ablation studies (BẮT BUỘC)

1. Encoder: CLIP / Fashion-SigLIP / DINOv2 / Fashion-SigLIP fine-tuned.
2. Body conditioning: on/off.
3. Occasion conditioning: on/off.
4. Decoding: greedy vs beam.

### 7.3 Qualitative

- User study: 10–15 testers, 5 cases mỗi người, Likert 1–5 trên relevance, body-fit, occasion-fit.
- LLM-as-judge: Gemini scoring 200 random outputs.
- Failure case analysis: 20 cases manual.

### 7.4 Strong baselines bắt buộc so

1. CLIP zero-shot retrieval + random outfit composition.
2. Fashion-SigLIP retrieval + Bi-LSTM compatibility.
3. **GPT-4V / Gemini zero-shot stylist** ← phải so với cái này, không né được.

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dataset access denied (DeepFashion) | Med | High | Apply tuần 1; fallback Fashion200K + Polyvore |
| GPU không đủ | High | High | Colab Pro+ ($50/m), Kaggle 30h/week, freeze backbone, dùng LoRA |
| Body classifier accuracy thấp | Med | Med | Fallback rule-based MediaPipe |
| Occasion labels Gemini noisy | High | Med | Human-verify 200 samples, calibrate prompt |
| FITB không vượt baseline | Med | High | Có sẵn baseline mạnh để so sánh; report kết quả trung thực |
| Team member drop / sick | Med | High | Pair programming → knowledge shared; backup task assignments |
| VLM zero-shot baseline mạnh hơn model của mình | High | Med | Tìm setting model thắng (retrieval trong catalog kín), report trung thực, frame as "specialized vs general" |
| Demo crash trong presentation | Med | High | Local backup, video record, dry run 2 lần |

---

## 9. XP Practices áp dụng

| Practice | Cách áp dụng |
|---|---|
| **Pair programming** | Mỗi sprint có ≥2 task pair, rotate pairs |
| **TDD** | Cho data loaders, attribute extractor, retrieval logic |
| **Continuous Integration** | GitHub Actions: lint + test on PR, auto-deploy demo on `main` |
| **Refactoring** | Cuối mỗi sprint 30 phút refactor session |
| **Small releases** | Demo working ở mỗi sprint review |
| **Collective ownership** | Mọi code đều có ≥2 người review/biết |
| **Simple design** | YAGNI — không over-engineer cho production phase 1 |
| **Sustainable pace** | Sprint review cho phép push lùi non-critical, no crunch |

---

## 10. Communication & Tools

| Purpose | Tool |
|---|---|
| Project board | GitHub Projects (Kanban: Backlog → In Progress → Review → Done) |
| Daily comms | Discord / Slack |
| Documentation | `/docs` trong repo (markdown) |
| Experiment tracking | Weights & Biases (free academic) |
| Data versioning | DVC + Google Drive remote |
| Code review | GitHub PR, mandatory 1 approval |
| Whiteboarding | Excalidraw |

---

## 11. Deliverables Checklist — Tuần 10

- [ ] `final_report.pdf` (18–20 trang)
- [ ] `final_slide.pdf` (25–30 slides)
- [ ] `demo_video.mp4` (3 phút)
- [ ] Gradio demo URL live + local fallback
- [ ] GitHub repo: README + LICENSE + `make demo` reproducible
- [ ] `dataset_card.md` + `model_card.md`
- [ ] Ablation tables CSV + plots
- [ ] User study results (anonymized CSV + summary)
- [ ] LLM-as-judge eval results
- [ ] All sprint retrospectives archived

---

## 12. Sau tuần 10 → Production phase

Chuyển sang `PROJECT_PLAN_PRODUCTION.md`.

Quy trình bàn giao:
1. Sprint 9 retrospective tổng hợp lessons.
2. User feedback từ Sprint 8 → prioritized backlog cho phase 2.
3. Architecture review: identify tech debt cần trả trước khi build feature mới.
4. Re-scope team: roles có thể đổi (vd Dev C chuyển sang full-time frontend).
