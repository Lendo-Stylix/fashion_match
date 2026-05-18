"""Validate custom-collected data before merging into raw/.

Usage:
    uv run python scripts/validate_custom_data.py --phase 1A
    uv run python scripts/validate_custom_data.py --phase 1B
    uv run python scripts/validate_custom_data.py --phase 1C
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_CUSTOM = ROOT / "data" / "custom"

BODY_SHAPES = {"hourglass", "pear", "apple", "rectangle", "inverted_triangle"}
GENDERS = {"female", "male", "non_binary"}
SPLITS = {"train", "val", "test"}
CATEGORY1 = {"tops", "bottoms", "dresses", "outerwear", "shoes", "bags", "accessories"}
OCCASIONS = {"casual", "formal", "business_casual", "sport", "party", "beach", "date_night", "outdoor"}
ITEM_ROLES = {"top", "bottom", "shoes", "bag", "outerwear", "accessory"}


def _err(msg: str) -> None:
    print(f"  ERROR: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"  WARN:  {msg}")


def _ok(msg: str) -> None:
    print(f"  OK:    {msg}")


# ── Phase 1A ──────────────────────────────────────────────────────────────────

def validate_1a() -> int:
    """Validate data/custom/body/. Returns error count."""
    base = DATA_CUSTOM / "body"
    csv_path = base / "body_labels.csv"
    img_dir = base / "images"
    errors = 0

    print("\n[Phase 1A — Body Pipeline]")

    if not csv_path.exists():
        _err(f"Missing {csv_path}")
        return 1

    import csv
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            rows.append((i, row))

    ids_seen: set[str] = set()
    shape_counts: dict[str, int] = {s: 0 for s in BODY_SHAPES}

    for lineno, row in rows:
        image_id = row.get("image_id", "").strip()
        image_path = row.get("image_path", "").strip()
        body_shape = row.get("body_shape", "").strip()
        source = row.get("source", "").strip()
        split = row.get("split", "").strip()

        if not image_id:
            _err(f"Line {lineno}: empty image_id")
            errors += 1
        if image_id in ids_seen:
            _err(f"Line {lineno}: duplicate image_id '{image_id}'")
            errors += 1
        ids_seen.add(image_id)

        full_path = img_dir / image_path
        if not full_path.exists():
            _err(f"Line {lineno}: image not found: {full_path}")
            errors += 1

        if body_shape not in BODY_SHAPES:
            _err(f"Line {lineno}: invalid body_shape '{body_shape}' (must be one of {BODY_SHAPES})")
            errors += 1
        else:
            shape_counts[body_shape] += 1

        if not source:
            _err(f"Line {lineno}: empty source")
            errors += 1

        if split not in SPLITS:
            _err(f"Line {lineno}: invalid split '{split}'")
            errors += 1

        gender = row.get("gender", "").strip()
        if gender and gender not in GENDERS:
            _err(f"Line {lineno}: invalid gender '{gender}'")
            errors += 1

    total = len(rows)
    _ok(f"{total} rows validated")

    print("\n  Distribution:")
    for shape, count in shape_counts.items():
        pct = (count / total * 100) if total else 0
        flag = "⚠" if pct < 15 else "✓"
        print(f"    {flag} {shape:<20} {count:>4} ({pct:.1f}%)")

    if errors == 0:
        _ok("All checks passed!")
    return errors


# ── Phase 1B ──────────────────────────────────────────────────────────────────

def validate_1b() -> int:
    base = DATA_CUSTOM / "catalog"
    csv_path = base / "catalog_metadata.csv"
    img_dir = base / "images"
    errors = 0

    print("\n[Phase 1B — Catalog Encoder]")

    if not csv_path.exists():
        _err(f"Missing {csv_path}")
        return 1

    import csv
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            rows.append((i, row))

    ids_seen: set[str] = set()
    cat1_counts: dict[str, int] = {c: 0 for c in CATEGORY1}

    for lineno, row in rows:
        item_id = row.get("item_ID", "").strip()
        image_path = row.get("image_path", "").strip()
        text = row.get("text", "").strip()
        cat1 = row.get("category1", "").strip()
        source = row.get("source", "").strip()
        split = row.get("split", "").strip()

        if not item_id:
            _err(f"Line {lineno}: empty item_ID")
            errors += 1
        if item_id in ids_seen:
            _err(f"Line {lineno}: duplicate item_ID '{item_id}'")
            errors += 1
        ids_seen.add(item_id)

        full_path = img_dir / image_path
        if not full_path.exists():
            _err(f"Line {lineno}: image not found: {full_path}")
            errors += 1

        if len(text) < 10:
            _err(f"Line {lineno}: text too short ({len(text)} chars, min 10)")
            errors += 1
        elif len(text) > 200:
            _warn(f"Line {lineno}: text very long ({len(text)} chars)")

        if cat1 not in CATEGORY1:
            _err(f"Line {lineno}: invalid category1 '{cat1}'")
            errors += 1
        else:
            cat1_counts[cat1] += 1

        if not source:
            _err(f"Line {lineno}: empty source")
            errors += 1

        if split not in SPLITS:
            _err(f"Line {lineno}: invalid split '{split}'")
            errors += 1

    total = len(rows)
    _ok(f"{total} rows validated")

    print("\n  Distribution:")
    for cat, count in cat1_counts.items():
        pct = (count / total * 100) if total else 0
        print(f"    {cat:<15} {count:>4} ({pct:.1f}%)")

    if errors == 0:
        _ok("All checks passed!")
    return errors


# ── Phase 1C ──────────────────────────────────────────────────────────────────

def validate_1c() -> int:
    base = DATA_CUSTOM / "outfits"
    jsonl_path = base / "outfits.jsonl"
    errors = 0

    print("\n[Phase 1C — Outfit Composer]")

    if not jsonl_path.exists():
        _err(f"Missing {jsonl_path}")
        return 1

    rows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                _err(f"Line {i}: invalid JSON — {e}")
                errors += 1

    outfit_ids_seen: set[str] = set()
    compat_counts = {True: 0, False: 0}
    occasion_counts: dict[str, int] = {}

    for lineno, obj in rows:
        outfit_id = obj.get("outfit_id", "")
        items = obj.get("items", [])
        compatible = obj.get("compatible")
        occasion = obj.get("occasion")
        source = obj.get("source", "")
        split = obj.get("split", "")

        if not outfit_id:
            _err(f"Line {lineno}: empty outfit_id")
            errors += 1
        if outfit_id in outfit_ids_seen:
            _err(f"Line {lineno}: duplicate outfit_id '{outfit_id}'")
            errors += 1
        outfit_ids_seen.add(outfit_id)

        if not isinstance(items, list) or len(items) < 2:
            _err(f"Line {lineno}: outfit must have ≥ 2 items")
            errors += 1
        elif len(items) > 8:
            _warn(f"Line {lineno}: outfit has {len(items)} items (>8)")

        for item in items:
            if not isinstance(item, dict) or "item_ID" not in item:
                _err(f"Line {lineno}: item missing 'item_ID'")
                errors += 1
            role = item.get("role", "")
            if role and role not in ITEM_ROLES:
                _err(f"Line {lineno}: invalid role '{role}'")
                errors += 1

        if not isinstance(compatible, bool):
            _err(f"Line {lineno}: 'compatible' must be bool, got {type(compatible).__name__}")
            errors += 1
        else:
            compat_counts[compatible] += 1

        if occasion is not None:
            if occasion not in OCCASIONS:
                _err(f"Line {lineno}: invalid occasion '{occasion}'")
                errors += 1
            else:
                occasion_counts[occasion] = occasion_counts.get(occasion, 0) + 1

        if not source:
            _warn(f"Line {lineno}: empty source")

        if split not in SPLITS:
            _err(f"Line {lineno}: invalid split '{split}'")
            errors += 1

    total = len(rows)
    _ok(f"{total} rows validated")

    print(f"\n  Compatibility: {compat_counts[True]} positive / {compat_counts[False]} negative")
    if occasion_counts:
        print("  Occasions:")
        for occ, cnt in sorted(occasion_counts.items(), key=lambda x: -x[1]):
            print(f"    {occ:<20} {cnt}")

    if errors == 0:
        _ok("All checks passed!")
    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=["1A", "1B", "1C"],
                        help="Phase to validate")
    args = parser.parse_args()

    dispatch = {"1A": validate_1a, "1B": validate_1b, "1C": validate_1c}
    errors = dispatch[args.phase]()

    if errors > 0:
        print(f"\n{errors} error(s) found. Fix them before merging.")
        sys.exit(1)
    else:
        print("\nValidation passed. Run merge_custom_data.py --phase " + args.phase)


if __name__ == "__main__":
    main()
