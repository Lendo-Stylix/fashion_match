"""Aggregate structured experiment CSV files into a summary table.

Produces a Markdown summary table (suitable for RESULTS.md) and a per-commit
JSON snapshot from all CSV files found under docs/experiments/.

Example:
    uv run python -m scripts.metrics_summary --dir docs/experiments/
    uv run python -m scripts.metrics_summary --dir docs/experiments/ --format json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

EXPERIMENTS_DIR = Path("docs/experiments")


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO-8601 timestamp string, return datetime for sorting."""
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.min


def read_csv_metrics(csv_path: Path) -> list[dict[str, str]]:
    """Read a single experiment CSV and return its rows as dicts."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def aggregate_csv_files(csv_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Return {csv_filename: [rows]} grouped by filename."""
    if not csv_dir.exists():
        return {}
    result: dict[str, list[dict[str, str]]] = {}
    for path in sorted(csv_dir.glob("*.csv")):
        result[path.name] = read_csv_metrics(path)
    return result


def build_markdown_table(data: dict[str, list[dict[str, str]]]) -> str:
    """Build a Markdown table from aggregated experiment data.

    Columns: Experiment | Ablation | Metric | Value | Latest Timestamp
    """
    lines: list[str] = []
    lines.append("| Experiment | Ablation | Metric | Value | Timestamp |")
    lines.append("|---|---|---|---|---|")

    def latest_ts(rows: list[dict[str, str]]) -> datetime:
        timestamps = [_parse_timestamp(r.get("timestamp", "")) for r in rows]
        return max(timestamps) if timestamps else datetime.min

    sorted_experiments = sorted(data.items(), key=lambda kv: latest_ts(kv[1]))

    for filename, rows in sorted_experiments:
        latest = latest_ts(rows).strftime("%Y-%m-%d %H:%M") if rows else "---"
        lines.append("| **" + filename + "** | | | | " + latest + " |")
        by_ablation: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_ablation[row.get("ablation", "unknown")].append(row)
        for ablation, ablation_rows in sorted(by_ablation.items()):
            for r in ablation_rows:
                metric = r["metric"]
                val = r["value"]
                ts = r.get("timestamp", "---")
                lines.append("| | " + ablation + " | " + metric + " | " + val + " | " + ts + " |")
    return "\n".join(lines)


def build_json_report(data: dict[str, list[dict[str, str]]]) -> dict:
    """Build a structured JSON report."""
    report: dict = {
        "generated_at": datetime.now().isoformat(),
        "experiments": {},
    }
    for filename, rows in data.items():
        by_ablation: dict[str, dict[str, dict[str, str]]] = {}
        for row in rows:
            ab = row.get("ablation", "unknown")
            metric = row.get("metric", "unknown")
            if ab not in by_ablation:
                by_ablation[ab] = {}
            by_ablation[ab][metric] = {
                "value": row["value"],
                "timestamp": row.get("timestamp", ""),
                "commit_sha": row.get("commit_sha", ""),
            }
        report["experiments"][filename] = by_ablation
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate experiment CSVs into a Markdown / JSON summary.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=EXPERIMENTS_DIR,
        help="Directory containing experiment CSV files.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        dest="out_path",
        help="Write output to this file instead of stdout.",
    )
    args = parser.parse_args(argv)

    data = aggregate_csv_files(args.dir)
    if not data:
        print(f"No CSV files found in {args.dir}", file=sys.stderr)
        return 1

    if args.format == "markdown":
        output = build_markdown_table(data)
    else:
        output = json.dumps(build_json_report(data), ensure_ascii=False, indent=2)

    if args.out_path:
        args.out_path.parent.mkdir(parents=True, exist_ok=True)
        args.out_path.write_text(output + "\n", encoding="utf-8")
        print(f"Written to {args.out_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
