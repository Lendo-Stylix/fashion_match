import io, os

p = "scripts/stylist/grpo_rewards.py"
with io.open(p, encoding="utf-8") as f:
    lines = f.readlines()

# Find the CONCISE block start
idx = None
for i, ln in enumerate(lines):
    if ln.strip().startswith("_CONCISE ="):
        idx = i
        break
assert idx is not None, "CONCISE not found"

# Find the closing ")" of that assignment (next line that is just "    )")
end = idx + 1
while end < len(lines) and not lines[end].rstrip() == "    )":
    end += 1
assert end < len(lines), "CONCISE end not found"

# latin1-safe ascii version of the directive (no vietnamese diacritics to avoid encode issues)
new_block = (
    '    _CONCISE = (\n'
    '        "\\nQUAN TRONG: tra loi CUC NGAN (duoi 120 token), chi liet ke tu khoa / "\n'
    '        "enum / loi goi cong cu, KHONG giai thich dai. "\\n'
    '        "Vi du dung: \'smart_casual\' / \'nhan eo, chan vay a; ne quan bo sat hong\' / "\\n'
    '        "\'phu hop\' / \'Ban muon mac dip nao a?\' / \'search_outfits(occasion=wedding)\'."\n'
    '    )\n'
)
lines[idx:end + 1] = [new_block]
with io.open(p, "w", encoding="utf-8") as f:
    f.writelines(lines)
print("CONCISE block fixed (ascii-safe)")
