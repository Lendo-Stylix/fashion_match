"""Remove now-unused `import json` from service.py (route owns serialization)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = ROOT / "src/outfitmatch/stylist/service.py"
s = service.read_text(encoding="utf-8").replace("\r\n", "\n")

old = "import json\nimport logging\nimport re\nfrom collections.abc import Callable"
new = "import logging\nimport re\nfrom collections.abc import Callable"
assert old in s, "import block not found"
s = s.replace(old, new, 1)
service.write_text(s, encoding="utf-8")
print("removed unused json import from service.py")
