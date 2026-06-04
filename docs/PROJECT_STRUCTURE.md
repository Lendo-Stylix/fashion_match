# Project Structure

OutfitMatch uses a source-first layout. **Primary KB path is now graph-based**: catalog item nodes + `item_edges.parquet` + Qdrant `items` seed filter. Materialized outfits remain only for legacy comparison.

```text
src/outfitmatch/             # Importable application/library code
  kb/                        # Tầng 1: graph KB + legacy materialized helpers
    catalog.py               # Scraped catalog -> ItemRecord
    embedding.py             # OT-labse item embedding extraction
    pair_scoring.py          # Pairwise compatibility scorer
    graph.py                 # Sparse item-compatibility graph builder
    graph_store.py           # item_edges.parquet + Qdrant `items`
    traversal.py             # Clique-safe outfit assembly from seed items
    assemble_record.py       # Assembled items -> OutfitRecord
    graph_eval.py            # Coverage/coherence/reuse report
    generation.py            # Legacy materialized generation helpers
    scoring.py               # Legacy materialized scoring helpers
    tagging.py               # Legacy Gemini outfit tagging
    qdrant_index.py          # Legacy Qdrant `outfits` collection
  retrieval.py               # Tầng 3: seed filter + traversal + post-filter
  stylist/                   # Tầng 2: Qwen tool schema + validation + model/data
  quiz/                      # Tầng 4: onboarding quiz + rerank + sizing
  metrics/                   # Offline eval metrics (Polyvore + graph FITB recall)
  ui/                        # Gradio demo entry points

scripts/                     # Operational commands, not core library APIs
  data/
    scrape/                  # VN store scraping + raw cache + quality gate
    kb/
      build_graph.py         # Primary graph KB build CLI
      eval_graph.py          # Graph grading / ablation CLI
      generate_outfits.py    # Legacy materialized outfit builder
  setup_databases.py         # Local DB / Qdrant setup helpers

tests/                       # Mirrors source/tooling domains
  kb/                        # Graph/materialized KB unit tests
  data/scrape/               # Scraper and catalog-quality tests
  test_*.py                  # Cross-layer tests for pipeline/quiz/stylist/vocab

docs/                        # Architecture, datasets, experiment guide, feature log
.pi/                         # Project-level Pi agent/rule/skill configuration

data/                        # Local/generated artifacts
  custom/catalog/*.parquet   # Scraped catalog metadata/link tables
  custom/catalog/images/     # Downloaded product images
  custom/graph/item_edges.parquet   # Canonical graph baseline (tracked)
  custom/outfits/*.parquet   # Legacy materialized outfit snapshots
  cache/                     # Raw HTTP cache + SQLite cache
```

Canonical commands:

```powershell
# Scrape / validate VN catalog
uv run python -m scripts.data.scrape.run --limit 20 --no-images --dry-run
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.scrape.quality

# Build / grade primary graph KB
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.build_graph --no-qdrant --limit-per-category 80
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.eval_graph --seeds 300 --occasion office

# Legacy materialized comparison path
PYTHONIOENCODING=utf-8 uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60

# Validate codebase
uv run ruff check scripts src tests
uv run pytest -q
uv run mypy scripts/data scripts/setup_databases.py src/outfitmatch
```
