"""Fix 3b: when the explicit tool_call is invalid, try keyword fallback
(uses canonical enum values) before erroring. Exact string replace."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

old_block = '''        if payload is not None:
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
                records = self._execute_tool_call(payload)'''
new_block = '''        if payload is not None:
            ok, errors = self._validate_tool_call(payload)
            if not ok:
                # Explicit tool_call malformed (bad enum / wrong type).
                # Try the keyword fallback (canonical enum values) before giving up.
                inferred = self._infer_request(user_message, response)
                if inferred is not None and self._validate_tool_call(inferred)[0]:
                    payload = inferred
                else:
                    yield {
                        "type": "error",
                        "data": f"tool_call không hợp lệ: {errors[0]}"
                        if errors
                        else "tool_call không hợp lệ",
                    }
                    return

            try:
                records = self._execute_tool_call(payload)'''
assert old_block in s, "service invalid-tool-call block not found"
s = s.replace(old_block, new_block, 1)
service.write_text(s, encoding="utf-8")
print("patched service.py (fallback)")

# tools.py: accept a bare exclude_colors string (wrap into a list)
tools = ROOT / "src/outfitmatch/stylist/tools.py"
t = tools.read_text(encoding="utf-8").replace("\r\n", "\n")

old_excl = (
    '        elif key == "exclude_colors" and (\n'
    "            not isinstance(value, list) or any(not isinstance(item, str) for item in value)\n"
    "        ):\n"
    '            errors.append("exclude_colors must be an array of strings")'
)
new_excl = (
    '        elif key == "exclude_colors":\n'
    "            if isinstance(value, str):\n"
    "                # Tolerate a bare string (wrap into a single-element list).\n"
    "                arguments[key] = [value]\n"
    "            elif not isinstance(value, list) or any(\n"
    "                not isinstance(item, str) for item in value\n"
    "            ):\n"
    '                errors.append("exclude_colors must be an array of strings")'
)
assert old_excl in t, "tools exclude_colors block not found"
t = t.replace(old_excl, new_excl, 1)
tools.write_text(t, encoding="utf-8")
print("patched tools.py (exclude_colors)")
print("PATCH 3b DONE")
