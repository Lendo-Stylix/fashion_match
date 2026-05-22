"""Knowledge Base builder for v3.1-lite.

Offline pipeline (run once):
  1. embedding.py  — extract item embeddings via OutfitTransformer-labse
  2. generation.py — FITB+beam (70%) + random+score (30%) combo generation
  3. scoring.py    — re-score every outfit with OT compatibility score
  4. tagging.py    — Gemini Flash metadata tagging (occasion, style, …)

See Kien_truc_v3.1.md §3 for full specification.
"""
from outfitmatch.kb.schema import ItemRecord, OutfitRecord

__all__ = ["ItemRecord", "OutfitRecord"]
