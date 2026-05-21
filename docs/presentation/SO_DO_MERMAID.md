# OutfitMatch — Bộ Sơ đồ Mermaid cho Thuyết trình

> Tài liệu đi kèm `PHAN_TICH_KIEN_TRUC_MODEL.md`. Mỗi sơ đồ render được trực tiếp trên GitHub, VS Code (Markdown Preview Mermaid), hoặc dán vào <https://mermaid.live> để xuất PNG/SVG đưa vào slide.
>
> **Mục lục sơ đồ:**
> 1. Kiến trúc hệ thống 6 tầng (System Overview)
> 2. Data Pipeline — 7 stage (DAG thu thập & tiền xử lý)
> 3. Training Pipeline — 5 component (đồ thị phụ thuộc)
> 4. SigLIP Contrastive Loss — luồng huấn luyện encoder
> 5a. OutfitTransformer — lắp ráp chuỗi token
> 5b. OutfitTransformer — bên trong một TransformerEncoderLayer
> 6. Inference Pipeline — sequence diagram 6 bước
> 7. Body Shape Classifier — cây quyết định 5 lớp
> 8. Preference Structuring — định tuyến hard/soft
> 9. Conditional Bradley-Terry — luồng preference post-training
> 10. Sprint Map — Gantt 10 tuần ↔ tầng kiến trúc
> 11. Experiment Cycle — lưới ablation một trục

---

## 1. Kiến trúc hệ thống 6 tầng (System Overview)

```mermaid
flowchart TD
    IN(["INPUT: selfie + height/weight + occasion + style prompt"])

    subgraph L0["LAYER 0 — Preference Structuring  ·  src/preference"]
        direction TB
        P1["PromptStructurer<br/>Gemini API + diskcache"]
        P2["StructuredPreference<br/>hard + soft"]
        P1 --> P2
    end

    subgraph L1["LAYER 1 — Body Understanding  ·  src/body"]
        direction TB
        B1["YOLOv8-pose<br/>17 keypoints COCO-17"]
        B2["keypoints_to_measures<br/>shoulder / waist / hip"]
        B3["rule classifier<br/>5-class body shape"]
        B1 --> B2 --> B3
    end

    L2["LAYER 2 — Catalog Encoder  ·  src/encoders<br/>Marqo/marqo-fashionSigLIP — image and text to L2-norm embedding"]
    L3["LAYER 3 — Vector Store / Retrieval<br/>Qdrant Docker :6333 — ANN search + hard-constraint payload filter"]
    L4["LAYER 4 — Outfit Composer  ·  src/train/composer.py<br/>OutfitTransformer — tokens CLS + item×N + BODY + OCC + PREF×K"]
    L5["LAYER 5 — Item Customization<br/>POST /customize-item — Qdrant filter + composer re-rank"]
    OUT(["OUTPUT: Top 3-5 outfit sets — items + score + body_shape + occasion"])

    IN --> P1
    IN --> B1
    P2 -->|"hard to payload filter"| L3
    P2 -->|"soft to PREF tokens"| L4
    B3 -->|"body_vector to BODY token"| L4
    B3 -->|"fallback fit_bias"| L3
    IN --> L2
    L2 --> L3 --> L4 --> L5 --> OUT

    classDef layer fill:#eef4ff,stroke:#3366cc,stroke-width:1px
    class L2,L3,L4,L5 layer
```

---

## 2. Data Pipeline — 7 Stage (Thu thập & Tiền xử lý)

```mermaid
flowchart TD
    SRC1["HF: Marqo/deepfashion-inshop<br/>52.6K rows"]
    SRC2["HF: Marqo/deepfashion-multimodal<br/>42.5K rows"]
    SRC3["HF: Marqo/fashion200k<br/>201.6K rows"]
    SRC4["HF: owj0421/polyvore-outfits<br/>413.8K rows"]
    SRC5["Custom catalog<br/>thu thap thu cong"]

    S1["STAGE 1 — Catalog Ingest and Validate<br/>chuan hoa schema catalog_metadata.parquet<br/>validate_custom_data.py + target distribution"]
    S2["STAGE 2 — Encoder FT Data Prep<br/>cap anchor/positive + augmentation<br/>flip / colorjitter / crop / resize 224 / normalize"]
    S3["STAGE 3 — Embed and Index<br/>encoder frozen to 768-dim L2-norm to Qdrant catalog"]
    S4["STAGE 4 — Outfit Compatibility Data Prep<br/>Polyvore to PolyvoreCompatDataset + PolyvoreFITBDataset"]
    S5["STAGE 5 — Occasion Labeling<br/>Gemini weak supervision + diskcache"]
    S6["STAGE 6 — Preference Triplet Generation<br/>triplets.jsonl + flip invariant >= 30 percent"]
    S7["STAGE 7 — Train/Val/Test Split<br/>anti-leakage item + outfit + instruction level — DVC"]

    ENCODER_CKPT[/"encoder checkpoint<br/>tu Training Component 1"/]

    SRC1 --> S1
    SRC2 --> S1
    SRC3 --> S1
    SRC5 --> S1
    SRC4 --> S4

    S1 --> S2 --> TRAIN1["to Training Component 1<br/>Encoder Fine-tuning"]
    S1 --> S3
    ENCODER_CKPT -.->|"can encoder da fine-tune"| S3
    S4 --> S5 --> S6 --> S7
    S7 --> TRAIN3["to Training Component 3 + 4"]

    classDef stage fill:#fff3e0,stroke:#e67e22
    class S1,S2,S3,S4,S5,S6,S7 stage
```

