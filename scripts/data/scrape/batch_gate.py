"""Per-batch quality gate for the scraper.

A *batch* is a chunk of ``batch_size`` normalized items from a single store. The
batch gate reuses the row-level checks in :mod:`scripts.data.scrape.quality`
without writing temp parquet files. Failed batches are quarantined and never
promoted into the main catalog parquet.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from scripts.data.scrape.base import CATALOG_DIR, REPO_ROOT
from scripts.data.scrape.normalize import NormalizedItem, to_catalog_frame, to_links_frame
from scripts.data.scrape.quality import QualityReport, check_frames

QUARANTINE_DIR: Path = CATALOG_DIR / "quarantine"


@dataclass(frozen=True)
class GateThresholds:
    """Tunable thresholds for the batch gate."""

    batch_size: int = 250
    min_yield: float = 0.30


@dataclass(frozen=True)
class BatchGateResult:
    """Outcome of gating one normalized chunk."""

    store_id: str
    chunk_index: int
    item_count: int
    passed: bool
    report: QualityReport
    metrics: dict[str, float]
    blocking_codes: list[str] = field(default_factory=list)

    @property
    def batch_id(self) -> str:
        return f"{self.store_id}#{self.chunk_index:03d}"


def chunk_items[T](items: list[T], size: int) -> list[list[T]]:
    """Split ``items`` into chunks of ``size`` (size<=0 => a single chunk)."""
    if size <= 0:
        return [list(items)]
    return [items[i : i + size] for i in range(0, len(items), size)]


def yield_ok(n_items: int, n_raws: int, thresholds: GateThresholds) -> bool:
    """Return whether the normalize/raw yield is still acceptable."""
    if n_raws <= 0:
        return True
    return (n_items / n_raws) >= thresholds.min_yield


def gate_batch(
    items: list[NormalizedItem],
    *,
    store_id: str,
    chunk_index: int,
    thresholds: GateThresholds = GateThresholds(),
    repo_root: Path = REPO_ROOT,
    check_images: bool = True,
) -> BatchGateResult:
    """Run in-memory quality checks on one normalized chunk."""
    del thresholds  # reserved for future batch-level metrics
    report = check_frames(
        to_catalog_frame(items),
        to_links_frame(items),
        repo_root=repo_root,
        check_images=check_images,
    )
    blocking = sorted({issue.code for issue in report.issues if issue.level == "error"})
    unisex_share = (
        sum(1 for item in items if item.gender == "unisex") / len(items) if items else 0.0
    )
    return BatchGateResult(
        store_id=store_id,
        chunk_index=chunk_index,
        item_count=len(items),
        passed=not blocking,
        report=report,
        metrics={"unisex_share": round(unisex_share, 4)},
        blocking_codes=blocking,
    )


def write_quarantine(
    result: BatchGateResult,
    items: list[NormalizedItem],
    *,
    quarantine_dir: Path = QUARANTINE_DIR,
) -> Path:
    """Persist a failed batch under ``quarantine/<store>__<chunk>/``."""
    out_dir = quarantine_dir / result.batch_id.replace("#", "__")
    out_dir.mkdir(parents=True, exist_ok=True)
    to_catalog_frame(items).to_parquet(out_dir / "catalog.parquet", index=False)
    to_links_frame(items).to_parquet(out_dir / "links.parquet", index=False)
    return out_dir


def now_iso() -> str:
    """Timestamp helper shared by the manifest/orchestrator."""
    return dt.datetime.now().isoformat(timespec="seconds")
