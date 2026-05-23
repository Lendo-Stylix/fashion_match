# OutfitMatch — Sơ đồ Mermaid v3.1-lite + 6-layer (Thuyết trình)

> Tài liệu đi kèm `PHAN_TICH_KIEN_TRUC_MODEL.md`. Mỗi sơ đồ render được trực tiếp trên GitHub, VS Code (Markdown Preview Mermaid), hoặc dán vào <https://mermaid.live> để xuất PNG/SVG đưa vào slide.
>
> **Mục lục v3.1-lite (sơ đồ mới — ưu tiên thuyết trình):**
> - V1. Kiến trúc 4 tầng v3.1-lite (System Overview)
> - V2. Inference Pipeline v3.1-lite — sequence diagram 7 bước
> - V3. KB Build Pipeline (Tầng 1) — 6 bước offline
> - V4. Controlled Vocabulary — chống lỗi enum mismatch
>
> **Mục lục 6-layer (grading experiments — giữ nguyên phía dưới):**
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
> 12. Related Work Lineage — paper nào truyền cảm hứng tầng nào
> 13. Gap Analysis — Prior Work vs OutfitMatch (quadrant chart)
> 14. Per-Layer Performance Measurement Framework
> 15. Ablation Design — 4 thí nghiệm kiểm soát

---

---

## V1. Kiến trúc 4 tầng v3.1-lite (System Overview)

```mermaid
flowchart TD
    IN(["INPUT: text + optional selfie + quiz answers"])

    subgraph T1["TẦNG 1 — Outfit Knowledge Base  ·  src/outfitmatch/kb"]
        direction TB
        T1A["OutfitTransformer-labse frozen\nFITB+Beam (70%) + Random+Score (30%)"]
        T1B["Re-score ALL outfits with OT compatibility"]
        T1C["Gemini Flash tagging → occasion / style / body / season\n(enum-constrained — vocab.py)"]
        T1A --> T1B --> T1C
    end

    subgraph T2["TẦNG 2 — Conversational Stylist  ·  src/outfitmatch/stylist"]
        direction TB
        T2A["Qwen3-VL-8B + LoRA nhẹ (3-5K hội thoại)\nParse intent · hỏi lại khi thiếu info"]
        T2B["Tool-call search_outfits(occasion, style, body_shape, price_max)\nvalidation layer: check outfit_id"]
        T2A --> T2B
    end

    subgraph T3["TẦNG 3 — Retrieval Engine  ·  Qdrant"]
        direction TB
        T3A["Filter metadata: occasion, style, body_shapes_fit\nprice_tier, has_vn_store=True, exclude_colors"]
        T3B["Sort by compatibility_score (precomputed)\n+ diversity penalty → Top 30-50"]
        T3A --> T3B
    end

    subgraph T4["TẦNG 4 — Personalization  ·  src/outfitmatch/quiz"]
        direction TB
        T4A["Quiz 5 câu → PreferenceProfile\nstyle · occasion · màu · budget · height/weight"]
        T4B["Rule-based re-rank: additive score\n→ Top 3-5 outfits"]
        T4A --> T4B
    end

    OUT(["OUTPUT: Top 3-5 outfits + store VN + giá VND + link mua\n+ giải thích tiếng Việt cá nhân hóa"])

    IN --> T2A
    T1C -.->|"KB 5-20K outfits (offline)"| T3A
    T2B -->|"search filters"| T3A
    T3B -->|"30-50 candidates"| T4A
    T4B --> OUT

    classDef tier fill:#eef4ff,stroke:#3366cc,stroke-width:1.5px
    class T1,T2,T3,T4 tier
```

---

## V2. Inference Pipeline v3.1-lite — Sequence Diagram 7 bước

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant API as pipeline.py
    participant QW as Tầng 2 Qwen3-VL
    participant QD as Tầng 3 Qdrant
    participant RR as Tầng 4 Re-rank
    participant VAL as Validation Layer

    U->>API: text + optional selfie + quiz answers
    API->>QW: parse intent (height, weight, occasion, style, missing_info[])
    QW-->>API: {parsed_fields} hoặc follow-up question

    alt Thiếu thông tin bắt buộc
        API-->>U: Qwen hỏi lại
    end

    API->>QW: generate tool call search_outfits(filters)
    QW-->>API: search_outfits({occasion, style, body_shape, price_max})
    API->>QD: filter metadata + sort by compatibility_score
    QD-->>API: 30-50 OutfitRecord candidates

    API->>RR: rerank_by_preference(outfits, profile, top_k=5)
    RR-->>API: Top 3-5 OutfitRecord

    API->>VAL: validate_response(explanation, valid_outfit_ids)
    VAL-->>API: (is_valid, invalid_ids)

    alt Có outfit_id bịa (hallucination)
        API->>QW: retry without invalid IDs
    end

    API-->>U: Top 3-5 outfits + ảnh + store + giá + link + giải thích VI
    Note over U,VAL: E2E target: < 5-8s trên GPU (streaming UX)
