"""Add graduation + birthday to the occasion fallback map."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

old = '''            "school": ["đi học", "đến trường"],
            "date": ["hẹn hò", "hen ho", "date", "cưa"],
            "cafe_hangout": ["cafe", "cà phê", "đi chơi", "dạo phố", "tụ tập"],
            "party": ["tiệc", "party", "liên hoan"],'''
new = '''            "school": ["đi học", "đến trường", "tốt nghiệp", "graduation", "tốt nghiệp đại học"],
            "date": ["hẹn hò", "hen ho", "date", "cưa"],
            "cafe_hangout": ["cafe", "cà phê", "đi chơi", "dạo phố", "tụ tập"],
            "party": ["tiệc", "party", "liên hoan", "sinh nhật", "birthday", "sn", "kỷ niệm"],'''
assert old in s, "occasion map block not found"
s = s.replace(old, new, 1)
service.write_text(s, encoding="utf-8")
print("patched occasion map")
