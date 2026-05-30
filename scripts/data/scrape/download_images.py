"""Bulk-download item images referenced by NormalizedItem.image_url.

Idempotent: skips files that already exist on disk. Failed downloads are
logged and reported so the orchestrator can drop the offending rows from
the catalog (we don't want catalog entries pointing at missing images).
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .base import IMAGE_DIR, REPO_ROOT, download_image, new_client
from .normalize import NormalizedItem

logger = logging.getLogger(__name__)


def download_all(items: list[NormalizedItem], *, client: httpx.Client | None = None) -> set[str]:
    """Download every item's primary image.

    Returns the set of item_ids that successfully landed on disk.
    """
    owned = client is None
    if client is None:
        client = new_client()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ok: set[str] = set()
    try:
        for it in items:
            dest = Path(it.image_path)
            if not dest.is_absolute():
                dest = REPO_ROOT / dest
            if download_image(client, it.image_url, dest):
                ok.add(it.item_id)
            else:
                logger.warning("image fail %s ← %s", it.item_id, it.image_url)
        return ok
    finally:
        if owned:
            client.close()
