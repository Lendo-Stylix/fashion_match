# OutfitMatch — Sơ đồ Mermaid v3.1-lite (Thuyết trình)

> Mỗi sơ đồ render được trực tiếp trên GitHub, VS Code (Markdown Preview Mermaid),
> hoặc dán vào <https://mermaid.live> để xuất PNG/SVG đưa vào slide.
>
> **Mục lục:**
> - V1. Kiến trúc 4 tầng v3.1-lite (System Overview)
> - V2. Inference Pipeline v3.1-lite — sequence diagram 7 bước
> - V3. KB Build Pipeline (Tầng 1) — 6 bước offline
> - V4. Controlled Vocabulary — chống lỗi enum mismatch

---

## V1. Kiến trúc 4 tầng v3.1-lite (System Overview)

```mermaid
flowchart TD
    IN(["INPUT: text + optional selfie + quiz answers"])

    subgraph T1["TẦNG 1 — Outfit Graph KB  ·  src/outfitmatch/kb"]
        direction TB
        T1A["OutfitTransformer-labse frozen → item embedding"]
        T1B["pair_scoring + graph.py → sparse item-compat graph\n(category/gender/formality gated, top-K)"]
        T1C["graph_store.py → item_edges.parquet + Qdrant items nodes"]
        T1A --> T1B --> T1C
    end

    subgraph T2["TẦNG 2 — Conversational Stylist  ·  src/outfitmatch/stylist"]
        direction TB
        T2A["Qwen3-VL-8B + LoRA nhẹ (3-5K hội thoại)\nParse intent · hỏi lại khi thiếu info"]
        T2B["Tool-call search_outfits(occasion, style, body_shape, price_max)\nvalidation layer: check outfit_id"]
        T2A --> T2B
    end

    subgraph T3["TẦNG 3 — Retrieval Engine  ·  Qdrant items + traversal"]
        direction TB
        T3A["Filter seed item (top/dress): gender, formality→occasion\nin_stock, has_vn_store=True"]
        T3B["Graph traversal ráp clique → OutfitRecord\npost-filter style/price/colors → Top 30-50"]
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
    T1C -.->|"graph KB: items + edges (offline)"| T3A
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
    API->>QD: filter seed items → graph traversal ráp clique
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
    S2["Bước 2 — Item Embedding Extraction (offline)\nOT-labse Vision+Text encoder → vector\nLưu Parquet · xác minh ITEM_EMBED_DIM từ checkpoint"]
    S3["Bước 3 — Pair Scoring\npair_scoring.py → bounded edge weight\ngiữa item nodes co-wearable"]
    S4["Bước 4 — Graph Build (gated)\ngraph.py: edge chỉ khi category/gender/formality hợp lệ\ntop-K=15 mỗi partner-category, canonical src<dst"]
    S5["Bước 5 — Item formality + gender inference\n(suy từ title/store/garment prior)\nValidate vs vocab.py — reject invalid values"]
    S6["Bước 6 — Persist + Index\nitem_edges.parquet + Qdrant items collection\npayload indexes (category/gender/formality/...)"]

    SRC --> S1 --> S2 --> S3 --> S4 --> S5 --> S6

    NOTE1["⚠️ Hard constraint tách khỏi weight:\ngraph.py quyết định edge tồn tại\npair_scoring chỉ cho weight bị chặn"]
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
    T3IDX["Tầng 3 Qdrant items\npayload index field values\nphải match enum trong vocab.py"]

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

## Ghi chú render

- **GitHub / VS Code:** hiển thị trực tiếp khi mở file `.md` này.
- **Xuất ảnh cho slide:** dán từng khối ` ```mermaid ` vào <https://mermaid.live>
  → Export PNG/SVG.
- Sơ đồ **V1** mở đầu phần System Overview; **V2** cho deep-dive inference pipeline.
- Sơ đồ **V3** dành cho phần thuyết minh Tầng 1 (offline KB build).
- Sơ đồ **V4** chốt nguyên tắc "controlled vocabulary chống lỗi enum mismatch" — giải thích
  vì sao chia tách `*_LABELS_VI` và internal English enum.
