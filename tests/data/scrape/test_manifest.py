from scripts.data.scrape.manifest import (
    BatchRecord,
    failed_batches,
    load_manifest,
    record_result,
    save_manifest,
)


def _rec(store: str, idx: int, status: str) -> BatchRecord:
    return BatchRecord(
        store_id=store,
        chunk_index=idx,
        status=status,
        item_count=10,
        blocking_codes=[] if status == "passed" else ["invalid_category"],
        metrics={"unisex_share": 0.5},
        updated_at="2026-06-01T00:00:00",
    )


def test_save_load_round_trip(tmp_path):
    path = tmp_path / "scrape_manifest.json"
    recs = {"dirtycoins#000": _rec("dirtycoins", 0, "passed")}
    save_manifest(recs, path)
    loaded = load_manifest(path)
    assert loaded["dirtycoins#000"].status == "passed"
    assert loaded["dirtycoins#000"].item_count == 10


def test_load_missing_returns_empty(tmp_path):
    assert load_manifest(tmp_path / "nope.json") == {}


def test_failed_batches_filters_non_passed():
    recs = {
        "a#000": _rec("a", 0, "passed"),
        "a#001": _rec("a", 1, "quarantined"),
        "b#000": _rec("b", 0, "quarantined"),
    }
    assert failed_batches(recs) == ["a#001", "b#000"]


def test_record_result_upserts():
    from scripts.data.scrape.batch_gate import BatchGateResult
    from scripts.data.scrape.quality import QualityReport

    recs: dict[str, BatchRecord] = {}
    result = BatchGateResult(
        store_id="rubies",
        chunk_index=0,
        item_count=5,
        passed=True,
        report=QualityReport(5, 5, {}, {}, []),
        metrics={"unisex_share": 0.0},
        blocking_codes=[],
    )
    record_result(recs, result, status="passed", now="2026-06-01T01:00:00")
    assert recs["rubies#000"].status == "passed"
    assert recs["rubies#000"].item_count == 5
