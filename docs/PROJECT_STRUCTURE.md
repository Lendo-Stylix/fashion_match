# Project Structure

OutfitMatch uses a source-first layout. Generated datasets are local artifacts and are ignored by Git.

```text
src/outfitmatch/             # Importable application/library code
  kb/                        # Tầng 1: catalog loading, embedding, outfit generation/scoring/eval
  stylist/                   # Tầng 2: Qwen tool schema + validation + model stubs
  quiz/                      # Tầng 4: onboarding quiz + preference re-rank
  metrics/                   # Offline eval metrics
  ui/                        # Gradio demo entry points

scripts/                     # Operational commands, not core library APIs
  data/
    scrape/                  # VN store scraping + raw catalog quality checks
    kb/                      # Generated outfit KB build commands
  setup_databases.py         # Qdrant/SQLite/data directory setup

tests/                       # Mirrors source/tooling domains
  kb/                        # Tầng 1 KB unit tests
  data/scrape/               # Scraper and catalog-quality tests
  test_*.py                  # Cross-layer tests for pipeline/quiz/stylist/vocab

docs/                        # Architecture, experiment guide, feature log, dataset schema notes
.pi/                         # Project-level Pi agent/rule/skill configuration

data/                        # Local/generated artifacts; datasets are ignored by Git
  custom/catalog/*.parquet   # Scraped catalog metadata/link tables (local)
  custom/catalog/images/     # Downloaded product images (local)
  custom/outfits/*.parquet   # Generated outfit KB tables (local)
  cache/                     # Raw HTTP cache + SQLite cache (local)
```

Canonical commands:

```powershell
# Scrape/validate raw VN catalog
uv run python -m scripts.data.scrape.run --limit 20 --no-images --dry-run
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.scrape.quality

# Build generated outfit combinations
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60

# Validate codebase
uv run ruff check scripts src tests
uv run pytest -q
uv run mypy scripts/data scripts/setup_databases.py src/outfitmatch
```
