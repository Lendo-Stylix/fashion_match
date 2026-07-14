import re
p = "scripts/stylist/grpo_rewards.py"
s = open(p, encoding="utf-8").read()

# Replace placeholder block with correct CONCISE definition (newline as "\n" escape)
new_concise = (
    '_CONCISE = (\n'
    '        "\\nQUAN TRỌNG: tra loi CUC NGAN (duoi 120 token), chi liet ke tu khoa / "\n'
    '        "enum / loi goi cong cu, KHONG giai thich dai. "\n'
    '        "Vi du dung: \'smart_casual\' / \'nhan eo, chan vay a; ne quan bo sat hong\' / "\n'
    '        "\'phu hop\' / \'Ban muon mac dip nao a?\' / \'search_outfits(occasion=wedding)\'."\n'
    '    )'
)
s = re.sub(r'_CONCISE = " "  # placeholder', new_concise, s, count=1)
open(p, "w", encoding="utf-8").write(s)
print("CONCISE block rewritten")