---

## 3. Training Pipeline — 5 Component (Đồ thị phụ thuộc)

```mermaid
flowchart TD
    D1[/"Catalog Data"/]
    D2[/"Outfit Pair Data — Polyvore"/]
    D3[/"Preference Triplet Data"/]
    D4[/"Pose Data"/]

    C1["COMPONENT 1 — Encoder Fine-tuning<br/>SigLIP contrastive loss + progressive unfreezing<br/>GATE: Recall@5 >= CLIP-ZS + 5pp"]
    C2["COMPONENT 2 — Embedding Index Build<br/>encoder frozen to batch encode to Qdrant"]
    C3["COMPONENT 3 — OutfitTransformer Base Train<br/>Bradley-Terry pairwise loss<br/>GATE: FITB >= 55 percent · AUC >= 0.85"]
    C4["COMPONENT 4 — Preference Post-training<br/>conditional Bradley-Terry + PREF tokens<br/>GATE: pairwise acc >= 0.65 · flip >= 0.30"]
    C5["COMPONENT 5 — Body Shape Classifier<br/>rule-based — validate bang unit test"]

    D1 --> C1 --> C2 --> C3 --> C4
    D2 --> C3
    D3 --> C4
    D4 --> C5

    INV1{{"INV-1: encoder FROZEN trong C3 va C4"}}
    INV2{{"INV-2: EXTRACTOR_VERSION giong nhau train va inference"}}
    INV3{{"INV-3: flip pairs >= 30 percent trong triplets.jsonl"}}

    INV1 -.-> C3
    INV1 -.-> C4
    INV2 -.-> C4
    INV3 -.-> C4

    classDef comp fill:#e8f5e9,stroke:#2e7d32
    classDef inv fill:#ffebee,stroke:#c62828
    class C1,C2,C3,C4,C5 comp
    class INV1,INV2,INV3 inv
```

---

## 4. SigLIP Contrastive Loss — Luồng huấn luyện Encoder (Component 1)

```mermaid
flowchart TD
    BATCH["Batch N item — moi item co (image, caption)"]

    IMG["images — N anh"]
    TXT["texts — N caption"]
    BATCH --> IMG
    BATCH --> TXT

    IENC["Image Tower (ViT)<br/>encode_image"]
    TENC["Text Tower (Transformer)<br/>encode_text"]
    IMG --> IENC
    TXT --> TENC

    IV["img vectors (N,D)"]
    TV["txt vectors (N,D)"]
    IENC --> IV
    TENC --> TV

    NORM["F.normalize dim=1 — L2 normalize ca hai"]
    IV --> NORM
    TV --> NORM

    LOGITS["logits = (img @ txt.T) * t + b<br/>t=10.0 temperature · b=-10.0 bias<br/>shape (N,N)"]
    NORM --> LOGITS

    LABELS["labels = 2*eye(N) - 1<br/>+1 tren duong cheo (cap dung)<br/>-1 ngoai duong cheo (cap sai)"]

    LOSS["loss = -mean( logsigmoid( labels * logits ) )<br/>binary classification doc lap tung cap (i,j)"]
    LOGITS --> LOSS
    LABELS --> LOSS

    BACK["AdamW — backward + step<br/>chi cap nhat param requires_grad=True"]
    LOSS --> BACK
    BACK -->|"next step"| BATCH

    EVAL["Eval val set — Recall@1/5/10 + mAP"]
    BACK -.-> EVAL

    classDef hot fill:#fff3e0,stroke:#e67e22
    class LOGITS,LOSS hot
```

---

