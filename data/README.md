# Local Dataset Folder

Dataset files under `data/` are local artifacts and are intentionally ignored by Git.

For the full sharing/restore guide, see:

```text
docs/datasets/README.md
```

Expected dataset snapshot layout:

```text
data/custom/catalog/catalog_metadata.parquet
data/custom/catalog/item_store_links.parquet
data/custom/catalog/images/
data/custom/outfits/generated_outfits.parquet
data/cache/store_registry.db
```

Validate after copying a dataset snapshot:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.quality
```

Regenerate generated outfit KB:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60
```
