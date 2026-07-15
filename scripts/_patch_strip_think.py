"""Also strip leaked </think> / <think> artifacts from the final answer."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

old = '''            # The model sometimes re-emits the <tool_call> block in its final
            # answer; strip it so the chat shows clean prose (cards are emitted
            # separately via outfit_cards and left untouched).
            final_response = re.sub(
                r"<tool_call>.*?</tool_call>", "", final_response,
                flags=re.DOTALL,
            ).strip()
            yield {"type": "token", "data": final_response}'''

new = '''            # The model sometimes re-emits the <tool_call> / </think> artifacts
            # in its final answer; strip them so the chat shows clean prose
            # (cards are emitted separately via outfit_cards, untouched).
            final_response = re.sub(
                r"<tool_call>.*?</tool_call>|</think>|<think>",
                "",
                final_response,
                flags=re.DOTALL,
            ).strip()
            yield {"type": "token", "data": final_response}'''

assert old in s, "strip block not found"
s = s.replace(old, new, 1)
service.write_text(s, encoding="utf-8")
print("patched service.py (also strip </think>)")
