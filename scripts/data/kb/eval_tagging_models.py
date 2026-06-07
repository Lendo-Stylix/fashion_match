"""Evaluate tagging model quality on a small pending-item sample.

The evaluator intentionally does not write back to the catalog. It runs each model
on the same selected items, records validated tag payloads plus latency, then
ranks models by usable quality before any long tagging wave is launched.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.tagging import TaggingBackend, tag_items
from scripts.data.kb.tag_items import _is_tagged, _select_items
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.eval_tagging_models")


@dataclass(frozen=True, slots=True)
class ModelQualitySummary:
    """Aggregate quality and latency for one tested tagging model."""

    model: str
    total: int
    ok: int
    with_body_shape: int
    with_season: int
    with_note: int
    avg_latency_s: float

    @property
    def quality_score(self) -> float:
        """Fraction of tested items with a complete, usable semantic payload."""
        if self.total <= 0:
            return 0.0
        usable = min(self.ok, self.with_body_shape, self.with_season, self.with_note)
        return usable / self.total


def _safe_model_name(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def _records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summarize_progress(path: Path, *, model: str) -> ModelQualitySummary:
    """Summarize one model JSONL progress file."""
    records = [record for record in _records(path) if str(record.get("model") or "") == model]
    latencies = [float(record.get("latency_s") or 0.0) for record in records]
    ok_records = [record for record in records if record.get("ok")]
    total = len(records)
    return ModelQualitySummary(
        model=model,
        total=total,
        ok=len(ok_records),
        with_body_shape=sum(bool(record.get("body_shapes_fit")) for record in ok_records),
        with_season=sum(bool(record.get("season")) for record in ok_records),
        with_note=sum(
            bool(str(record.get("stylist_notes_vi") or "").strip()) for record in ok_records
        ),
        avg_latency_s=round(sum(latencies) / total, 3) if total else 0.0,
    )


def choose_best_model(summaries: list[ModelQualitySummary]) -> ModelQualitySummary | None:
    """Choose best model by quality, successful items, then lower average latency."""
    if not summaries:
        return None
    return max(
        summaries,
        key=lambda summary: (summary.quality_score, summary.ok, -summary.avg_latency_s),
    )


def _append_record(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _progress_record_count(path: Path) -> int:
    return len(_records(path))


def _newest_progress_record(path: Path) -> dict[str, object]:
    records = _records(path)
    return records[-1] if records else {"ok": False, "errors": [{"error": "missing progress"}]}


def evaluate_model(
    items: list,
    *,
    model: str,
    output_dir: Path,
    cache_dir: Path,
    force: bool,
    provider: str = "ollama",
) -> ModelQualitySummary:
    """Evaluate one local/compatible tagging model without parquet writes."""
    safe_model = _safe_model_name(model)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / f"{safe_model}.jsonl"
    temp_path = output_dir / f".{safe_model}.tmp.jsonl"
    backend = TaggingBackend(provider=provider, model=model)

    for path in (progress_path, temp_path):
        if path.exists():
            path.unlink()

    for item in items:
        start = time.perf_counter()
        before_count = _progress_record_count(temp_path)
        tag_items(
            [item],
            cache_dir=str(cache_dir),
            force=force,
            backends=[backend],
            progress_log=temp_path,
        )
        latency_s = round(time.perf_counter() - start, 3)
        records = _records(temp_path)
        record = records[-1] if len(records) > before_count else _newest_progress_record(temp_path)
        record = {**record, "latency_s": latency_s}
        _append_record(progress_path, record)
        logger.info(
            "%s/%s ok=%s latency=%.1fs body=%s season=%s note=%s",
            model,
            getattr(item, "item_id", ""),
            record.get("ok"),
            latency_s,
            record.get("body_shapes_fit"),
            record.get("season"),
            str(record.get("stylist_notes_vi") or "")[:60],
        )

    return summarize_progress(progress_path, model=model)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate tagging model quality on pending items")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--model", action="append", required=True, help="Model name to evaluate")
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai"],
        default="ollama",
        help="Tagging provider adapter to use for all --model values",
    )
    parser.add_argument(
        "--openai-base-url",
        default=None,
        help="OpenAI-compatible /v1 base URL for provider=openai",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("data/cache/tagging_model_eval"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/gemini_tagging"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    if args.openai_base_url:
        import os

        os.environ["OPENAI_BASE_URL"] = args.openai_base_url

    items = load_catalog_items(args.catalog, args.links, in_stock_only=False)
    selected = _select_items(
        items,
        item_ids=set(),
        offset=args.offset,
        limit=args.limit,
        skip_tagged=True,
    )
    logger.info(
        "selected %d pending items from %d catalog rows (tagged=%d)",
        len(selected),
        len(items),
        sum(1 for item in items if _is_tagged(item)),
    )
    if not selected:
        return 1

    summaries = [
        evaluate_model(
            copy.deepcopy(selected),
            model=model,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
            force=args.force,
            provider=args.provider,
        )
        for model in args.model
    ]
    best = choose_best_model(summaries)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "summaries": [
                    {**asdict(summary), "quality_score": summary.quality_score}
                    for summary in summaries
                ],
                "best_model": best.model if best else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("best_model=%s summary=%s", best.model if best else None, summary_path)
    return 0 if best and best.quality_score > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