## 5a. OutfitTransformer — Lắp ráp chuỗi token (forward)

```mermaid
flowchart TD
    subgraph INPUTS["Input tensors cua forward()"]
        IE["item_embeds (B,N,D)<br/>da encode boi catalog encoder"]
        MK["mask (B,N) bool — True = item hop le"]
        BD["body (B,D) — tuy chon"]
        OC["occ (B,D) — tuy chon"]
        PR["pref dict — group to (B,D) — tuy chon"]
    end

    CLS["self.cls — nn.Parameter (1,1,D)<br/>expand to (B,1,D)"]
    BDP["body_proj — Linear(D,D)"]
    OCP["occ_proj — Linear(D,D)"]
    PRP["pref_proj ModuleDict — Linear(D,D) moi group"]

    BD --> BDP
    OC --> OCP
    PR --> PRP

    SEQ["x = concat — token sequence (B,L,D)<br/>CLS + item_1..item_N + BODY? + OCC? + PREF_style? PREF_color? PREF_fit?<br/>L = 1 + N + body? + occ? + K"]
    CLS --> SEQ
    IE --> SEQ
    BDP --> SEQ
    OCP --> SEQ
    PRP --> SEQ

    PAD["src_key_padding_mask (B,L)<br/>pad = NOT concat(keep) — che vi tri padding<br/>CLS/BODY/OCC/PREF luon keep=True"]
    MK --> PAD

    ENC["nn.TransformerEncoder — 4 layers<br/>self-attention — KHONG positional encoding (Set Transformer)"]
    SEQ --> ENC
    PAD --> ENC

    HOUT["h (B,L,D) — output sau 4 layer"]
    ENC --> HOUT

    PICK["h[:, 0] — lay token CLS (B,D)"]
    HOUT --> PICK

    HEAD["head — Linear(D,1) to squeeze"]
    PICK --> HEAD

    SCORE(["compatibility score (B,) — 1 scalar / outfit"])
    HEAD --> SCORE

    classDef tok fill:#ede7f6,stroke:#5e35b1
    classDef hot fill:#fff3e0,stroke:#e67e22
    class CLS,BDP,OCP,PRP tok
    class ENC,SCORE hot
```

---

## 5b. OutfitTransformer — Bên trong một TransformerEncoderLayer

```mermaid
flowchart TD
    X["Input x (B,L,D) — D=512"]

    subgraph MHA["Multi-Head Self-Attention"]
        QKV["Q,K,V projection — Linear<br/>8 head · head_dim = 512/8 = 64"]
        ATT["Attention = softmax(Q·K^T / sqrt(64)) · V<br/>ap dung src_key_padding_mask"]
        OUTP["Output projection — Linear(D,D)"]
        QKV --> ATT --> OUTP
    end

    ADD1["Add residual + LayerNorm"]
    X --> QKV
    X --> ADD1
    OUTP --> ADD1

    subgraph FFN["Feed-Forward Network (position-wise)"]
        L1["Linear(512 to 2048)"]
        ACT["ReLU"]
        L2["Linear(2048 to 512)"]
        L1 --> ACT --> L2
    end

    ADD1 --> L1
    ADD2["Add residual + LayerNorm"]
    ADD1 --> ADD2
    L2 --> ADD2

    OUTX(["Output (B,L,D) — vao layer ke tiep"])
    ADD2 --> OUTX

    NOTE["~3.15M params / layer · x4 layer ~ 12.6M<br/>tong model ~ 13-14M params (model nhe — muc tieu < 3s CPU)"]
    OUTX -.-> NOTE

    classDef hot fill:#fff3e0,stroke:#e67e22
    class MHA,FFN hot
```

---

## 6. Inference Pipeline — Sequence Diagram 6 bước

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant API as FastAPI /recommend
    participant L0 as Layer 0 PromptStructurer
    participant L1 as Layer 1 Body Pipeline
    participant ENC as Layer 2 fashionSigLIP
    participant QD as Layer 3 Qdrant
    participant CMP as Layer 4 OutfitTransformer

    U->>API: image_b64 + height/weight + occasion + instruction
    API->>L0: structure(instruction, body_shape)
    L0-->>API: StructuredPreference {hard, soft}
    Note over L0: cache hit ~0ms · miss ~300-800ms

    alt co anh selfie
        API->>L1: extract pose + classify shape
        L1-->>API: body_shape (1 trong 5 lop)
    else khong co anh
        Note over API: body_shape = "" — bo qua body filter
    end

    API->>ENC: encode_text(query) to 768-dim vector
    ENC-->>API: query embedding L2-norm
    API->>QD: ANN cosine search + hard payload filter
    QD-->>API: candidate pool theo category slot (top-K=50)

    API->>CMP: forward CLS + item×N + BODY + OCC + PREF×K
    CMP-->>API: compatibility score moi outfit set
    Note over CMP: rank + deduplicate theo score

    API-->>U: Top 3-5 outfit sets + latency_ms
    Note over U,CMP: tong E2E latency < 3 giay tren CPU