```

---

## V3. KB Build Pipeline (Tầng 1) — 6 bước Offline

```mermaid
flowchart TD
    SRC["VN Store Catalog\nYODY · Canifa · Format · The Blues\nUniqlo VN · Zara VN · H&M VN · Libé · HNOSS"]

    S1["Bước 1 — Ingestion & Preprocessing\nScrape → normalize schema → resize ảnh\nGhép title_vi + desc_vi cho text tower"]
    S2["Bước 2 — Item Embedding Extraction (offline)\nOT-labse Vision+Text encoder → vector\nLưu Parquet · xác minh OUTFIT_EMBED_DIM từ checkpoint"]
    S3["Bước 3 — Candidate Generation\n70% FITB+Beam (beam=3, top-k sampling)\n30% Random+Score (OT pre-filter, không phải CLIP)"]
    S4["Bước 4 — Re-scoring BẮT BUỘC\nMọi outfit OT re-score compatibility\nChỉ giữ outfit ≥ ngưỡng (chốt Sprint 3)"]
    S5["Bước 5 — Gemini Flash Tagging\nGán occasion/style/body_shapes_fit/season\nValidate vs vocab.py — reject invalid values"]
    S6["Bước 6 — Index vào Qdrant\nCollection outfits · payload indexes\n5-20K outfits (chất lượng > số lượng)"]

    SRC --> S1 --> S2 --> S3 --> S4 --> S5 --> S6

    NOTE1["⚠️ Re-score là bắt buộc:\nFITB/beam chỉ tối ưu cục bộ\nkhông đảm bảo hài hòa toàn cục"]
    S4 -.-> NOTE1

    NOTE2["3 data stream độc lập:\n· KB: VN store items\n· Grading eval: Polyvore\n· LoRA training: synthetic convs"]
    S6 -.-> NOTE2

    classDef step fill:#fff3e0,stroke:#e67e22
    class S1,S2,S3,S4,S5,S6 step
```

---

## V4. Controlled Vocabulary — Chống lỗi Enum Mismatch

```mermaid
flowchart LR
    VOCAB["vocab.py\n(nguồn sự thật duy nhất)\nOCCASION · STYLE · BODY_SHAPE\nSEASON · PRICE_TIER · ITEM_CATEGORY · SKIN_TONE"]

    T1TAG["Tầng 1 Gemini tagging\nprompt chứa enum list từ vocab.py\nvalidate output trước khi ghi KB"]
    T2TOOL["Tầng 2 Qwen3-VL\nsearch_outfits tool parameters\nenum: list(OCCASION) từ vocab.py"]
    T3IDX["Tầng 3 Qdrant\npayload index field values\nphải match enum trong vocab.py"]

    VOCAB --> T1TAG
    VOCAB --> T2TOOL
    VOCAB --> T3IDX

    BUG["❌ Lỗi v3.0:\nGemini gán 'dáng quả lê' (VI)\nQdrant filter dùng 'pear' (EN)\n→ filter trả 0 kết quả"]
    FIX["✅ Sửa v3.1-lite:\nMọi internal value = English snake_case\nVietnamese CHỈ ở *_LABELS_VI (UI)"]

    BUG --> FIX
    FIX --> VOCAB

    classDef fix fill:#e8f5e9,stroke:#2e7d32
    classDef bug fill:#ffebee,stroke:#c62828
    class FIX fix
    class BUG bug
