"""Initialise databases required by v3.1-lite.

Creates:
  - Qdrant `outfits` collection (vector dim verified from OT-labse checkpoint,
    do NOT hardcode — see Kien_truc_v3.1.md §3.5).
  - Payload indexes on: occasion, style, body_shapes_fit, price_tier, season, has_vn_store.
  - SQLite cache `data/cache/gemini_tagging.db` for diskcache (LLM tagging in Tầng 1).
  - Data directories (`data/custom/`, `data/kb/`, `data/stylist/`, `data/eval/`).

Usage:
    uv run python scripts/setup_databases.py --vector-dim 768
    uv run python scripts/setup_databases.py --vector-dim 768 --skip-qdrant
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent

from outfitmatch.kb.qdrant_index import PAYLOAD_INDEX_FIELDS  # noqa: E402


# ── Qdrant outfits collection (v3.1-lite Tầng 3) ───────────────────────────────

def setup_qdrant(vector_dim: int, host: str, port: int) -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams
    except ImportError:
        print("[Qdrant] qdrant-client not installed — skipping")
        return

    client = QdrantClient(host=host, port=port, timeout=10)

    try:
        existing = {c.name for c in client.get_collections().collections}
    except Exception as e:
        print(f"[Qdrant] Cannot connect to {host}:{port} — {e}")
        print("         Start: docker compose up qdrant -d")
        return

    if "outfits" not in existing:
        client.create_collection(
            collection_name="outfits",
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"[Qdrant] Created collection 'outfits' (dim={vector_dim}, Cosine)")
    else:
        info = client.get_collection("outfits")
        print(f"[Qdrant] Collection 'outfits' exists — {info.points_count} points")

    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index("outfits", field, PayloadSchemaType.KEYWORD)
            print(f"[Qdrant] Payload index ready: {field}")
        except Exception:
            pass


# ── SQLite cache for Gemini Flash LLM-tagging ──────────────────────────────────

def setup_sqlite() -> None:
    db_path = ROOT / "data" / "cache" / "gemini_tagging.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS outfit_tags (
            outfit_id     TEXT PRIMARY KEY,
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
    parser = argparse.ArgumentParser(description="Initialise v3.1-lite databases")
    parser.add_argument(
        "--vector-dim", type=int, required=False, default=None,
        help="OT-labse outfit_embedding dim (read from checkpoint config — Sprint 1).",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--skip-qdrant", action="store_true")
    args = parser.parse_args()

    print("=== OutfitMatch v3.1-lite — Database Setup ===\n")
    setup_directories()
    setup_sqlite()

    if args.skip_qdrant:
        print("[Qdrant] Skipped (--skip-qdrant)")
    elif args.vector_dim is None:
        print("[Qdrant] Skipped — pass --vector-dim once you verified the OT-labse dim")
    else:
        setup_qdrant(args.vector_dim, args.host, args.port)

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