```

---

## 7. Body Shape Classifier — Cây quyết định 5 lớp

```mermaid
flowchart TD
    KP["YOLO-pose to 17 keypoints COCO-17"]
    M["keypoints_to_measures<br/>shoulder = dist(kp5,kp6)<br/>hip = dist(kp11,kp12)<br/>waist = (shoulder+hip)/2 * 0.85 — proxy"]
    KP --> M

    R1{"waist >= shoulder<br/>VA waist >= hip ?"}
    M --> R1
    R1 -->|"co"| APPLE(["apple"])
    R1 -->|"khong"| R2

    R2{"shoulder/hip > 1.05 ?"}
    R2 -->|"co"| INV(["inverted_triangle"])
    R2 -->|"khong"| R3

    R3{"shoulder/hip < 0.95 ?"}
    R3 -->|"co"| PEAR(["pear"])
    R3 -->|"khong — vai xap xi hong"| R4

    R4{"waist_ratio <= 0.80 ?<br/>waist_ratio = waist / max(shoulder,hip)"}
    R4 -->|"co — eo that ro"| HG(["hourglass"])
    R4 -->|"khong"| RECT(["rectangle"])

    NONE["khong detect duoc pose"]
    KP -.->|"kp = None"| NONE
    NONE --> RECTDEF(["body_shape = rectangle (default an toan)"])

    classDef cls fill:#e8f5e9,stroke:#2e7d32
    class APPLE,INV,PEAR,HG,RECT,RECTDEF cls
```

---

## 8. Preference Structuring — Định tuyến hard / soft (Layer 0)

```mermaid
flowchart TD
    INST["instruction — free-text style prompt cua user"]
    BSHAPE["body_shape — tu Layer 1"]

    KEY["key = SHA256(EXTRACTOR_VERSION | instruction)"]
    INST --> KEY

    CACHE{"diskcache<br/>co key ?"}
    KEY --> CACHE
    CACHE -->|"hit"| RAW["raw JSON tu cache"]
    CACHE -->|"miss"| GEMINI["Gemini — STRUCT_PROMPT.format(instruction)"]
    GEMINI --> RAW
    GEMINI -.->|"luu lai"| CACHE

    PARSE["json.loads to StructuredPreference (pydantic validate)"]
    RAW --> PARSE

    HARD["hard: HardConstraint<br/>colors_avoid · categories_exclude<br/>materials_require · fit_bias · source"]
    SOFT["soft: SoftPreference<br/>style · color · fit"]
    PARSE --> HARD
    PARSE --> SOFT

    FB{"hard.is_empty() ?"}
    HARD --> FB
    FB -->|"co — user khong neu rang buoc"| BFB["apply_body_fallback<br/>pear to structured_top · apple to defined_waist<br/>hourglass to fitted · rectangle to add_curves<br/>inverted_triangle to volume_bottom<br/>source = body_fallback"]
    BSHAPE --> BFB
    FB -->|"khong"| HKEEP["giu hard cua user"]

    QFILTER["LAYER 3 — Qdrant payload filter"]
    BFB --> QFILTER
    HKEEP --> QFILTER

    PTOK["LAYER 4 — moi nhom soft active<br/>to encode_text to token PREF_style / PREF_color / PREF_fit"]
    SOFT --> PTOK

    classDef hot fill:#fff3e0,stroke:#e67e22
    class QFILTER,PTOK hot