```

---

## Sơ đồ 6-layer — Grading Experiments

> Các sơ đồ dưới đây mô tả kiến trúc 6-layer dùng cho encoder ablations và academic deliverables.
> Hệ thống sản phẩm (v3.1-lite) được mô tả ở các sơ đồ V1–V4 phía trên.

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

## 12. Related Work Lineage — Paper nào truyền cảm hứng tầng nào

> Sơ đồ cho thấy OutfitMatch không "phát minh lại từ đầu" mà xây trên nền các SOTA đã có — và mở rộng ở đâu.

```mermaid
flowchart LR
    subgraph ENC["Nhom 1 — Encoder / CLIP Family"]
        CLIP["CLIP\nRadford et al. 2021\nOpenAI\ndual-tower + InfoNCE loss"]
        SIGLIP["SigLIP\nZhai et al. 2023 arxiv:2303.15343\nGoogle Research\nsigmoid loss thay softmax"]
        FCLIP["FashionCLIP\nChia et al. 2022\ndomain CLIP fashion"]
        MSIGLIP["marqo-fashionSigLIP\nMarqo 2023-2024\nSOTA fashion retrieval\n7 fashion datasets SigLIP"]
        CLIP --> FCLIP
        CLIP --> MSIGLIP
        SIGLIP --> MSIGLIP
    end

    subgraph COMPAT["Nhom 2 — Outfit Compatibility"]
        BILSTM["Bi-LSTM Compat\nHan et al. ACM MM 2017\nordered sequence outfit\nPolyvore dataset"]
        VASILEVA["Type-Aware Embedding\nVasileva et al. ECCV 2018\nPolyvore disjoint/nondisjoint\nFITB + AUC metric definition"]
        OT["OutfitTransformer\nSarkar et al. 2022\narXiv:2204.04812\nSet Transformer - CLS token"]
        BILSTM --> OT
        VASILEVA --> OT
    end

    subgraph BODY_GRP["Nhom 3 — Body-Aware Fashion"]
        VIBE["ViBE\nHsiao and Grauman CVPR 2020\nbody shape diversity\nflattering labels"]
        YOLO["YOLOv8-pose\nUltralytics 2023\nCOCO-17 keypoints\nPython 3.13 compatible"]
    end

    subgraph PREF_GRP["Nhom 4 — Preference Learning"]
        BT["Bradley-Terry 1952\npairwise comparison\nP(A>B) = sigmoid(s_A - s_B)"]
        RLHF["InstructGPT - RLHF\nOuyang et al. NeurIPS 2022\ninstruction-conditional ranking"]
        BT --> RLHF
    end

    subgraph OM["OutfitMatch — dong gop cua du an"]
        L2["Layer 2\nCatalog Encoder\nfine-tune fashionSigLIP"]
        L1["Layer 1\nBody Pipeline\nYOLO + rule classifier"]
        L4["Layer 4\nOutfitTransformer\n+ BODY / OCC / PREF tokens"]
        L0["Layer 0\nPreference Structuring\nGemini + conditional BT"]
    end

    MSIGLIP -->|"PRIMARY encoder\nfine-tune"| L2
    FCLIP -->|"ablation baseline"| L2
    SIGLIP -->|"training loss"| L2

    VIBE -->|"body shape concept"| L1
    YOLO -->|"pose extractor"| L1

    OT -->|"tham chieu kien truc\nmo rong conditioning tokens"| L4
    BILSTM -->|"baseline B2"| L4
    VASILEVA -->|"dataset + metric"| L4

    BT -->|"pairwise_bt_loss"| L0
    RLHF -->|"preference post-training concept"| L0

    classDef prior fill:#e3f2fd,stroke:#1565c0
    classDef om fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    class CLIP,SIGLIP,FCLIP,MSIGLIP,BILSTM,VASILEVA,OT,VIBE,YOLO,BT,RLHF prior
    class L0,L1,L2,L4 om
```

---

## 13. Gap Analysis — Prior Work vs OutfitMatch

```mermaid
quadrantChart
    title Fashion Recommendation Capability Coverage
    x-axis "Chi retrieval" --> "Retrieval + Composition"
    y-axis "Khong co personalization" --> "Co body + occasion + preference"
    quadrant-1 "Ideal - OutfitMatch zone"
    quadrant-2 "Personalized nhung khong compose"
    quadrant-3 "Neither"
    quadrant-4 "Compose nhung generic"
    CLIP-ZS: [0.1, 0.05]
    FashionSigLIP-ZS: [0.25, 0.05]
    Bi-LSTM-2017: [0.5, 0.1]
    OutfitTransformer-2022: [0.75, 0.15]
    GPT-4V-stylist: [0.35, 0.6]
    OutfitMatch: [0.85, 0.85]
