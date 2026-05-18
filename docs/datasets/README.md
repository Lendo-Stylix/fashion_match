# Dataset Guide — OutfitMatch

> Đây là tài liệu tổng quan về tất cả dataset theo từng phase. Đọc file chi tiết của từng phase trước khi thu thập hoặc bổ sung dữ liệu.

---

## Tổng quan theo Phase

| Phase | Sprint | Dataset cần | File chi tiết |
|---|---|---|---|
| **1A — Body Pipeline** | S3, S6 | Full-body images + body shape labels | [BODY_PIPELINE.md](BODY_PIPELINE.md) |
| **1B — Catalog Encoder** | S4, S5 | Item images + text descriptions | [CATALOG_ENCODER.md](CATALOG_ENCODER.md) |
| **1C — Outfit Composer** | S5, S6, S7 | Outfit sets + compatibility + occasion labels | [OUTFIT_COMPOSER.md](OUTFIT_COMPOSER.md) |
| **1D — Evaluation** | S8, S9 | User study responses + LLM-as-judge | [USER_STUDY.md](USER_STUDY.md) |

---

## Cấu trúc thư mục data

```
data/
├── raw/                        # Dữ liệu gốc — không sửa sau khi download
│   ├── body/                   # Ảnh full-body + body_labels.csv
│   ├── catalog/                # Ảnh item + catalog_metadata.parquet
│   ├── outfits/                # Outfit sets + outfits.jsonl
│   └── occasion_cache/         # SQLite cache của Gemini labels
├── custom/                     # Dữ liệu tự thu thập (cùng schema với raw/)
│   ├── body/                   # Theo BODY_PIPELINE.md §Custom Collection
│   ├── catalog/                # Theo CATALOG_ENCODER.md §Custom Collection
│   └── outfits/                # Theo OUTFIT_COMPOSER.md §Custom Collection
└── processed/                  # Generated files — không commit (DVC tracked)
    ├── catalog_index.qdrant/   # Qdrant snapshot
    ├── catalog_embeddings.npy  # Pre-computed embeddings
    └── occasion_labels.parquet # Processed Gemini labels
```

---

## Nguồn HuggingFace đã verified (dùng ngay)

| HF Dataset | Rows | Size | Phase |
|---|---:|---:|---|
| `Marqo/deepfashion-inshop` | 52.6K | 216 MB | 1B |
| `Marqo/deepfashion-multimodal` | 42.5K | 153 MB | 1B |
| `Marqo/fashion200k` | 201.6K | 3.5 GB | 1B |
| `owj0421/polyvore-outfits` | 413.8K | ~50 MB | 1C |

---

## Khi bổ sung data tự thu thập

1. Đặt file vào `data/custom/<phase>/` — KHÔNG đặt vào `data/raw/`.
2. Validate schema: `uv run python scripts/validate_custom_data.py --phase <1A|1B|1C>`.
3. Merge vào raw: `uv run python scripts/merge_custom_data.py --phase <1A|1B|1C>`.
4. Commit DVC: `dvc add data/raw/ && git add data/raw.dvc && git commit`.

**Không bao giờ commit ảnh trực tiếp lên git** — dùng DVC cho tất cả file `data/`.
