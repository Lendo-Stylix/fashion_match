"""E2E smoke test: verify all FastAPI endpoints respond correctly.

Uses TestClient with mocked singletons (no GPU, no Qdrant).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestE2ESmoke:
    """Full-stack smoke test via TestClient."""

    @patch("outfitmatch.server.deps._graph")
    @patch("outfitmatch.server.deps._model")
    @patch("outfitmatch.server.deps._stylist_service")
    def test_health_endpoint(self, mock_stylist, mock_model, mock_graph):
        """GET /api/health returns status with all singletons."""
        from outfitmatch.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "graph_loaded" in data
        assert "stylist_available" in data
        assert "gpu_available" in data

    def test_quiz_endpoint(self):
        """GET /api/quiz returns 5 questions."""
        from outfitmatch.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/quiz")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["questions"]) == 5
        keys = [q["key"] for q in data["questions"]]
        assert "style" in keys
        assert "occasions" in keys
        assert "price_tier" in keys

    @patch("outfitmatch.server.deps._graph")
    @patch("outfitmatch.server.deps._stylist_service")
    @patch("outfitmatch.pipeline.recommend_outfit")
    def test_recommend_endpoint(self, mock_recommend, mock_stylist, mock_graph):
        """POST /api/recommend returns outfits + explanation."""
        mock_item = SimpleNamespace(
            item_id="IT_00001",
            category="top",
            store={
                "title_vi": "Ao so mi",
                "price_vnd": 150000,
                "store_name": "YODY",
                "product_url": "https://yody.vn",
            },
            image_path="",
        )
        mock_outfit = SimpleNamespace(
            outfit_id="OF_00001",
            items=[mock_item],
            stylist_explanation_vi="Phoi ao so mi voi quan tay.",
            price_total_vnd=450000,
            price_tier="mid",
            style=["minimalist"],
            occasion=["office"],
            color_palette=["white", "navy"],
            compatibility_score=0.85,
        )
        mock_recommend.return_value = SimpleNamespace(
            outfits=[mock_outfit],
            body_shape="rectangle",
            occasion="office",
            explanation_vi="Phoi ao so mi voi quan tay.",
            latency_ms=120.0,
            suggested_sizes={"top": "M"},
        )

        from outfitmatch.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/recommend", json={"occasion": "office"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["occasion"] == "office"
        assert len(data["outfits"]) == 1
        assert data["outfits"][0]["outfit_id"] == "OF_00001"
        assert data["explanation_vi"] == "Phoi ao so mi voi quan tay."
        assert "suggested_sizes" in data

    @patch("outfitmatch.server.deps._stylist_service", None)
    def test_chat_endpoint_503_without_model(self):
        """POST /api/chat returns 503 when stylist unavailable."""
        from outfitmatch.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 503

    def test_openapi_schema_available(self):
        """GET /openapi.json returns valid schema."""
        from outfitmatch.server.app import app

        with TestClient(app) as client:
            resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "OutfitMatch API"
        assert "/api/health" in schema["paths"]
        assert "/api/chat" in schema["paths"]
        assert "/api/recommend" in schema["paths"]
        assert "/api/quiz" in schema["paths"]