```

---

## 14. Per-Layer Performance Measurement Framework

> Mỗi tầng có bộ metric riêng. Sơ đồ này minh họa "ai đo gì" — dùng cho slide mở đầu phần Performance Evaluation.

```mermaid
flowchart TD
    subgraph L0["Layer 0 — Preference Structuring"]
        M0["JSON parse rate<br/>slot coverage rate<br/>cache hit rate<br/>latency ms<br/>body fallback rate"]
    end

    subgraph L1["Layer 1 — Body Shape Classifier"]
        M1["keypoint detection rate<br/>5-class accuracy — manual 50 anh<br/>confusion matrix 5x5<br/>keypoint confidence distribution"]
    end

    subgraph L2["Layer 2 — Catalog Encoder"]
        M2["Recall@1/5/10 · mAP<br/>SigLIP loss curve vs epoch<br/>t-SNE embedding space<br/>intra vs inter class similarity"]
    end

    subgraph L3["Layer 3 — Qdrant Retrieval"]
        M3["filter precision — zero violation<br/>coverage rate after filter<br/>ANN search latency ms"]
    end

    subgraph L4["Layer 4 — OutfitTransformer"]
        M4["FITB accuracy — target >= 55%<br/>Compatibility AUC — target >= 0.85<br/>Body-cond Precision@5 — +10pp<br/>Pref pairwise accuracy >= 0.70<br/>Flip consistency >= 0.60"]
    end

    subgraph E2E["System E2E"]
        ME["Latency per step — stacked bar<br/>Total E2E — target < 3s<br/>LLM-as-judge Gemini — mean >= 3.5/5<br/>User study Likert 1-5 — 3 dimensions"]
    end

    L0 --> L1 --> L2 --> L3 --> L4 --> E2E

    BL["Baselines bat buoc so sanh<br/>B1: CLIP-ZS + random composition<br/>B2: FashionSigLIP-ZS + Bi-LSTM<br/>B3: GPT-4V zero-shot stylist"]
    E2E -.->|"so sanh"| BL

    classDef metric fill:#e3f2fd,stroke:#1565c0
    classDef sys fill:#fce4ec,stroke:#880e4f
    class L0,L1,L2,L3,L4 metric
    class E2E,BL sys
```

---

## 13. Ablation Design — 4 Thí nghiệm Kiểm soát

> Mỗi ablation quét DUNG 1 biến, giữ cố định tất cả biến còn lại. Sơ đồ minh họa cách mỗi ablation chứng minh đóng góp của 1 component.

```mermaid
flowchart TD
    START(["Encoder fine-tuned — Base config<br/>FashionSigLIP-ZS · Polyvore-nondisjoint · cond_body_occ"])

    subgraph A1["Ablation 1 — Encoder Variants"]
        direction LR
        E1["CLIP-ZS<br/>floor"]
        E2["FashionCLIP-ZS<br/>domain CLIP"]
        E3["FashionSigLIP-ZS<br/>SigLIP pretrained"]
        E4["FashionSigLIP-FT<br/>fine-tuned — our contribution"]
        E1 --> E2 --> E3 --> E4
    end

    subgraph A2["Ablation 2 — Body Conditioning"]
        direction LR
        B1["cond_none<br/>khong co BODY token"]
        B2["cond_body<br/>co BODY token"]
        B1 --> B2
    end

    subgraph A3["Ablation 3 — Occasion Conditioning"]
        direction LR
        O1["cond_body<br/>khong co OCC token"]
        O2["cond_body_occ<br/>co OCC token"]
        O1 --> O2
    end

    subgraph A4["Ablation 4 — Decoding Strategy"]
        direction LR
        D1["Greedy decoding<br/>chon item cao nhat tung slot"]
        D2["Beam search B=3<br/>giu top-3 partial outfit"]
        D1 --> D2
    end

    START --> A1
    START --> A2
    START --> A3
    START --> A4

    R1["Metric: Recall@1/5/10 · mAP<br/>Ket qua ky vong: FT > ZS > CLIP"]
    R2["Metric: Body-cond Precision@5<br/>Ket qua ky vong: +10pp vs cond_none"]
    R3["Metric: FITB acc phan theo occasion<br/>Ket qua ky vong: gain ro nhat tren formal/sport"]
    R4["Metric: FITB acc + outfit diversity<br/>Ket qua ky vong: Beam cao hon ca 2 metric"]

    A1 --> R1
    A2 --> R2
    A3 --> R3
    A4 --> R4

    classDef abl fill:#fff9c4,stroke:#f9a825
    classDef res fill:#e8f5e9,stroke:#2e7d32
    class A1,A2,A3,A4 abl
    class R1,R2,R3,R4 res
```

---

## Ghi chú render

- **GitHub / VS Code:** hiển thị trực tiếp khi mở file `.md` này.
- **Xuất ảnh cho slide:** dán từng khối ` ```mermaid ` vào <https://mermaid.live> → Export PNG/SVG.
- Sơ đồ **1, 5a, 5b, 6** là "đinh" cho phần deep-dive model — nên phóng to full slide.
- Sơ đồ **2, 3** cho phần data & training pipeline.
- Sơ đồ **10** mở đầu phần Scrum/XP để hội đồng thấy quy trình sinh ra kiến trúc.
