from pathlib import Path

from outfitmatch.export import append_result_row, read_results


def test_append_and_read(tmp_path: Path):
    csv = tmp_path / "ablation.csv"
    append_result_row(csv, {"name": "a", "recall@5": 0.5})
    append_result_row(csv, {"name": "b", "recall@5": 0.7})
    rows = read_results(csv)
    assert len(rows) == 2
    assert rows[0]["name"] == "a"
    assert rows[1]["name"] == "b"
    assert float(rows[1]["recall@5"]) == 0.7


def test_creates_parent_dirs(tmp_path: Path):
    csv = tmp_path / "nested" / "deep" / "results.csv"
    append_result_row(csv, {"k": "v"})
    assert csv.exists()
