"""Strip a re-emitted <tool_call> block from the final stylist answer so the
chat UI shows clean prose (outfit_cards are emitted separately, untouched)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

old = '''            final_response = self._generate(
                messages,
                max_new_tokens=max_new_tokens,
                temperature=0.0,
                enable_thinking=False,
            )
            yield {"type": "token", "data": final_response}'''

new = '''            final_response = self._generate(
                messages,
                max_new_tokens=max_new_tokens,
                temperature=0.0,
                enable_thinking=False,
            )
            # The model sometimes re-emits the <tool_call> block in its final
            # answer; strip it so the chat shows clean prose (cards are emitted
            # separately via outfit_cards and left untouched).
            final_response = re.sub(
                r"<tool_call>.*?</tool_call>", "", final_response,
                flags=re.DOTALL,
            ).strip()
            yield {"type": "token", "data": final_response}'''

assert old in s, "final_response block not found"
s = s.replace(old, new, 1)
service.write_text(s, encoding="utf-8")
print("patched service.py (strip tool_call from final answer)")
