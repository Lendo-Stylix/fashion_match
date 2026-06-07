"""Knowledge Base for v3.1-lite (graph KB).

Graph path (current architecture):
  1. catalog.py     — load scraped catalog rows into ItemRecord
  2. embedding.py   — extract item embeddings via OutfitTransformer-labse
  3. pair_scoring.py — bounded edge weights between item nodes
  4. graph.py       — sparse item-compatibility graph (category/gender/formality gated)
  5. graph_store.py — item_edges.parquet + Qdrant `items` node index
  6. tagging.py     — Gemini item semantic tagging for graph nodes
  7. traversal.py   — clique-safe outfit assembly from seed items
  8. assemble_record.py — derive OutfitRecord tags from assembled items
  9. graph_eval.py  — GraphReport (coverage / coherence / reuse)

Legacy materialized path (kept for comparison, see build_outfits.py):
  generation.py + scoring.py + qdrant_index.py (`outfits` collection).

See Kien_truc_v3.1.md §3 and docs/ARCHITECTURE.md for the full specification.
"""

from outfitmatch.kb.schema import ItemRecord, OutfitRecord

__all__ = ["ItemRecord", "OutfitRecord"]
