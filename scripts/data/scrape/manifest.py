"""Scrape manifest: per-batch status for incremental, resumable scraping.

Records which (store, chunk) batches passed the gate and which were quarantined,
so ``run --rescrape-failed`` can re-run only the quality-gate failures.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.data.scrape.base import CATALOG_DIR
from scripts.data.scrape.batch_gate import BatchGateResult

MANIFEST_PATH: Path = CATALOG_DIR / "scrape_manifest.json"


@dataclass
class BatchRecord:
    store_id: str
    chunk_index: int
    status: str
    item_count: int
    blocking_codes: list[str]
    metrics: dict[str, float]
    updated_at: str
    raw_count: int = 0

    @property
    def batch_id(self) -> str:
        if self.chunk_index < 0:
            return f"{self.store_id}#ALL"
        return f"{self.store_id}#{self.chunk_index:03d}"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, BatchRecord]:
    """Load the manifest, returning an empty mapping when it doesn't exist."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: BatchRecord(**value) for key, value in raw.items()}


def save_manifest(records: dict[str, BatchRecord], path: Path = MANIFEST_PATH) -> None:
    """Persist manifest records as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: asdict(rec) for key, rec in sorted(records.items())}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_result(
    records: dict[str, BatchRecord],
    result: BatchGateResult,
    *,
    status: str,
    now: str,
    raw_count: int = 0,
) -> None:
    """Upsert one manifest record from a :class:`BatchGateResult`."""
    records[result.batch_id] = BatchRecord(
        store_id=result.store_id,
        chunk_index=result.chunk_index,
        status=status,
        item_count=result.item_count,
        blocking_codes=list(result.blocking_codes),
        metrics=dict(result.metrics),
        updated_at=now,
        raw_count=raw_count,
    )


def failed_batches(records: dict[str, BatchRecord]) -> list[str]:
    """Return batch IDs whose status is not ``passed``."""
    return sorted(batch_id for batch_id, record in records.items() if record.status != "passed")
