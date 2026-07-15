"""Extend the keyword fallback: old money -> elegant; phối đồ/set đồ -> cafe_hangout."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

# 1) generic "phối đồ / set đồ" maps to a casual outing occasion
old_cafe = '            "cafe_hangout": ["cafe", "cà phê", "đi chơi", "dạo phố", "tụ tập"],'
new_cafe = '            "cafe_hangout": ["cafe", "cà phê", "đi chơi", "dạo phố", "tụ tập", "phối đồ", "set đồ", "mix đồ", "phối đồ nam", "phối đồ nữ"],'
assert old_cafe in s, "cafe_hangout line not found"
s = s.replace(old_cafe, new_cafe, 1)

# 2) style detection also recognizes English aliases not in STYLE_LABELS_VI
old_style = '''        style: str | None = None
        for st, label in STYLE_LABELS_VI.items():
            if label.lower() in text:
                style = st
                break'''
new_style = '''        style_aliases = {
            "elegant": ["old money", "oldmoney", "old_money", "thanh lịch", "sang trọng"],
            "minimalist": ["tối giản", "toi gian", "minimal"],
            "streetwear": ["streetwear", "đường phố", "duong pho"],
            "vintage": ["vintage", "cổ điển", "co dien"],
            "casual": ["casual", "thường ngày", "thuong ngay"],
            "korean": ["hàn", "korean", "han quoc"],
            "feminine": ["nữ tính", "nu tinh"],
            "sporty": ["thể thao", "the thao", "sporty"],
        }
        style: str | None = None
        for st, label in STYLE_LABELS_VI.items():
            if label.lower() in text:
                style = st
                break
        if style is None:
            for st, aliases in style_aliases.items():
                if any(a in text for a in aliases):
                    style = st
                    break'''
assert old_style in s, "style detection block not found"
s = s.replace(old_style, new_style, 1)

service.write_text(s, encoding="utf-8")
print("patched service.py (fallback style aliases + generic occasion)")
