"""FastAPI dependency injection and lifespan singletons."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level singletons, set during lifespan startup.
app: FastAPI | None = None
_graph: Any | None = None
_model: Any | None = None
_processor: Any | None = None
_stylist_service: Any | None = None


@asynccontextmanager
async def lifespan(app_obj: FastAPI) -> AsyncGenerator[None]:
    """Load graph + model at startup, clean up at shutdown."""
    global _graph, _model, _processor, _stylist_service

    logger.info("Loading OutfitMatch singletons...")

    # Load graph KB (CPU)
    from scripts.data.scrape.base import CATALOG_DIR

    from outfitmatch.kb.catalog import load_catalog_items
    from outfitmatch.kb.graph_store import load_graph

    items = load_catalog_items(
        CATALOG_DIR / "catalog_metadata.parquet",
        CATALOG_DIR / "item_store_links.parquet",
    )
    _graph = load_graph(items=items)
    logger.info("Graph loaded: %d items", len(items))

    # Load model + processor (GPU, optional)
    try:
        from outfitmatch.stylist.model import load_stylist_model

        model, processor = load_stylist_model()
        _model = model
        _processor = processor
        logger.info("Stylist model loaded successfully")

        from outfitmatch.stylist.service import StylistService

        _stylist_service = StylistService(model=model, processor=processor, graph=_graph)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not load stylist model (running without LLM): %s", e)

    yield

    logger.info("Shutting down OutfitMatch server.")


def get_graph() -> Any:
    """Dependency: retrieve the shared OutfitGraph."""
    if _graph is None:
        raise RuntimeError("Graph not loaded. Has lifespan started?")
    return _graph


def get_stylist_service() -> Any | None:
    """Dependency: retrieve the StylistService (or None if model unavailable)."""
    return _stylist_service


def get_model_and_processor() -> tuple[Any, Any] | None:
    """Dependency: retrieve (model, processor) or None."""
    if _model is None or _processor is None:
        return None
    return _model, _processor
