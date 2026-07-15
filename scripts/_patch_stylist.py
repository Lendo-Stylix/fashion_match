"""One-shot exact-replace patch for fixes 1-4 (no regex, no edit-tool)."""
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# 1) service.py
# ---------------------------------------------------------------------------
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

# a) imports
old_imports = "import logging\nfrom collections.abc import Callable"
new_imports = "import json\nimport logging\nimport re\nfrom collections.abc import Callable"
assert old_imports in s, "service imports not found"
s = s.replace(old_imports, new_imports, 1)

# b) insert _infer_request before chat_stream
old_chat = "    def chat_stream("
new_method = '''    def _infer_request(self, user_message: str, response: str) -> dict[str, Any] | None:
        """Heuristic fallback: if the model skipped a <tool_call> but the user
        clearly named an occasion, infer a search_outfits payload from keywords.

        Returns the canonical payload dict or None when no occasion is detected.
        """
        from outfitmatch.vocab import STYLE_LABELS_VI

        text = (user_message + " " + response).lower()
        occasion_map = {
            "office": ["đi làm", "văn phòng", "công sở", "công ty"],
            "interview": ["phỏng vấn", "pv"],
            "school": ["đi học", "đến trường"],
            "date": ["hẹn hò", "hen ho", "date", "cưa"],
            "cafe_hangout": ["cafe", "cà phê", "đi chơi", "dạo phố", "tụ tập"],
            "party": ["tiệc", "party", "liên hoan"],
            "wedding": ["cưới", "đám cưới", "wedding", "thành hôn"],
            "home_casual": ["ở nhà", "thường ngày", "hằng ngày"],
            "travel": ["du lịch", "du lich", "đi du", "nghỉ mát", "biển"],
        }
        occasion: str | None = None
        for occ, kws in occasion_map.items():
            if any(k in text for k in kws):
                occasion = occ
                break
        if occasion is None:
            return None

        style: str | None = None
        for st, label in STYLE_LABELS_VI.items():
            if label.lower() in text:
                style = st
                break

        price_max: int | None = None
        m = re.search(r"(\\d+(?:[.,]\\d+)?)\\s*(triệu|tr|nghìn|ngàn|k)?", text)
        if m:
            num = float(m.group(1).replace(",", "."))
            unit = m.group(2)
            if unit == "triệu":
                price_max = int(num * 1_000_000)
            elif unit in ("nghìn", "ngàn", "k"):
                price_max = int(num * 1_000)
            else:
                price_max = int(num)
                if price_max < 1000:
                    price_max = int(num * 1_000_000)

        arguments: dict[str, Any] = {"occasion": occasion}
        if style is not None:
            arguments["style"] = style
        if price_max is not None:
            arguments["price_max"] = price_max
        return {"name": "search_outfits", "arguments": arguments}

    def chat_stream('''
assert old_chat in s, "service chat_stream marker not found"
s = s.replace(old_chat, new_method, 1)

# c) replace the chat_stream body block
old_body = '''        thinking_text = "Phân tích yêu cầu..."
        yield {"type": "thinking", "data": thinking_text}

        # Pass 1: parse intent / tool call
        response = self._generate(messages, max_new_tokens=max_new_tokens)
        yield {"type": "token", "data": response}

        payload = self._extract_tool_call(response)
        if payload is not None:
            ok, errors = self._validate_tool_call(payload)
            if not ok:
                yield {
                    "type": "error",
                    "data": f"tool_call không hợp lệ: {errors[0]}"
                    if errors
                    else "tool_call không hợp lệ",
                }
                return

            try:
                records = self._execute_tool_call(payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tool execution failed")
                yield {"type": "error", "data": f"Lỗi truy vấn KB: {exc}"}
                return

            tool_result = self._format_tool_result(records)
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "tool", "content": tool_result})

            final_response = self._generate(messages, max_new_tokens=max_new_tokens)
            yield {"type": "token", "data": final_response}

            # Validation
            valid, v_errors = self._run_validation(final_response, records, height_cm, weight_kg)
            if not valid:
                yield {"type": "error", "data": "; ".join(v_errors)}
                return

            cards = self._format_outfit_cards(records)
            yield {"type": "outfit_cards", "data": cards}
        else:
            # No tool call: validate that we did not hallucinate IDs
            valid, _ = validate_response(response, set())
            if not valid:
                yield {"type": "error", "data": "Phát hiện outfit_id không tồn tại trong phản hồi."}
                return

        yield {"type": "done", "data": ""}'''
