"""Tests for outfitmatch.stylist.service — StylistService agent loop."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from outfitmatch.stylist.service import StylistService


def _make_item(item_id="IT_00001", price_vnd=100000, sizes=None, title_vi=""):
    return SimpleNamespace(
        item_id=item_id,
        category="top",
        image_path="img.webp",
        store={
            "title_vi": title_vi,
            "price_vnd": price_vnd,
            "store_name": "TestStore",
            "product_url": "http://example.com",
            "sizes": sizes or ["M", "L"],
        },
    )


def _make_outfit(outfit_id="OF_00001"):
    return SimpleNamespace(
        outfit_id=outfit_id,
        items=[_make_item("IT_00001"), _make_item("IT_00002", 200000, sizes=["M"])],
        stylist_explanation_vi="Outfit phù hợp cho dịp đi làm.",
        price_total_vnd=300000,
        price_tier="budget",
        style=["minimalist"],
        occasion=["office"],
        color_palette=["trắng", "đen"],
        compatibility_score=0.95,
    )


class TestStylistService:
    """Unit tests for StylistService.chat_stream and recommend_from_structured."""

    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_with_tool_call(self, mock_search):
        """If generate_fn emits tool_call, service executes search_outfits."""
        fake_outfit = _make_outfit("OF_00001")
        mock_search.return_value = [fake_outfit]

        tool_call = (
            '<tool_call>{"name":"search_outfits",'
            '"arguments":{"occasion":"office","style":"minimalist"}}'
            "</tool_call>"
        )
        final_answer = "Tôi gợi ý outfit OF_00001 với phong cách minimalist cho buổi đi làm."

        def fake_generate(model, processor, messages, **kwargs):
            # First call: assistant tool call, second call: final explanation
            for msg in reversed(messages):
                if msg.get("role") == "tool":
                    return final_answer
            return tool_call

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        events = list(service.chat_stream("Mình đi làm văn phòng, style minimalist"))
        types = [e["type"] for e in events]
        assert "thinking" in types
        assert "token" in types
        assert "outfit_cards" in types
        assert "done" in types

        # search_outfits called with correct occasion/style
        mock_search.assert_called_once()
        request_arg = mock_search.call_args[0][0]
        assert request_arg.occasion == "office"
        assert request_arg.style == "minimalist"

        # outfit_cards payload correct
        outfit_cards_event = next(e for e in events if e["type"] == "outfit_cards")
        assert outfit_cards_event["data"][0]["outfit_id"] == "OF_00001"

    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_without_tool_call(self, mock_search):
        """If no tool_call, service returns normal chat response."""

        def fake_generate(model, processor, messages, **kwargs):
            return "Xin hãy cho tôi biết bạn đi đâu để tôi gợi ý outfit."

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        events = list(service.chat_stream("Tôi không biết mặc gì"))
        types = [e["type"] for e in events]
        assert "thinking" in types
        assert "token" in types
        assert "outfit_cards" not in types
        assert "done" in types
        mock_search.assert_not_called()

    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_invalid_tool_call(self, mock_search):
        """Invalid tool_call payload yields error event."""

        def fake_generate(model, processor, messages, **kwargs):
            return (
                '<tool_call>{"name":"search_outfits","arguments":'
                '{"style":"invalid_style"}}</tool_call>'
            )

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        events = list(service.chat_stream("Mình đi làm"))
        types = [e["type"] for e in events]
        assert "error" in types
        error_event = next(e for e in events if e["type"] == "error")
        assert "tool_call" in error_event["data"].lower()
        mock_search.assert_not_called()

    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_hallucinated_outfit_id(self, mock_search):
        """Final response referencing non-existent outfit_id yields error."""
        fake_outfit = _make_outfit("OF_00001")
        mock_search.return_value = [fake_outfit]

        def fake_generate(model, processor, messages, **kwargs):
            for msg in reversed(messages):
                if msg.get("role") == "tool":
                    # Hallucinated ID
                    return "Tôi gợi ý OF_99999 cho bạn."
            return (
                '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
            )

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        events = list(service.chat_stream("Mình đi làm"))
        types = [e["type"] for e in events]
        assert "error" in types
        error_event = next(e for e in events if e["type"] == "error")
        assert "OF_99999" in error_event["data"]

    @patch("outfitmatch.pipeline.recommend_outfit")
    def test_recommend_from_structured(self, mock_recommend):
        """recommend_from_structured delegates to pipeline.recommend_outfit."""
        from outfitmatch.pipeline import RecommendRequest

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(spec="OutfitGraph"),
        )
        request = RecommendRequest(occasion="wedding", style="elegant")
        service.recommend_from_structured(request)

        mock_recommend.assert_called_once()
        args, kwargs = mock_recommend.call_args
        assert kwargs["graph"] is service.graph
        assert kwargs["qdrant_url"] is None


def test_service_uses_default_system_prompt():
    """StylistService loads the default system prompt."""
    service = StylistService(model=None, processor=None, graph=None)
    assert "stylist" in service._system_prompt.lower()
