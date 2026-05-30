"""Seed `data/cache/store_registry.db` (SQLite) from config.STORES.

Schema follows docs/datasets/STORE_CATALOG_VN.md §3 exactly.

Idempotent: drops & recreates both tables on every run. Branches table is
populated empty for now — populated manually as physical store info is
collected.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from .base import REGISTRY_DB
from .config import STORES

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE stores (
    store_id      TEXT PRIMARY KEY,
    store_name    TEXT NOT NULL,
    store_type    TEXT NOT NULL,
    website       TEXT,
    price_tier    TEXT NOT NULL,
    target_gender TEXT NOT NULL,
    style_tags    TEXT,
    notes         TEXT
);
CREATE TABLE branches (
    branch_id  TEXT PRIMARY KEY,
    store_id   TEXT NOT NULL REFERENCES stores(store_id),
    city       TEXT NOT NULL,
    district   TEXT,
    address    TEXT,
    maps_url   TEXT,
    is_active  INTEGER DEFAULT 1
);
"""


def build_registry() -> int:
    REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB)
    try:
        cur = conn.cursor()
        cur.executescript("DROP TABLE IF EXISTS branches; DROP TABLE IF EXISTS stores;" + DDL)
        rows = [
            (
                s.store_id,
                s.store_name,
                s.store_type,
                s.website,
                s.price_tier,
                s.target_gender,
                json.dumps(list(s.style_tags), ensure_ascii=False),
                s.notes or None,
            )
            for s in STORES
        ]
        cur.executemany(
            "INSERT INTO stores VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
        conn.commit()
        logger.info("seeded %d stores → %s", len(rows), REGISTRY_DB)
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = build_registry()
    print(f"OK: {n} stores written to {REGISTRY_DB}")