new_body = '''        thinking_text = "Phân tích yêu cầu..."
        yield {"type": "thinking", "data": thinking_text}

        # Pass 1: parse intent / tool call (greedy + short; just to extract intent)
        response = self._generate(messages, max_new_tokens=256, temperature=0.0,
                                  enable_thinking=False)

        payload = self._extract_tool_call(response)
        if payload is None:
            # Model skipped the tool call but the user named an occasion ->
            # infer the search_outfits payload so KB retrieval still fires.
            inferred = self._infer_request(user_message, response)
            if inferred is not None:
                payload = inferred

        if payload is not None:
            ok, errors = self._validate_tool_call(payload)
            if not ok:
                yield {
                    "type": "error",
                    "data": f"tool_call không hợp lệ: {errors[0]}"
                    if errors
                    else "tool_call không hợp lệ",
                }
                return

            try:
                records = self._execute_tool_call(payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tool execution failed")
                yield {"type": "error", "data": f"Lỗi truy vấn KB: {exc}"}
                return

            tool_result = self._format_tool_result(records)
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "tool", "content": tool_result})

            final_response = self._generate(
                messages, max_new_tokens=max_new_tokens, temperature=0.0,
                enable_thinking=False,
            )
            yield {"type": "token", "data": final_response}

            # Validation
            valid, v_errors = self._run_validation(final_response, records, height_cm, weight_kg)
            if not valid:
                yield {"type": "error", "data": "; ".join(v_errors)}
                return

            cards = self._format_outfit_cards(records)
            yield {"type": "outfit_cards", "data": json.dumps(cards, ensure_ascii=False)}
        else:
            # No tool call and no detectable occasion: validate that we did not
            # hallucinate IDs
            valid, _ = validate_response(response, set())
            if not valid:
                yield {"type": "error", "data": "Phát hiện outfit_id không tồn tại trong phản hồi."}
                return
            yield {"type": "token", "data": response}

        yield {"type": "done", "data": ""}'''
assert old_body in s, "service chat_stream body not found"
s = s.replace(old_body, new_body, 1)

service.write_text(s, encoding="utf-8")
print("patched service.py")

# ---------------------------------------------------------------------------
# 2) model.py — few-shot system prompt + enable_thinking param
# ---------------------------------------------------------------------------
model = ROOT / "src/outfitmatch/stylist/model.py"
m = model.read_text(encoding="utf-8").replace("\r\n", "\n")

old_prompt = '''DEFAULT_SYSTEM_PROMPT = (
    "Ban la AI stylist tieng Viet cua OutfitMatch. Nhiem vu cua ban la HIEU "
    "yeu cau cua nguoi dung va GOI tool search_outfits de lay outfit tu "
    "Knowledge Base. Phai goi tool truoc khi dua ra loi khuyen."
)'''
new_prompt = '''DEFAULT_SYSTEM_PROMPT = (
    "Ban la AI stylist tieng Viet cua OutfitMatch. Nhiem vu cua ban la HIEU "
    "yeu cau cua nguoi dung va GOI tool search_outfits de lay outfit tu "
    "Knowledge Base. Phai goi tool truoc khi dua ra loi khuyen.\\n\\n"
    "Quy tac:\\n"
    "1. Phan tich yeu cau -> anh xa sang cac tham so:\\n"
    "   - occasion (bat buoc): office | interview | school | date | cafe_hangout "
    "| party | wedding | home_casual | travel\\n"
    "   - style: minimalist | korean | streetwear | elegant | casual | vintage "
    "| sporty | feminine\\n"
    "   - body_shape: pear | apple | hourglass | rectangle | inverted_triangle\\n"
    "   - skin_tone: warm | neutral | cool\\n"
    "   - price_max: so nguyen VND (vd 1000000)\\n"
    "   - exclude_colors: mang ten mau tieng Viet\\n"
    "2. Phat dung dinh dang: <tool_call>{\\"name\\":\\"search_outfits\\","
    "\\"arguments\\":{...}}</tool_call>\\n"
    "3. KHONG bia outfit_id, khong bia gia; chi tool_call.\\n\\n"
    "Vi du 1:\\n"
    "User: Minh di lam van phong, style minimalist, ngan sach 800k\\n"
    "Assistant: <tool_call>{\\"name\\":\\"search_outfits\\",\\"arguments\\":"
    "{\\"occasion\\":\\"office\\",\\"style\\":\\"minimalist\\",\\"price_max\\":800000}"
    "}</tool_call>\\n\\n"
    "Vi du 2:\\n"
    "User: Dang qua le, di tiec cuoi nam, sang mot chut\\n"
    "Assistant: <tool_call>{\\"name\\":\\"search_outfits\\",\\"arguments\\":"
    "{\\"occasion\\":\\"party\\",\\"body_shape\\":\\"pear\\",\\"style\\":\\"elegant\\"}"
    "}</tool_call>"
)'''
assert old_prompt in m, "model prompt not found"
m = m.replace(old_prompt, new_prompt, 1)

old_sig = '''def generate_stylist_response(
    model: Any,
    processor: Any,
    user_prompt: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 0.9,
) -> str:'''
new_sig = '''def generate_stylist_response(
    model: Any,
    processor: Any,
    user_prompt: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 0.9,
    enable_thinking: bool | None = None,
) -> str:'''
assert old_sig in m, "model generate sig not found"
m = m.replace(old_sig, new_sig, 1)

old_template = '    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)'
new_template = '''    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )'''
assert old_template in m, "model apply_chat_template not found"
m = m.replace(old_template, new_template, 1)

model.write_text(m, encoding="utf-8")
print("patched model.py")

# ---------------------------------------------------------------------------
# 3) chat/page.tsx — split SSE on CRLF
# ---------------------------------------------------------------------------
page = ROOT / "web/src/app/chat/page.tsx"
p = page.read_text(encoding="utf-8").replace("\r\n", "\n")

old_split = '        const parts = buffer.split("\\n\\n");'
new_split = '        const parts = buffer.split(/\\r?\\n\\r?\\n/);'
assert old_split in p, "page split not found"
p = p.replace(old_split, new_split, 1)

page.write_text(p, encoding="utf-8")
print("patched chat/page.tsx")
print("ALL PATCHES APPLIED")
