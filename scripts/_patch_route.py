"""Fix: service yields outfit_cards as a list (unit-test contract); the SSE
route serializes list/dict payloads to JSON so sse_starlette emits valid JSON
(not a Python repr). Exact string replace."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1) service.py: revert outfit_cards to the list (drop json.dumps)
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")
old = '            cards = self._format_outfit_cards(records)\n            yield {"type": "outfit_cards", "data": json.dumps(cards, ensure_ascii=False)}'
new = '            cards = self._format_outfit_cards(records)\n            yield {"type": "outfit_cards", "data": cards}'
assert old in s, "service outfit_cards json.dumps not found"
s = s.replace(old, new, 1)
service.write_text(s, encoding="utf-8")
print("patched service.py (list payload)")

# 2) routes/chat.py: serialize list/dict payloads to JSON for SSE
route = ROOT / "src/outfitmatch/server/routes/chat.py"
r = route.read_text(encoding="utf-8").replace("\r\n", "\n")

old_import = 'from __future__ import annotations\n\nfrom typing import Any'
new_import = 'from __future__ import annotations\n\nimport json\nfrom typing import Any'
assert old_import in r, "route import block not found"
r = r.replace(old_import, new_import, 1)

old_gen = '''            for event in stylist.chat_stream(user_message=req.message):
                yield {
                    "event": event["type"],
                    "data": event.get("data", ""),
                }'''
new_gen = '''            for event in stylist.chat_stream(user_message=req.message):
                data = event.get("data", "")
                # sse_starlette str()s complex objects as a Python repr
                # (single-quoted, invalid JSON). Serialize list/dict payloads
                # explicitly so the Next.js client receives valid JSON.
                if isinstance(data, (list, dict)):
                    data = json.dumps(data, ensure_ascii=False)
                yield {
                    "event": event["type"],
                    "data": data,
                }'''
assert old_gen in r, "route generator block not found"
r = r.replace(old_gen, new_gen, 1)
route.write_text(r, encoding="utf-8")
print("patched routes/chat.py (json serialize)")
print("PATCH ROUTE DONE")
