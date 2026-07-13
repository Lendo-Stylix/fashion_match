"""Stable outfit id helpers (Fix D).

Kept in its own module with no internal imports so both ``assemble_record`` and
``generation`` can use it without creating a circular import.
"""

from __future__ import annotations

import uuid

NS = uuid.NAMESPACE_URL


def stable_outfit_id(item_ids: list[str]) -> str:
    """Stable outfit_id derived from the exact item set (Fix D).

    Previously outfit_id was ``OF_{index:05d}`` -- a per-call positional index
    that reset every retrieval run, so the same outfit got different IDs. Now we
    hash the sorted item_id set, keeping the ``OF_`` prefix so the stylist
    hallucination regex (validation.py: ``\\bOF_[0-9A-Za-z]{5,}\\b``) still matches.
    """
    digest = uuid.uuid5(NS, "|".join(sorted(item_ids))).hex[:8]
    return "OF_" + digest
