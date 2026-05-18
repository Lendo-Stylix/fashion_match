"""Initialize all databases required for the OutfitMatch project.

Creates:
  - data/raw/occasion_cache/occasion_cache.db  (SQLite — Gemini occasion labels)
  - Qdrant collection 'catalog' (768-dim Cosine) — requires Qdrant running on :6333

Usage:
    uv run python scripts/setup_databases.py
    uv run python scripts/setup_databases.py --skip-qdrant   # if Qdrant not running yet
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── SQLite occasion cache ──────────────────────────────────────────────────────

def setup_sqlite() -> None:
    db_path = ROOT / "data" / "raw" / "occasion_cache" / "occasion_cache.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS occasion_labels (
            outfit_id   TEXT PRIMARY KEY,
            occasion    TEXT NOT NULL,
            confidence  REAL,
            model       TEXT DEFAULT 'gemini-2.0-flash',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_occasion ON occasion_labels(occasion);
    """)

    conn.commit()
    conn.close()
    print(f"[SQLite] Created: {db_path}")


# ── Qdrant catalog collection ──────────────────────────────────────────────────

def setup_qdrant() -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        print("[Qdrant] qdrant-client not installed — skipping")
        return

    client = QdrantClient(host="localhost", port=6333, timeout=10)

    try:
        collections = {c.name for c in client.get_collections().collections}
    except Exception as e:
        print(f"[Qdrant] Cannot connect to localhost:6333 — {e}")
        print("         Start Qdrant with: docker run -p 6333:6333 qdrant/qdrant")
        return

    if "catalog" not in collections:
        client.create_collection(
            collection_name="catalog",
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print("[Qdrant] Created collection 'catalog' (768-dim, Cosine)")
    else:
        info = client.get_collection("catalog")
        print(f"[Qdrant] Collection 'catalog' already exists — {info.points_count} points")

    # Body shape collection (for future body-aware retrieval)
    if "body_shapes" not in collections:
        client.create_collection(
            collection_name="body_shapes",
            vectors_config=VectorParams(size=512, distance=Distance.COSINE),
        )
        print("[Qdrant] Created collection 'body_shapes' (512-dim, Cosine)")
    else:
        print("[Qdrant] Collection 'body_shapes' already exists")


# ── Data directories ──────────────────────────────────────────────────────────

def setup_directories() -> None:
    dirs = [
        "data/raw/body/images",
        "data/raw/catalog/images",
        "data/raw/outfits",
        "data/raw/occasion_cache",
        "data/raw/user_study/outfit_images",
        "data/custom/body/images",
        "data/custom/catalog/images",
        "data/custom/outfits",
        "data/processed",
    ]
    for d in dirs:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        # Keep empty dirs in git with .gitkeep
        gitkeep = path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    print(f"[Dirs] Created {len(dirs)} data directories")


# ── DVC init check ────────────────────────────────────────────────────────────

def check_dvc() -> None:
    dvc_dir = ROOT / ".dvc"
    if not dvc_dir.exists():
        print("[DVC]  Not initialized. Run: dvc init && dvc remote add -d gdrive gdrive://<folder-id>")
    else:
        print(f"[DVC]  Already initialized at {dvc_dir}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-qdrant", action="store_true",
                        help="Skip Qdrant setup (use if Docker not running)")
    args = parser.parse_args()

    print("=== OutfitMatch Database Setup ===\n")

    setup_directories()
    setup_sqlite()

    if not args.skip_qdrant:
        setup_qdrant()
    else:
        print("[Qdrant] Skipped (--skip-qdrant)")

    check_dvc()

    print("\nSetup complete.")
    print("Next steps:")
    print("  1. Start Qdrant:  docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant")
    print("  2. Init DVC:      dvc init && dvc remote add -d gdrive gdrive://<folder-id>")
    print("  3. Add data:      dvc add data/raw/ && git add data/raw.dvc")


if __name__ == "__main__":
    main()
