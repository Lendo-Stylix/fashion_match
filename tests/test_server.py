"""Tests for FastAPI server routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestHealthRoute:
    """GET /api/health."""

    @patch("outfitmatch.server.deps._graph")
    @patch("outfitmatch.server.deps._model")
    @patch("outfitmatch.server.deps._stylist_service")
    def test_health_returns_status(self, mock_stylist, mock_model, mock_graph):
        from fastapi import FastAPI

        from outfitmatch.server.routes.health import router

        app = FastAPI()
        app.include_router(router, prefix="/api/health")

        with TestClient(app) as client:
            resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "graph_loaded" in data


class TestQuizRoute:
    """GET /api/quiz."""

    def test_quiz_returns_questions(self):
        from fastapi import FastAPI

        from outfitmatch.server.routes.quiz import router

        app = FastAPI()
        app.include_router(router, prefix="/api/quiz")

        with TestClient(app) as client:
            resp = client.get("/api/quiz")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["questions"]) == 5
        assert data["questions"][0]["key"] == "style"


class TestChatRoute:
    """POST /api/chat."""

    @patch("outfitmatch.server.deps._stylist_service", None)
    def test_chat_returns_503_when_no_stylist(self):
        from fastapi import FastAPI

        from outfitmatch.server.routes.chat import router

        app = FastAPI()
        app.include_router(router, prefix="/api/chat")

        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"message": "test"})
        assert resp.status_code == 503


class TestRecommendRoute:
    """POST /api/recommend."""

    @patch("outfitmatch.server.deps._graph", new_callable=lambda: MagicMock)
    @patch("outfitmatch.server.deps._stylist_service", new_callable=lambda: MagicMock)
    @patch("outfitmatch.pipeline.recommend_outfit")
    def test_recommend_returns_outfits(self, mock_recommend, mock_stylist, mock_graph):
        from fastapi import FastAPI

        from outfitmatch.server.routes.recommend import router

        mock_recommend.return_value = SimpleNamespace(
            outfits=[],
            body_shape="",
            occasion="office",
            explanation_vi="",
            latency_ms=100.0,
            suggested_sizes={},
        )

        app = FastAPI()
        app.include_router(router, prefix="/api/recommend")

        with TestClient(app) as client:
            resp = client.post("/api/recommend", json={"occasion": "office"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["occasion"] == "office"
        assert "outfits" in data
        assert "explanation_vi" in data
