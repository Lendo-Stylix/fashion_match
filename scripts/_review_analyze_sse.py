"""Analyze a saved SSE chat log from the OutfitMatch backend.

Prints event types, token text, and (for outfit_cards) the parsed outfit IDs
+ item IDs so we can check for hallucinated IDs. Safe for Vietnamese (utf-8).
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PATH = sys.argv[1] if len(sys.argv) > 1 else "logs/chat1.sse"


def main() -> None:
    raw = open(PATH, encoding="utf-8", errors="replace").read()
    blocks = [b for b in raw.split("\n\n") if b.strip()]
    n_cards = 0
    for b in blocks:
        ev = ""
        data: list[str] = []
        for ln in b.split("\n"):
            if ln.startswith("event:"):
                ev = ln[6:].strip()
            elif ln.startswith("data:"):
                data.append(ln[5:].lstrip())
        if not ev:
            continue
        d = "\n".join(data)
        if ev == "outfit_cards":
            try:
                cards = json.loads(d)
                n_cards += 1
                print(f"[outfit_cards] {len(cards)} cards")
                for c in cards:
                    ids = [i.get("item_id") for i in c.get("items", [])]
                    print(
                        f"   - id={c.get('outfit_id')} price={c.get('price_total_vnd')} "
                        f"style={c.get('style')} occasion={c.get('occasion')} items={ids}"
                    )
            except Exception as e:  # noqa: BLE001
                print(f"[outfit_cards] parse-fail: {e} :: {d[:200]}")
        elif ev == "token":
            print(f"[token] {d[:400].replace(chr(10), ' ')}")
        else:
            print(f"[{ev}] {d[:300].replace(chr(10), ' ')}")
    print(f"\n-- summary: {len(blocks)} events, {n_cards} outfit_cards blocks --")


if __name__ == "__main__":
    main()
