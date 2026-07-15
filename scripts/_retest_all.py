"""Re-test all prompts against the live /api/chat SSE endpoint (patched server).

Reads logs/prompts.txt (lines "N|prompt"), POSTs each to the backend, saves
raw SSE to logs/chat_N.sse, and prints a compact summary (event counts,
outfit_cards presence, latency). UTF-8 safe.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

URL = "http://localhost:8000/api/chat"
PROMPTS = "logs/prompts.txt"


def post(prompt: str) -> tuple[bytes, float]:
    body = json.dumps({"message": prompt}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read()
    return raw, time.time() - t0


def main() -> None:
    lines = [
        ln.strip() for ln in open(PROMPTS, encoding="utf-8") if ln.strip()
    ]
    print(f"=== re-testing {len(lines)} prompts ===")
    for ln in lines:
        if "|" not in ln:
            continue
        idx, prompt = ln.split("|", 1)
        idx = idx.strip()
        prompt = prompt.strip()
        try:
            raw, secs = post(prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx}] ERROR {exc}  ({prompt[:50]})")
            continue
        open(f"logs/chat_{idx}.sse", "wb").write(raw)
        text = raw.decode("utf-8", errors="replace")
        evs = [e for e in text.split("\n\n") if e.strip()]
        has_cards = "event: outfit_cards" in text
        has_tool = "search_outfits" in text
        has_err = "event: error" in text
        # count tokens
        ntok = text.count("event: token")
        print(
            f"[{idx}] {secs:5.1f}s events={len(evs)} tokens={ntok} "
            f"cards={'Y' if has_cards else 'N'} tool={'Y' if has_tool else 'N'} "
            f"err={'Y' if has_err else 'N'} | {prompt[:46]}"
        )
    print("=== DONE ===")


if __name__ == "__main__":
    main()
