"""Update test_chat_stream_invalid_tool_call for the fallback behavior:
an invalid explicit tool_call now falls back to keyword inference when a
recoverable occasion keyword is present; only errors when nothing recovers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
test = ROOT / "tests/test_stylist_service.py"
t = test.read_text(encoding="utf-8").replace("\r\n", "\n")

old = '''    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_invalid_tool_call(self, mock_search):
        """Invalid tool_call payload yields error event."""

        def fake_generate(model, processor, messages, **kwargs):
            return (
                \'<tool_call>{"name":"search_outfits","arguments":\'
                \'{"style":"invalid_style"}}</tool_call>\'
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
        mock_search.assert_not_called()'''

new = '''    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_invalid_tool_call_unrecoverable(self, mock_search):
        """Invalid tool_call with NO recoverable occasion keyword -> error."""

        def fake_generate(model, processor, messages, **kwargs):
            return (
                \'<tool_call>{"name":"search_outfits","arguments":\'
                \'{"style":"invalid_style"}}</tool_call>\'
            )

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        # "Tôi không biết mặc gì" has no occasion keyword -> fallback finds
        # nothing -> invalid tool_call is surfaced as an error.
        events = list(service.chat_stream("Tôi không biết mặc gì"))
        types = [e["type"] for e in events]
        assert "error" in types
        error_event = next(e for e in events if e["type"] == "error")
        assert "tool_call" in error_event["data"].lower()
        mock_search.assert_not_called()

    @patch("outfitmatch.retrieval.search_outfits")
    def test_chat_stream_invalid_tool_call_falls_back(self, mock_search):
        """Invalid tool_call but recoverable occasion keyword -> KB retrieval."""

        fake_outfit = _make_outfit("OF_00001")
        mock_search.return_value = [fake_outfit]

        def fake_generate(model, processor, messages, **kwargs):
            # Invalid enum on first call; second call (post-tool) is final text.
            for msg in reversed(messages):
                if msg.get("role") == "tool":
                    return "Gợi ý OF_00001 cho bạn."
            return (
                \'<tool_call>{"name":"search_outfits","arguments":\'
                \'{"style":"invalid_style"}}</tool_call>\'
            )

        service = StylistService(
            model=MagicMock(),
            processor=MagicMock(),
            graph=MagicMock(),
            generate_fn=fake_generate,
        )

        # "Mình đi làm" -> keyword fallback infers occasion=office (valid).
        events = list(service.chat_stream("Mình đi làm văn phòng"))
        types = [e["type"] for e in events]
        assert "outfit_cards" in types
        assert "error" not in types
        mock_search.assert_called_once()
        assert mock_search.call_args[0][0].occasion == "office"'''

assert old in t, "test invalid_tool_call block not found"
t = t.replace(old, new, 1)
test.write_text(t, encoding="utf-8")
print("patched test_stylist_service.py")
