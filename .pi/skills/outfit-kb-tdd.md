---
name: outfit-kb-tdd
description: TDD workflow for OutfitMatch KB outfit generation from scraped catalog
---

# OutfitMatch KB TDD

Use this skill when implementing OutfitMatch Knowledge Base generation.

1. Read `CLAUDE.md`, `Kien_truc_v3.1.md`, and `docs/ARCHITECTURE.md` sections relevant to Tầng 1 before changing KB code.
2. Write failing tests first for schema/quality/generation behavior.
3. Keep raw scraper outputs separate from KB outputs: raw items live in `data/custom/catalog/`; generated outfits live in `data/custom/outfits/` or `data/kb/`.
4. Valid outfit category rules are only:
   - `top + bottom + shoes`
   - `dress + shoes`
   Optional add-ons: `outerwear`, `bag`, `accessory`.
5. Generated `OutfitRecord.schema_version` must be `"3.1"`; `gen_method` must identify the method.
6. Do not use vector search for retrieval logic; generation/scoring can use the OT-compatible encoder/scorer adapter.
7. Run at least:
   - `uv run ruff check scripts src tests`
   - `uv run pytest -q`
   - `uv run mypy scripts/data/scrape src/outfitmatch`
