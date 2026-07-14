"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from outfitmatch.server.deps import lifespan
from outfitmatch.server.routes.chat import router as chat_router
from outfitmatch.server.routes.health import router as health_router
from outfitmatch.server.routes.outfits import router as outfits_router
from outfitmatch.server.routes.quiz import router as quiz_router
from outfitmatch.server.routes.recommend import router as recommend_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="OutfitMatch API",
    description="Body & occasion-aware fashion recommender (v3.1-lite)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router, prefix="/api/health", tags=["Health"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(recommend_router, prefix="/api/recommend", tags=["Recommend"])
app.include_router(quiz_router, prefix="/api/quiz", tags=["Quiz"])
app.include_router(outfits_router, prefix="/api/outfits", tags=["Outfits"])
