# Dataset Guide — v3.1-lite

> Tài liệu data theo từng sprint v3.1-lite (4 tầng MVP). Đọc file chi tiết của từng sprint
> trước khi thu thập hoặc bổ sung dữ liệu.

---

## Ba luồng data độc lập (`Kien_truc_v3.1.md` §3.3)

| Luồng | Mục đích | Nguồn |
|---|---|---|
| **KB catalog** | Item → outfit recommendation cuối cùng cho user | **Scrape thủ công** từ store VN có chọn lọc |
| **OT grading eval** | Báo cáo FITB acc + Compat AUC (academic) | Polyvore (public benchmark) |
| **Stylist LoRA training** | Fine-tune Qwen3-VL hội thoại | Hội thoại synthetic sinh bằng Gemini Flash |

---

## Theo Sprint

| Sprint | Tầng | Dataset cần | Tham chiếu |
|---|---|---|---|
| **Sprint 0** | Setup | Spike thu thập item VN — chốt quy mô KB thực tế | [STORE_CATALOG_VN.md](STORE_CATALOG_VN.md) |
| **Sprint 1–2** | Tầng 1 KB | Item images + VN store catalog (scrape thủ công) | [STORE_CATALOG_VN.md](STORE_CATALOG_VN.md) |
| **Sprint 3–4** | Tầng 1 KB | Gemini Flash quota; (song song) Polyvore cho OT fine-tune | `Kien_truc_v3.1.md` §3.4, §3.6 |
| **Sprint 5** | Tầng 3 Retrieval | KB outfits đã index lên Qdrant | `kb/qdrant_index.py` |
| **Sprint 6–7** | Tầng 2 Stylist | 3–5K conversation synthetic (Gemini-generated) | `Kien_truc_v3.1.md` §4.2 |
| **Sprint 8** | E2E | Quiz UI + E2E integration test | — |
| **Sprint 9** | Eval | LLM-as-judge (Gemini) + 4 ablations | [`../EXPERIMENT_GUIDE.md`](../EXPERIMENT_GUIDE.md) |

---

## Cấu trúc thư mục `data/`

```
data/
├── custom/                       # Item ảnh + metadata scrape thủ công từ store VN
│   ├── catalog/
│   │   ├── images/               # item_custom_NNNNN.jpg
│   │   └── catalog_metadata.parquet   # schema: STORE_CATALOG_VN.md
│   └── outfits/
│       └── outfits.jsonl         # KB outfits sau bước 3-4 (FITB+Beam + tag)
├── kb/                           # Output build pipeline (Sprint 3-4)
│   ├── items_with_embeddings.parquet
│   ├── kb_greedy.parquet         # KB sinh bằng greedy decoding (ablation 4)
│   └── kb_beam.parquet           # KB sinh bằng beam decoding (ablation 4)
├── polyvore/                     # Download HF dataset cho OT eval (§3.6)
├── stylist/
│   └── conversations.jsonl       # Hội thoại synthetic Gemini (Sprint 6-7)
└── eval/
    └── recommend_results.jsonl   # Output E2E để LLM-judge (Sprint 9)
```

> Project chỉ đang là skeleton — các thư mục trên sẽ được tạo dần qua từng sprint.
> Dataset catalog sẽ scrape thủ công, không có pipeline auto-scrape trong repo.

---

## Stores VN — danh sách v3.1-lite

Catalog v3.1-lite chỉ lấy item từ store có ảnh per-item sạch, giá VND rõ ràng và có thể
mua tại VN:

| Loại | Store |
|---|---|
| **Local VN** | YODY, Canifa, Format, The Blues, Libé, Elise, Owen, HNOSS |
| **International chain tại VN** | Uniqlo VN, Zara VN, H&M VN |

**Loại khỏi MVP:** Musinsa, ZOZOTOWN, Taobao, YesStyle, Pinterest/Instagram —
xem `Kien_truc_v3.1.md` §3.3 (anti-scraping, ảnh outfit nguyên bộ không có per-item,
không có đường lấy hàng về VN).

Schema chi tiết, naming convention, quy trình validation: **[STORE_CATALOG_VN.md](STORE_CATALOG_VN.md)**.
