"""Integration patches for the new frontend in web/:
1) write .env.local with backend URL
2) fix SSE CRLF split in src/lib/api.ts
3) add image remotePatterns to next.config.ts
Exact string replace with assertions."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1] / "web"

# 1) env
env = ROOT / ".env.local"
env.write_text("NEXT_PUBLIC_API_URL=http://localhost:8000\n", encoding="utf-8")
print("wrote .env.local")

# 2) api.ts CRLF split
api = ROOT / "src/lib/api.ts"
a = api.read_text(encoding="utf-8").replace("\r\n", "\n")
old_split = '        const parts = buffer.split("\\n\\n");'
new_split = '        const parts = buffer.split(/\\r?\\n\\r?\\n/);'
assert old_split in a, "api.ts split not found"
a = a.replace(old_split, new_split, 1)
api.write_text(a, encoding="utf-8")
print("patched api.ts (CRLF SSE split)")

# 3) next.config.ts image allowlist
cfg = ROOT / "next.config.ts"
c = cfg.read_text(encoding="utf-8").replace("\r\n", "\n")
old_cfg = "const nextConfig: NextConfig = {\n  output: \"standalone\","
new_cfg = (
    "const nextConfig: NextConfig = {\n"
    "  output: \"standalone\",\n"
    "  images: {\n"
    "    // Allow backend-served / remote product images (localhost dev + https).\n"
    "    remotePatterns: [\n"
    "      { protocol: \"http\", hostname: \"localhost\" },\n"
    "      { protocol: \"https\", hostname: \"**\" },\n"
    "    ],\n"
    "  },"
)
assert old_cfg in c, "next.config.ts marker not found"
c = c.replace(old_cfg, new_cfg, 1)
cfg.write_text(c, encoding="utf-8")
print("patched next.config.ts (image allowlist)")
print("FRONTEND INTEGRATE PATCHES DONE")
