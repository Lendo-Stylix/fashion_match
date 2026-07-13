"""RED/GREEN tests for the on-device stylist runner (toolcall -> graph -> outfit ids).

These tests exercise the REAL local fashion_kb graph (catalog + edges parquet,
CPU-only) but MOCK the GPU model load + generate, so they run without a GPU and
without touching HF network. They lock in the contract:

    user_prompt -> (mock) model emits <tool_call>search_outfits{...} ->
    execute_tool_call parses it -> search_outfits(graph) -> real outfit ids

Run:  uv run pytest tests/stylist/test_run_inference_device.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
for _p in (str(_REPO), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import scripts.stylist.run_inference_device as m  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: build a fake model/processor pair + patch generate()
# ---------------------------------------------------------------------------
class _FakeProcessor:
    """Minimal stand-in: apply_chat_template returns the prompt string;
    text() returns a dict with input_ids; decode() echoes a canned tool_call."""

    def __init__(self, canned: str) -> None:
        self._canned = canned

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        # echo only the last user message so test can assert on it
        return messages[-1]["content"]

    def text(self, prompt, images=None, return_tensors="pt"):
        return {"input_ids": [0]}

    def decode(self, ids, skip_special_tokens=True):
        return self._canned


class _FakeModel:
    def __init__(self, processor: _FakeProcessor):
        self.processor = processor

    def eval(self):
        return self

    def parameters(self):
        # device placeholder
        class _P:
            def __init__(self):
                self.device = "cpu"

        return [_P()]


def _patch_model(monkeypatch, canned_tool_call: str):
    """Patch load_stylist + generate so no GPU/HF is touched."""
    proc = _FakeProcessor(canned_tool_call)
    model = _FakeModel(proc)

    def _fake_load(base_path, adapter_path=None, kind="vl"):
        return model, proc

    def _fake_generate(mdl, processor, user_prompt, max_new_tokens=512, kind="vl"):
        # record that the user prompt reached the model (sanity)
        return canned_tool_call

    monkeypatch.setattr(m, "load_stylist", _fake_load)
    monkeypatch.setattr(m, "generate", _fake_generate)


# A wedding tool_call (occasion required) — valid enum values from vocab.py
WEDDING_CALL = (
    '<tool_call>{"name":"search_outfits","arguments":'
    '{"occasion":"wedding","body_shape":"pear","skin_tone":"warm",'
    '"price_max":1000000}}</tool_call>'
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_system_prompt_forces_tool_call_format():
    sp = m.SYSTEM_PROMPT
    assert "<tool_call>" in sp
    assert "search_outfits" in sp
    # both few-shot examples present
    assert "office" in sp and "party" in sp
    # lists the canonical enums so the model stays on-vocab
    assert "wedding" in sp and "minimalist" in sp


def test_execute_tool_call_returns_real_outfit_ids(monkeypatch, tmp_path):
    """The core contract: a valid tool_call -> search_outfits -> real ids."""
    _, graph = m.build_graph_context()  # real local KB (CPU)
    tool_call = {
        "name": "search_outfits",
        "arguments": {
            "occasion": "wedding",
            "body_shape": "pear",
            "skin_tone": "warm",
            "price_max": 1000000,
        },
    }
    brief, records = m.execute_tool_call(tool_call, graph, top_n=3)
    assert records, "search_outfits must return outfits for a valid wedding query"
    # stable hex ids (FIX D) keep the OF_ prefix
    assert all(r.outfit_id.startswith("OF_") for r in records)
    assert len(records) <= 3
    # price_max guard should not crash; brief echoes the request
    assert "occasion=wedding" in brief


def test_format_outfit_shows_real_item_details(monkeypatch):
    """FIX E: output must show title + price + product_url, not generic cats."""
    from outfitmatch.kb.catalog import load_catalog_items
    from outfitmatch.kb.graph_store import load_graph
    from outfitmatch.pipeline import RecommendRequest
    from outfitmatch.retrieval import search_outfits

    items = load_catalog_items(m.CATALOG_PARQUET, m.LINKS_PARQUET)
    graph = load_graph(m.EDGES_PARQUET, items=items)
    rec = search_outfits(RecommendRequest(occasion="wedding"), graph=graph, top_n=1)[0]
    text = m.format_outfit(rec)
    # at least one item title + price + url surfaced
    assert any(it.store.get("title_vi") for it in rec.items)
    assert "VND" in text
    assert "->" in text  # product_url line


def test_main_end_to_end_with_mocked_model(monkeypatch, capsys):
    """Full main() with a mocked model must print outfit ids to stdout."""
    _patch_model(monkeypatch, WEDDING_CALL)
    rc = m.main(["--prompt", "dummy wedding query", "--top-n", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OUTFIT IDs:" in out
    # the mocked model emits a wedding call -> ids printed
    assert "OF_" in out
