"""Initialise databases required by v3.1-lite (graph KB).

Creates:
  - Qdrant `items` collection (graph path, PRIMARY) — seed-node retrieval for
    Tầng 3 graph traversal. Vector dim verified from OT-labse item embedding
    (do NOT hardcode — see Kien_truc_v3.1.md §3.5).
  - Payload indexes on: category, gender, formality, price_tier, has_vn_store,
    in_stock, store_id.
  - Optional legacy `outfits` collection (materialized path) via --with-legacy-outfits.
  - SQLite cache `data/cache/gemini_tagging.db` for diskcache (LLM tagging in Tầng 1).
  - Data directories (`data/custom/`, `data/kb/`, `data/stylist/`, `data/eval/`).

Note: `scripts.data.kb.build_graph` provisions + indexes the `items` collection
end-to-end (dim inferred from real item embeddings). This script only pre-creates
empty collections / directories for a fresh environment.

Usage:
    uv run python scripts/setup_databases.py --vector-dim 768
    uv run python scripts/setup_databases.py --vector-dim 768 --skip-qdrant
    uv run python scripts/setup_databases.py --vector-dim 768 --with-legacy-outfits
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from outfitmatch.kb.graph_store import ITEM_PAYLOAD_INDEX_FIELDS
from outfitmatch.kb.qdrant_index import PAYLOAD_INDEX_FIELDS

ROOT = Path(__file__).parent.parent


# ── Qdrant collections ─────────────────────────────────────────────────────────


def _ensure_collection(
    client,
    name: str,
    vector_dim: int,
    index_fields: tuple[str, ...],
) -> None:
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"[Qdrant] Created collection '{name}' (dim={vector_dim}, Cosine)")
    else:
        info = client.get_collection(name)
        print(f"[Qdrant] Collection '{name}' exists — {info.points_count} points")

    for field in index_fields:
        try:
            client.create_payload_index(name, field, PayloadSchemaType.KEYWORD)
            print(f"[Qdrant] Payload index ready: {name}.{field}")
        except Exception:
            pass


def setup_qdrant(vector_dim: int, host: str, port: int, *, with_legacy_outfits: bool) -> None:
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("[Qdrant] qdrant-client not installed — skipping")
        return

    client = QdrantClient(host=host, port=port, timeout=10)

    try:
        client.get_collections()
    except Exception as e:
        print(f"[Qdrant] Cannot connect to {host}:{port} — {e}")
        print("         Start: docker compose up qdrant -d")
        return

    # PRIMARY: graph path — item seed nodes for Tầng 3 traversal.
    _ensure_collection(client, "items", vector_dim, ITEM_PAYLOAD_INDEX_FIELDS)

    # Legacy materialized path (kept for comparison only).
    if with_legacy_outfits:
        _ensure_collection(client, "outfits", vector_dim, PAYLOAD_INDEX_FIELDS)


# ── SQLite cache for Gemini Flash LLM-tagging ──────────────────────────────────


def setup_sqlite() -> None:
    db_path = ROOT / "data" / "cache" / "gemini_tagging.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS item_tags (
            item_id       TEXT PRIMARY KEY,
            occasion      TEXT,         -- JSON-encoded list of OCCASION enum values
            style         TEXT,         -- JSON-encoded list of STYLE enum values
            body_shapes   TEXT,         -- JSON-encoded list of BODY_SHAPE enum values
            season        TEXT,         -- JSON-encoded list of SEASON enum values
            color_palette TEXT,
            explanation_vi TEXT,
            model         TEXT DEFAULT 'gemini-2.0-flash',
            created_at    TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    print(f"[SQLite] Created cache: {db_path}")


# ── Data directories ──────────────────────────────────────────────────────────


def setup_directories() -> None:
    dirs = [
        "data/custom/catalog/images",
        "data/custom/graph",
        "data/custom/outfits",
        "data/kb",
        "data/polyvore",
        "data/stylist",
        "data/eval",
        "data/cache",
    ]
    for d in dirs:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        gitkeep = path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    print(f"[Dirs] Created {len(dirs)} data directories")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise v3.1-lite graph KB databases")
    parser.add_argument(
        "--vector-dim",
        type=int,
        required=False,
        default=None,
        help="OT-labse item_embedding dim (read from checkpoint config — Sprint 1).",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument(
        "--with-legacy-outfits",
        action="store_true",
        help="Also create the legacy materialized `outfits` collection.",
    )
    args = parser.parse_args()

    print("=== OutfitMatch v3.1-lite — Database Setup (graph KB) ===\n")
    setup_directories()
    setup_sqlite()

    if args.skip_qdrant:
        print("[Qdrant] Skipped (--skip-qdrant)")
    elif args.vector_dim is None:
        print("[Qdrant] Skipped — pass --vector-dim once you verified the OT-labse dim")
    else:
        setup_qdrant(
            args.vector_dim,
            args.host,
            args.port,
            with_legacy_outfits=args.with_legacy_outfits,
        )

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
