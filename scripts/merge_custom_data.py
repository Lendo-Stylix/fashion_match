"""Merge validated custom data into data/raw/.

Runs validate first; aborts if errors found.

Usage:
    uv run python scripts/merge_custom_data.py --phase 1A
    uv run python scripts/merge_custom_data.py --phase 1B
    uv run python scripts/merge_custom_data.py --phase 1C
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_CUSTOM = ROOT / "data" / "custom"
DATA_RAW = ROOT / "data" / "raw"


def _run_validate(phase: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_custom_data.py"), "--phase", phase],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        print("\nValidation failed — aborting merge.")
        sys.exit(1)


def merge_1a() -> None:
    src_csv = DATA_CUSTOM / "body" / "body_labels.csv"
    dst_csv = DATA_RAW / "body" / "body_labels.csv"
    src_img = DATA_CUSTOM / "body" / "images"
    dst_img = DATA_RAW / "body" / "images"

    dst_csv.parent.mkdir(parents=True, exist_ok=True)
    dst_img.mkdir(parents=True, exist_ok=True)

    # Copy images
    copied_images = 0
    for img in src_img.glob("*"):
        dst = dst_img / img.name
        if not dst.exists():
            shutil.copy2(img, dst)
            copied_images += 1

    # Append rows to CSV (avoid duplicates by image_id)
    existing_ids: set[str] = set()
    if dst_csv.exists():
        with open(dst_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_ids.add(row["image_id"])

    new_rows = []
    with open(src_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["image_id"] not in existing_ids:
                new_rows.append(row)

    write_header = not dst_csv.exists()
    with open(dst_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f"[1A] Merged: {len(new_rows)} new rows, {copied_images} new images")


def merge_1b() -> None:
    src_csv = DATA_CUSTOM / "catalog" / "catalog_metadata.csv"
    dst_parquet = DATA_RAW / "catalog" / "catalog_metadata.parquet"
    src_img = DATA_CUSTOM / "catalog" / "images"
    dst_img = DATA_RAW / "catalog" / "images"

    dst_parquet.parent.mkdir(parents=True, exist_ok=True)
    dst_img.mkdir(parents=True, exist_ok=True)

    # Copy images
    copied_images = 0
    for img in src_img.glob("*"):
        dst = dst_img / img.name
        if not dst.exists():
            shutil.copy2(img, dst)
            copied_images += 1

    # Load existing parquet if present, merge with CSV, save back
    try:
        import pandas as pd
    except ImportError:
        print("pandas not installed — saving CSV only (run: uv add pandas pyarrow)")
        dst_csv = dst_parquet.with_suffix(".csv")
        existing_ids: set[str] = set()
        if dst_csv.exists():
            with open(dst_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing_ids.add(row["item_ID"])
        new_rows = []
        with open(src_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["item_ID"] not in existing_ids:
                    new_rows.append(row)
        write_header = not dst_csv.exists()
        with open(dst_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(new_rows)
        print(f"[1B] Merged: {len(new_rows)} new rows (CSV fallback), {copied_images} images")
        return

    new_df = pd.read_csv(src_csv)
    if dst_parquet.exists():
        existing_df = pd.read_parquet(dst_parquet)
        existing_ids_set = set(existing_df["item_ID"].tolist())
        new_df = new_df[~new_df["item_ID"].isin(existing_ids_set)]
        merged = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        merged = new_df

    merged.to_parquet(dst_parquet, index=False)
    print(f"[1B] Merged: {len(new_df)} new rows → {dst_parquet}, {copied_images} images")


def merge_1c() -> None:
    src_jsonl = DATA_CUSTOM / "outfits" / "outfits.jsonl"
    dst_jsonl = DATA_RAW / "outfits" / "outfits.jsonl"

    dst_jsonl.parent.mkdir(parents=True, exist_ok=True)

    existing_ids: set[str] = set()
    if dst_jsonl.exists():
        with open(dst_jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    existing_ids.add(obj.get("outfit_id", ""))

    new_count = 0
    with open(src_jsonl, encoding="utf-8") as src, \
         open(dst_jsonl, "a", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("outfit_id") not in existing_ids:
                dst.write(json.dumps(obj, ensure_ascii=False) + "\n")
                new_count += 1

    print(f"[1C] Merged: {new_count} new outfit rows → {dst_jsonl}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=["1A", "1B", "1C"])
    parser.add_argument("--skip-validate", action="store_true",
                        help="Skip validation (not recommended)")
    args = parser.parse_args()

    if not args.skip_validate:
        print(f"Running validation for Phase {args.phase}...")
        _run_validate(args.phase)

    dispatch = {"1A": merge_1a, "1B": merge_1b, "1C": merge_1c}
    dispatch[args.phase]()

    print(f"\nDone! Next: dvc add data/raw/ && git add data/raw.dvc && git commit")


if __name__ == "__main__":
    main()
