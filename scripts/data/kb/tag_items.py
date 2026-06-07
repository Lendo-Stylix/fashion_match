"""Semantic tagging for graph-KB item nodes.

Reads the canonical scraper catalog, gates candidate backends on one real item,
then writes the validated semantic tags back into `catalog_metadata.parquet`.

Usage:
    uv run python -m scripts.data.kb.tag_items
    uv run python -m scripts.data.kb.tag_items --limit 50 --verbose
    uv run python -m scripts.data.kb.tag_items --offset 100 --limit 50 --force
    uv run python -m scripts.data.kb.tag_items --item-id item_custom_00001 --force
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import pandas as pd

from outfitmatch.kb.catalog import load_catalog_items
from outfitmatch.kb.tagging import (
    TaggingBackend,
    clear_failed_429_tags,
    gate_backends,
    probe_backends,
    select_backend,
    tag_items,
)
from scripts.data.scrape.base import CATALOG_DIR

logger = logging.getLogger("kb.tag_items")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Semantic tagging for graph-KB item nodes")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_metadata.parquet")
    parser.add_argument("--links", type=Path, default=CATALOG_DIR / "item_store_links.parquet")
    parser.add_argument("--item-id", action="append", default=[], help="Tag only these item_ids")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N matched items")
    parser.add_argument(
        "--limit", type=int, default=0, help="Tag only the first N matched items after offset"
    )
    parser.add_argument("--model", default="gemma-4-26b-a4b-it")
    parser.add_argument("--gemma-model", default="gemma-4-31b-it")
    parser.add_argument("--lite-model", default="gemini-3.1-flash-lite")
    parser.add_argument(
        "--ollama-model",
        action="append",
        default=[],
        help="Local Ollama model to try before remote Gemini/Gemma candidates; repeatable",
    )
    parser.add_argument(
        "--ollama-host",
        default=None,
        help="Ollama host URL, defaults to OLLAMA_HOST or http://127.0.0.1:11434",
    )
    parser.add_argument(
        "--ollama-only",
        action="store_true",
        help="Use only local Ollama models; do not probe remote Gemini/Gemma fallbacks",
    )
    parser.add_argument(
        "--openai-model",
        action="append",
        default=[],
        help=(
            "OpenAI-compatible chat model to try before remote candidates; repeatable. "
            "Use with llama.cpp/TurboQuant servers via --openai-base-url."
        ),
    )
    parser.add_argument(
        "--openai-base-url",
        default=None,
        help="OpenAI-compatible /v1 base URL, defaults to OPENAI_BASE_URL or llama.cpp :8087",
    )
    parser.add_argument(
        "--openai-only",
        action="store_true",
        help="Use only OpenAI-compatible models; do not probe Ollama or remote fallbacks",
    )
    parser.add_argument("--cache-dir", default="data/cache/gemini_tagging")
    parser.add_argument(
        "--failed-log", type=Path, help="JSONL progress log used to clear 429-dirty rows"
    )
    parser.add_argument(
        "--progress-log",
        type=Path,
        help="Append one JSONL progress record per processed item",
    )
    parser.add_argument(
        "--max-consecutive-backend-failures",
        type=int,
        default=5,
        help=(
            "Abort after this many consecutive transport-level backend failures "
            "(connection refused/reset/EOF). Use 0 to disable."
        ),
    )
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-call the backend")
    parser.add_argument(
        "--skip-tagged",
        action="store_true",
        help="Skip items that already have semantic tags or stylist notes",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write parquet")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _is_tagged(item: object) -> bool:
    body_shapes = getattr(item, "body_shapes_fit", []) or []
    seasons = getattr(item, "season", []) or []
    notes = str(getattr(item, "stylist_notes_vi", "") or "").strip()
    return bool(body_shapes or seasons or notes)


def _selection_counts(items: list) -> dict[str, int]:
    tagged = sum(1 for item in items if _is_tagged(item))
    return {
        "total": len(items),
        "tagged": tagged,
        "pending": len(items) - tagged,
    }


def _select_items(
    items: list, *, item_ids: set[str], offset: int, limit: int, skip_tagged: bool
) -> list:
    selected = [item for item in items if not item_ids or item.item_id in item_ids]
    if skip_tagged:
        selected = [item for item in selected if not _is_tagged(item)]
    if offset > 0:
        selected = selected[offset:]
    if limit > 0:
        selected = selected[:limit]
    return selected


def _candidate_backends(args: argparse.Namespace) -> list[TaggingBackend]:
    openai_backends = [
        TaggingBackend(provider="openai", model=model) for model in args.openai_model
    ]
    ollama_backends = [
        TaggingBackend(provider="ollama", model=model) for model in args.ollama_model
    ]
    if args.openai_only:
        return openai_backends
    if args.ollama_only:
        return ollama_backends
    return [
        *openai_backends,
        *ollama_backends,
        TaggingBackend(provider="gemini", model=args.model),
        TaggingBackend(provider="gemini", model=args.gemma_model),
        TaggingBackend(provider="gemini", model=args.lite_model),
    ]


def _write_back(catalog_path: Path, tagged_items: list) -> int:
    catalog = pd.read_parquet(catalog_path)
    updates = {
        item.item_id: {
            "body_shapes_fit": json.dumps(item.body_shapes_fit, ensure_ascii=False),
            "season": json.dumps(item.season, ensure_ascii=False),
            "stylist_notes_vi": item.stylist_notes_vi,
        }
        for item in tagged_items
        if _is_tagged(item)
    }
    if not updates:
        return 0

    for column in ("body_shapes_fit", "season", "stylist_notes_vi"):
        if column not in catalog.columns:
            catalog[column] = "[]" if column != "stylist_notes_vi" else ""

    updated = 0
    for idx, item_id in enumerate(catalog["item_id"].astype(str)):
        payload = updates.get(item_id)
        if payload is None:
            continue
        for column, value in payload.items():
            catalog.at[idx, column] = value
        updated += 1

    catalog.to_parquet(catalog_path, index=False)
    return updated


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if args.ollama_host:
        os.environ["OLLAMA_HOST"] = args.ollama_host
    if args.openai_base_url:
        os.environ["OPENAI_BASE_URL"] = args.openai_base_url

    if args.failed_log:
        cleared = clear_failed_429_tags(args.catalog, args.failed_log)
        logger.info("cleared %d rows from prior 429 failures", cleared)

    items = load_catalog_items(args.catalog, args.links, in_stock_only=False)
    counts = _selection_counts(items)
    selected = _select_items(
        items,
        item_ids=set(args.item_id),
        offset=args.offset,
        limit=args.limit,
        skip_tagged=args.skip_tagged,
    )
    logger.info(
        "catalog summary: total=%d tagged=%d pending=%d",
        counts["total"],
        counts["tagged"],
        counts["pending"],
    )
    logger.info("selected %d/%d items for semantic tagging", len(selected), len(items))
    if not selected:
        return 0

    backends = _candidate_backends(args)
    probe_results = (
        gate_backends(selected[0], backends=backends, progress_path=args.failed_log)
        if args.failed_log
        else probe_backends(selected[0], backends=backends)
    )
    chosen = select_backend(probe_results)
    healthy_backends = [result.backend for result in probe_results if result.status == "ok"]
    if chosen is None or not healthy_backends:
        for result in probe_results:
            logger.warning(
                "backend %s/%s unavailable: status=%s limit=%s retry_after=%s error=%s",
                result.backend.provider,
                result.backend.model,
                result.status,
                result.limit_rpm,
                result.retry_after_s,
                result.error,
            )
        return 1

    logger.info("selected primary backend %s/%s", chosen.provider, chosen.model)
    logger.info("healthy backends for this wave: %s", healthy_backends)
    try:
        tagged = tag_items(
            selected,
            cache_dir=args.cache_dir,
            force=args.force,
            backends=healthy_backends,
            progress_log=args.progress_log,
            max_consecutive_backend_failures=args.max_consecutive_backend_failures,
        )
    except RuntimeError as exc:
        logger.error("tagging aborted: %s", exc)
        return 1

    if args.dry_run:
        for item in tagged[:5]:
            logger.info(
                "%s :: body_shapes_fit=%s season=%s note=%s",
                item.item_id,
                item.body_shapes_fit,
                item.season,
                item.stylist_notes_vi,
            )
        logger.info("dry-run: skipped parquet write")
        return 0

    updated = _write_back(args.catalog, tagged)
    logger.info("wrote semantic tags for %d items -> %s", updated, args.catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
