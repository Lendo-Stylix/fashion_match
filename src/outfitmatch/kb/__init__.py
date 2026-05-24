"""Knowledge Base builder for v3.1-lite (Tầng 1).

Offline pipeline (run once):
  1. embedding.py     — extract item embeddings via OutfitTransformer-labse
  2. generation.py    — FITB+beam (70%) + random+score (30%) combo generation
  3. scoring.py       — re-score every outfit with OT compatibility score
  4. tagging.py       — Gemini Flash metadata tagging (occasion, style, …)
  5. qdrant_index.py  — push KB to Qdrant `outfits` collection (Sprint 5)

See Kien_truc_v3.1.md §3 for full specification.
"""

from outfitmatch.kb.schema import ItemRecord, OutfitRecord

__all__ = ["ItemRecord", "OutfitRecord"]
