"""
core/payload_parser.py — Parse dữ liệu có cấu trúc nhúng trong HTML.

Hỗ trợ:
  - __NUXT_DATA__ (Nuxt.js / Vue)  → Coolmate
  - __NEXT_DATA__ (Next.js / React) → một số web khác
  - JSON-LD structured data         → fallback tổng quát
"""

import json
import re
from typing import Optional


def _safe_json(text: str) -> Optional[dict | list]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ── Nuxt.js ───────────────────────────────────────────────────────────────────

def parse_nuxt_data(html: str) -> Optional[dict]:
    """
    Tìm và parse __NUXT_DATA__ từ HTML của trang Nuxt.js.
    Coolmate dùng format này.
    """
    # Format 1: <script id="__NUXT_DATA__" type="application/json">...</script>
    match = re.search(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if match:
        return _safe_json(match.group(1).strip())

    # Format 2: window.__NUXT__={...}
    match = re.search(
        r'window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>',
        html, re.DOTALL
    )
    if match:
        return _safe_json(match.group(1))

    return None


# ── Next.js ───────────────────────────────────────────────────────────────────

def parse_next_data(html: str) -> Optional[dict]:
    """
    Tìm và parse __NEXT_DATA__ từ HTML của trang Next.js.
    """
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if match:
        return _safe_json(match.group(1).strip())
    return None


# ── JSON-LD ───────────────────────────────────────────────────────────────────

def parse_json_ld(html: str) -> list[dict]:
    """
    Tìm tất cả JSON-LD structured data trong trang.
    Thường chứa Product schema với price, name, image, availability.
    """
    results = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    ):
        data = _safe_json(match.group(1).strip())
        if data:
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
    return results


def extract_product_from_json_ld(json_ld_list: list[dict]) -> Optional[dict]:
    """Tìm object có @type='Product' trong danh sách JSON-LD."""
    for item in json_ld_list:
        if isinstance(item, dict) and item.get("@type") == "Product":
            return item
    return None


# ── Auto-detect & Extract ────────────────────────────────────────────────────

def detect_framework(html: str) -> str:
    """
    Phát hiện framework từ HTML.
    Returns: 'nuxt' | 'next' | 'react' | 'generic'
    """
    if "__NUXT_DATA__" in html or "window.__NUXT__" in html:
        return "nuxt"
    if "__NEXT_DATA__" in html:
        return "next"
    if 'id="root"' in html or 'id="__next"' in html:
        return "react"
    return "generic"


def try_extract_structured_data(html: str) -> tuple[str, Optional[dict | list]]:
    """
    Thử tất cả các phương pháp parse có cấu trúc.
    Returns: (method_name, data) hoặc ('none', None)
    """
    # 1. Nuxt
    data = parse_nuxt_data(html)
    if data:
        return "nuxt", data

    # 2. Next
    data = parse_next_data(html)
    if data:
        return "next", data

    # 3. JSON-LD
    json_ld = parse_json_ld(html)
    product = extract_product_from_json_ld(json_ld)
    if product:
        return "json_ld", product

    return "none", None