```

---

## 9. Conditional Bradley-Terry — Luồng Preference Post-training (Component 4)

```mermaid
flowchart TD
    TRIP["Triplet — instruction + body_shape + pos_items + neg_items"]

    STR["PromptStructurer.structure(instruction, body_shape)<br/>to StructuredPreference"]
    TRIP --> STR

    PDICT["pref_dict — moi nhom soft active<br/>encoder.encode_text(phrase) to vector (1,D)"]
    STR --> PDICT

    ENCP["encoder.encode_image(pos_items) — FROZEN<br/>to pos_embeds (1,Np,D)"]
    ENCN["encoder.encode_image(neg_items) — FROZEN<br/>to neg_embeds (1,Nn,D)"]
    TRIP --> ENCP
    TRIP --> ENCN

    FPOS["composer(pos_embeds, pos_mask, pref=pref_dict) to s_pos"]
    FNEG["composer(neg_embeds, neg_mask, pref=pref_dict) to s_neg"]
    ENCP --> FPOS
    ENCN --> FNEG
    PDICT --> FPOS
    PDICT --> FNEG

    LOSS["pairwise_bt_loss = -log sigmoid(s_pos - s_neg)<br/>CUNG bo PREF token o ca 2 forward — conditional"]
    FPOS --> LOSS
    FNEG --> LOSS

    OPT["AdamW — chi cap nhat composer.parameters()<br/>encoder KHONG nam trong optimizer (INV-1)"]
    LOSS --> OPT
    OPT -->|"next batch"| TRIP

    EVAL["Eval — preference_pairwise_accuracy + instruction_flip_consistency"]
    OPT -.-> EVAL

    classDef hot fill:#fff3e0,stroke:#e67e22
    classDef frozen fill:#eceff1,stroke:#607d8b
    class LOSS hot
    class ENCP,ENCN frozen
```

---

## 10. Sprint Map — Gantt 10 tuần ↔ Tầng kiến trúc

```mermaid
gantt
    title OutfitMatch — 10 Sprint (Scrum 1 tuan / sprint) anh xa sang tang kien truc
    dateFormat YYYY-MM-DD
    axisFormat S%W

    section Nen tang
    S0 Research va baseline CLIP            :done,    s0, 2026-03-16, 7d
    S1 Architecture va pipeline draft       :done,    s1, after s0, 7d
    S2 Proposal (milestone)                 :milestone, s2, after s1, 0d

    section Cac tang hoc
    S3 Layer1 Body + Component5             :active,  s3, 2026-03-30, 7d
    S4 Layer2 Encoder + Component1          :         s4, after s3, 7d
    S5 Layer4 Composer + Component3         :         s5, after s4, 7d
    S6 Conditioning BODY/OCC + Ablation 2-3 :         s6, after s5, 7d

    section Tich hop va ban giao
    S7 Layer5 Customization + E2E + FastAPI :         s7, after s6, 7d
    S8 Gradio demo + user study             :         s8, after s7, 7d
    S9 Layer0 Preference + ablation + report:         s9, after s8, 7d
    Final Report (milestone)                :milestone, fin, after s9, 0d
```

---

## 11. Experiment Cycle — Lưới Ablation một trục (Sprint = Experiment Cycle)

```mermaid
flowchart LR
    CFG["configs/&lt;axis&gt;/*.yaml<br/>moi file = 1 thi nghiem"]

    CLI["om-exp sweep configs/&lt;axis&gt;/<br/>--out-csv docs/experiments/ablation_&lt;axis&gt;.csv"]
    CFG --> CLI

    subgraph RUNNER["runner.execute(cfg) — voi moi config"]
        direction TB
        SEED["set_seed(cfg.seed)"]
        WB["start W&B run — group=sprint · job_type=axis"]
        LOAD["load dataset (max_rows cap) + build_encoder"]
        TRAIN["train (contrastive / composer / preference)"]
        EVALR["evaluate to metrics dict"]
        SEED --> WB --> LOAD --> TRAIN --> EVALR
    end
    CLI --> SEED

    CSV[/"ablation_&lt;axis&gt;.csv — name la row key"/]
    WBCHART["W&B charts — tu dong so sanh cac run"]
    EVALR --> CSV
    EVALR --> WBCHART

    subgraph AXES["4 truc thi nghiem — moi sprint quet DUNG 1 truc"]
        direction TB
        AX1["Model — encoder kind/checkpoint"]
        AX2["Dataset type — hf_id + config"]
        AX3["Rows scaling — max_rows 5K/25K/100K/all"]
        AX4["Conditioning — use_body / use_occ"]
    end
    AXES -.->|"chon 1 truc, co dinh phan con lai"| CFG

    classDef hot fill:#fff3e0,stroke:#e67e22
    class CLI,WBCHART hot
```

---

## Ghi chú render

- **GitHub / VS Code:** hiển thị trực tiếp khi mở file `.md` này.
- **Xuất ảnh cho slide:** dán từng khối ` ```mermaid ` vào <https://mermaid.live> → Export PNG/SVG.
- Sơ đồ **1, 5a, 5b, 6** là "đinh" cho phần deep-dive model — nên phóng to full slide.
- Sơ đồ **2, 3** cho phần data & training pipeline.
- Sơ đồ **10** mở đầu phần Scrum/XP để hội đồng thấy quy trình sinh ra kiến trúc.
