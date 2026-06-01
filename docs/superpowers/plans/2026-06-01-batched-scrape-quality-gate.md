# Batched Scrape with Per-Batch Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape theo batch (chunk N item / store) với **quality gate chạy trước khi merge** — batch đạt mới promote vào catalog chính; batch **quality-failed** (nghĩa là data lỗi/chất lượng kém, không phải script crash) bị quarantine + ghi manifest để agent tự rerun đúng batch đó bằng `--rescrape-failed`. Không còn "scrape hết rồi mới phát hiện data sai".

**Architecture:** Tái dùng bộ check row-level sẵn có trong `quality.py` bằng cách tách lõi `check_frames(df, df)` (in-memory). Mỗi store: fetch → normalize (1 lần, item_id ổn định) → **store-level yield gate** (parser sanity) → chunk thành batch `batch_size` item → mỗi chunk: download ảnh → **batch gate data-quality** (`check_frames` + metric) → đạt thì `write_frames` (promote), lỗi thì `write_quarantine` + ghi `scrape_manifest.json`. "Lỗi" ở đây là lỗi data: metadata lệch ảnh, thiếu field quan trọng, category/title/url/price/join sai, parser yield bất thường, v.v. Coding agent đọc manifest, viết regression test cho lỗi data mới phát hiện, fix parser/normalizer, rồi tự rerun `--rescrape-failed` trong session cho đến khi sạch.

**Tech Stack:** Python 3.13, `uv`, pandas (parquet), pytest, dataclasses, httpx (đã có). Không thêm dependency mới.

## Thuật ngữ trong plan

- `failed` / `quarantined` / `--rescrape-failed` luôn nói về **data-quality failure** của batch đã scrape, không nói về `pytest` fail hay network/session crash.
- Ví dụ quality-failed: category/title/colors/gender/formality không khớp ảnh; thiếu title/desc/price/sizes/image; join hoặc URL sai; duplicate item; parser drop bất thường (`yield` quá thấp).
- `test thất bại` trong các task bên dưới là checkpoint TDD do agent chủ động viết để khóa regression; nó khác với batch bị quality gate chặn.

## Execution contract for coding agent

- Coding agent tự chạy scraper trong session(s), ưu tiên tách theo store hoặc theo wave `--rescrape-failed` để log/manifest dễ truy vết.
- Khi session scrape phát hiện một lỗi data mới chưa có coverage, agent phải biến nó thành một failing regression test trước khi sửa code.
- User **không** phải inspect quarantine hay rerun thủ công trong quá trình; agent owns loop `scrape → quarantine → test fail → fix → rerun`.

---

## Bối cảnh (đã kiểm chứng trong code)

- `run.py` (`run_store`) duyệt **từng store**: `fetch_products` → `normalize_products` → `download_all` (drop ảnh lỗi) → `write_frames` (**append-merge thẳng vào parquet chung NGAY**). → store lỗi nhiễm catalog ngay lập tức.
- `quality.py` có `check_catalog(catalog_path, links_path)` → `QualityReport` (`QualityIssue` level/code/message/count/sample, `.ok`, `.error_count`) với bộ check row-level đầy đủ: dup item_id, invalid category, missing title, invalid colors JSON, missing image file, catalog↔link join, invalid store_id/url/price, sale>price. **Nhưng chỉ chạy trên toàn catalog SAU khi xong.**
- Chỉ **6 store active** (`config.active_stores()`): yody_vn, canifa_vn (`sitemap_html`), aristino_vn (`sitemap_product_json`), huelleyrose, dirtycoins, rubies (`shopify_like`); còn lại `platform="skip"`.
- `normalize_products` ổn định item_id qua `existing_link_map` (re-scrape không đổi id) → an toàn cho re-scrape.
- `download_all(items, client=client) -> set[str]` trả về id ảnh tải OK.

**Quyết định chốt:** batch = chunk `batch_size` item trong 1 store (mặc định 250 ≈ 1 trang); quality-fail → quarantine + manifest. `--rescrape-failed` là đường rerun do coding agent tự gọi trong session sau khi đã codify lỗi thành failing test; không yêu cầu user can thiệp thủ công giữa chừng. Chunk **sau normalize** ở tầng orchestration (không sửa fetch adapter; re-fetch dùng cache nên rẻ).

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `scripts/data/scrape/quality.py` | Tách `check_frames(catalog_df, links_df)` (lõi in-memory) + cờ `check_images` | Modify |
| `scripts/data/scrape/normalize.py` | Tách `to_catalog_frame` / `to_links_frame`; `write_frames` dùng lại | Modify |
| `scripts/data/scrape/batch_gate.py` | `GateThresholds`, `BatchGateResult`, `chunk_items`, `yield_ok`, `gate_batch`, `write_quarantine` | **Create** |
| `scripts/data/scrape/manifest.py` | `BatchRecord`, `load_manifest`/`save_manifest`, `failed_batches` | **Create** |
| `scripts/data/scrape/run.py` | `gate_and_promote` + tích hợp chunk-loop, `--batch-size`/`--gate`/`--rescrape-failed` (agent-driven rerun) | Modify |
| `tests/data/scrape/test_quality.py` | Test `check_frames` + `check_images=False` | Modify |
| `tests/data/scrape/test_normalize.py` | Test frame builders | Modify |
| `tests/data/scrape/test_batch_gate.py` | Test chunk/yield/gate/quarantine | **Create** |
| `tests/data/scrape/test_manifest.py` | Test manifest round-trip + failed_batches | **Create** |
| `tests/data/scrape/test_run_gate.py` | Test `gate_and_promote` routing | **Create** |
| `scripts/data/scrape/README.md` | Tài liệu lệnh batch/gate/rescrape agentic | Modify |

---

### Global execution rule: session loop + regression tests

- [ ] Mỗi vòng live scrape phải chạy trong session riêng (theo store hoặc theo wave `--rescrape-failed`) để giữ log/manifest/quarantine tách bạch.
- [ ] Nếu session phát hiện batch quality-failed do bug parser/normalize chưa có coverage, agent phải trích sample tối thiểu từ `quarantine/` hoặc raw cache và **viết failing pytest regression trước khi sửa code**.
- [ ] Sau khi fix, agent tự chạy lại test liên quan rồi rerun scraper (`--store ...` hoặc `--rescrape-failed`) cho đến khi manifest sạch hoặc gặp blocker external rõ ràng. User không cần can thiệp thủ công giữa chừng.

---

### Task 1: Tách `check_frames` (lõi in-memory) trong quality.py

**Files:**
- Modify: `scripts/data/scrape/quality.py` (`check_catalog:142`)
- Test: `tests/data/scrape/test_quality.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/data/scrape/test_quality.py`:

```python
def test_check_frames_validates_in_memory_without_files(tmp_path):
    import pandas as pd

    from scripts.data.scrape.quality import check_frames

    image = tmp_path / "data" / "custom" / "catalog" / "images" / "item_custom_00001.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x")
    catalog = pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_custom_00001.jpg",
                "title_vi": "Áo thun",
                "desc_vi": "cotton",
                "colors": '["đen"]',
                "collected_date": "2026-06-01",
                "collector": "unit",
            }
        ]
    )
    links = pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "store_id": "yody_vn",
                "source_product_id": "p1",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 199000,
                "sale_price_vnd": None,
                "sku": "S1",
                "in_stock": True,
                "available_sizes": '["M"]',
                "sizes_in_stock": '["M"]',
            }
        ]
    )
    assert check_frames(catalog, links, repo_root=tmp_path).ok


def test_check_frames_skip_image_check(tmp_path):
    import pandas as pd

    from scripts.data.scrape.quality import check_frames

    catalog = pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "category": "top",
                "image_path": "data/custom/catalog/images/missing.jpg",
                "title_vi": "Áo thun",
                "desc_vi": "cotton",
                "colors": '["đen"]',
                "collected_date": "2026-06-01",
                "collector": "unit",
            }
        ]
    )
    links = pd.DataFrame(
        [
            {
                "item_id": "item_custom_00001",
                "store_id": "yody_vn",
                "source_product_id": "p1",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 199000,
                "sale_price_vnd": None,
                "sku": "S1",
                "in_stock": True,
                "available_sizes": '["M"]',
                "sizes_in_stock": '["M"]',
            }
        ]
    )
    codes = {i.code for i in check_frames(catalog, links, repo_root=tmp_path).issues}
    assert "missing_image_file" in codes  # default checks images
    codes_off = {
        i.code for i in check_frames(catalog, links, repo_root=tmp_path, check_images=False).issues
    }
    assert "missing_image_file" not in codes_off
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_quality.py::test_check_frames_validates_in_memory_without_files -v`
Expected: FAIL — `ImportError: cannot import name 'check_frames'`

- [ ] **Step 3: Tách `check_frames` từ `check_catalog`**

Trong `quality.py`, thay toàn bộ thân `check_catalog` (từ `:142`) bằng: một `check_frames` chứa logic cũ (nhận DataFrame), và `check_catalog` chỉ đọc parquet rồi gọi `check_frames`. Cụ thể, đổi chữ ký + thân:

```python
def check_catalog(
    catalog_path: Path = CATALOG_PARQUET,
    links_path: Path = LINKS_PARQUET,
    *,
    repo_root: Path = REPO_ROOT,
) -> QualityReport:
    """Validate scraped catalog/link parquet files and return a quality report."""
    return check_frames(_read_parquet(catalog_path), _read_parquet(links_path), repo_root=repo_root)


def check_frames(
    catalog: pd.DataFrame,
    links: pd.DataFrame,
    *,
    repo_root: Path = REPO_ROOT,
    check_images: bool = True,
) -> QualityReport:
    """In-memory core of :func:`check_catalog` — validate already-loaded frames.

    ``check_images=False`` skips the image-file-existence check (used by the batch
    gate when images are downloaded separately or skipped).
    """
    issues: list[QualityIssue] = []
```

Giữ nguyên toàn bộ phần thân kiểm tra cũ (missing columns → ... → store_counts/category_counts → `return QualityReport(...)`), nhưng **bọc khối kiểm tra ảnh** trong `if check_images:`:

```python
    if check_images:
        image_paths = catalog["image_path"].fillna("").astype(str)
        missing_image = catalog.loc[
            ~image_paths.map(lambda p: bool(p) and (repo_root / p).exists())
        ]
        _issue(
            issues,
            level="error",
            code="missing_image_file",
            message="image_path must point to an existing local file",
            count=int(missing_image.shape[0]),
            sample=missing_image["image_path"],
        )
```

- [ ] **Step 4: Chạy test xác nhận PASS (kể cả test cũ)**

Run: `uv run pytest tests/data/scrape/test_quality.py -v`
Expected: PASS toàn bộ (3 test cũ vẫn xanh vì `check_catalog` chỉ delegate).

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/quality.py tests/data/scrape/test_quality.py
git commit -m "refactor(scrape): extract in-memory check_frames + check_images flag"
```

---

### Task 2: Frame builders trong normalize

**Files:**
- Modify: `scripts/data/scrape/normalize.py` (`write_frames:274` — tách dựng row)
- Test: `tests/data/scrape/test_normalize.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/data/scrape/test_normalize.py`:

```python
def test_to_frames_have_expected_columns():
    from scripts.data.scrape.normalize import to_catalog_frame, to_links_frame

    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    cat = to_catalog_frame(items)
    links = to_links_frame(items)
    assert {"item_id", "category", "gender", "formality", "colors"} <= set(cat.columns)
    assert {"item_id", "store_id", "price_vnd", "available_sizes"} <= set(links.columns)
    assert len(cat) == 1 and len(links) == 1
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_normalize.py::test_to_frames_have_expected_columns -v`
Expected: FAIL — `ImportError: cannot import name 'to_catalog_frame'`

- [ ] **Step 3: Tách frame builders + dùng lại trong `write_frames`**

Thêm 2 hàm ngay trước `write_frames` trong `normalize.py`:

```python
def to_catalog_frame(items: list[NormalizedItem]) -> pd.DataFrame:
    """One catalog-metadata row per item."""
    return pd.DataFrame(
        [
            {
                "item_id": it.item_id,
                "category": it.category,
                "source_product_type": it.source_product_type,
                "gender": it.gender,
                "formality": it.formality,
                "image_path": it.image_path,
                "title_vi": it.title_vi,
                "desc_vi": it.desc_vi,
                "colors": json.dumps(it.colors, ensure_ascii=False),
                "collected_date": it.collected_date,
                "collector": it.collector,
            }
            for it in items
        ]
    )


def to_links_frame(items: list[NormalizedItem]) -> pd.DataFrame:
    """One store-link row per item."""
    return pd.DataFrame(
        [
            {
                "item_id": it.item_id,
                "store_id": it.store_id,
                "source_product_id": it.source_product_id,
                "product_url": it.product_url,
                "price_vnd": int(it.price_vnd),
                "sale_price_vnd": (int(it.sale_price_vnd) if it.sale_price_vnd else None),
                "sku": it.sku,
                "in_stock": bool(it.in_stock),
                "available_sizes": json.dumps(it.available_sizes, ensure_ascii=False),
                "sizes_in_stock": json.dumps(it.sizes_in_stock, ensure_ascii=False),
            }
            for it in items
        ]
    )
```

Trong `write_frames`, thay đoạn dựng `cat_rows`/`link_rows` + `new_cat = pd.DataFrame(cat_rows)` / `new_link = pd.DataFrame(link_rows)` bằng:

```python
    new_cat = to_catalog_frame(items)
    new_link = to_links_frame(items)
```

(Giữ nguyên phần merge `if CATALOG_PARQUET.exists(): ...` phía sau.)

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/data/scrape/test_normalize.py -v`
Expected: PASS toàn bộ (test write_frames cũ vẫn xanh — output không đổi).

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/normalize.py tests/data/scrape/test_normalize.py
git commit -m "refactor(scrape): extract to_catalog_frame/to_links_frame"
```

---

### Task 3: Module `batch_gate.py`

**Files:**
- Create: `scripts/data/scrape/batch_gate.py`
- Test: `tests/data/scrape/test_batch_gate.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/data/scrape/test_batch_gate.py`:

```python
from pathlib import Path

from scripts.data.scrape.batch_gate import (
    GateThresholds,
    chunk_items,
    gate_batch,
    write_quarantine,
    yield_ok,
)
from scripts.data.scrape.normalize import NormalizedItem


def _item(tmp_path: Path, item_id: str, *, category: str = "top", price: int = 199000) -> NormalizedItem:
    img_rel = f"data/custom/catalog/images/{item_id}.jpg"
    img_abs = tmp_path / img_rel
    img_abs.parent.mkdir(parents=True, exist_ok=True)
    img_abs.write_bytes(b"x")
    return NormalizedItem(
        item_id=item_id,
        category=category,
        source_product_type="",
        gender="unisex",
        formality="casual",
        image_path=img_rel,
        image_url="https://cdn/x.jpg",
        title_vi="Áo thun",
        desc_vi="cotton",
        colors=["đen"],
        collected_date="2026-06-01",
        collector="unit",
        store_id="dirtycoins",
        source_product_id=item_id,
        product_url=f"https://dirtycoins.vn/p/{item_id}",
        price_vnd=price,
        sale_price_vnd=None,
        sku="SKU",
        in_stock=True,
        available_sizes=["M"],
        sizes_in_stock=["M"],
    )


def test_chunk_items_splits_by_size():
    xs = list(range(0, 7))
    assert chunk_items(xs, 3) == [[0, 1, 2], [3, 4, 5], [6]]
    assert chunk_items(xs, 0) == [xs]  # 0 → single chunk


def test_yield_ok():
    th = GateThresholds(min_yield=0.30)
    assert yield_ok(40, 100, th) is True
    assert yield_ok(10, 100, th) is False
    assert yield_ok(0, 0, th) is True  # no raws → not applicable


def test_gate_batch_passes_clean_chunk(tmp_path):
    items = [_item(tmp_path, "item_custom_00001"), _item(tmp_path, "item_custom_00002")]
    result = gate_batch(
        items, store_id="dirtycoins", chunk_index=0, repo_root=tmp_path
    )
    assert result.passed is True
    assert result.blocking_codes == []
    assert result.item_count == 2
    assert result.batch_id == "dirtycoins#000"


def test_gate_batch_quarantines_invalid_category(tmp_path):
    items = [
        _item(tmp_path, "item_custom_00001"),
        _item(tmp_path, "item_custom_00002", category="not_a_cat"),
    ]
    result = gate_batch(items, store_id="dirtycoins", chunk_index=1, repo_root=tmp_path)
    assert result.passed is False
    assert "invalid_category" in result.blocking_codes


def test_write_quarantine_persists_chunk(tmp_path):
    import pandas as pd

    items = [_item(tmp_path, "item_custom_00001", category="not_a_cat")]
    result = gate_batch(items, store_id="dirtycoins", chunk_index=2, repo_root=tmp_path)
    out_dir = write_quarantine(result, items, quarantine_dir=tmp_path / "quarantine")
    assert (out_dir / "catalog.parquet").exists()
    assert (out_dir / "links.parquet").exists()
    assert len(pd.read_parquet(out_dir / "catalog.parquet")) == 1
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_batch_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.data.scrape.batch_gate'`

- [ ] **Step 3: Viết module**

Tạo `scripts/data/scrape/batch_gate.py`:

```python
"""Per-batch quality gate for the scraper.

A *batch* is a chunk of ``batch_size`` normalized items from a single store. The
gate reuses the row-level checks in ``quality.check_frames`` (in-memory, no temp
files) and adds batch-level signals. A batch that fails is quarantined, never
merged into the main catalog. See run.py for the orchestration.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from scripts.data.scrape.base import CATALOG_DIR, REPO_ROOT
from scripts.data.scrape.normalize import NormalizedItem, to_catalog_frame, to_links_frame
from scripts.data.scrape.quality import QualityReport, check_frames

QUARANTINE_DIR: Path = CATALOG_DIR / "quarantine"

T = TypeVar("T")


@dataclass(frozen=True)
class GateThresholds:
    """Tunable gate parameters. Calibrate after the first real run."""

    batch_size: int = 250  # items per chunk (≈ one Shopify page)
    min_yield: float = 0.30  # normalized items / raw products (store-level parser sanity)


@dataclass(frozen=True)
class BatchGateResult:
    store_id: str
    chunk_index: int
    item_count: int
    passed: bool
    report: QualityReport
    metrics: dict[str, float]
    blocking_codes: list[str] = field(default_factory=list)

    @property
    def batch_id(self) -> str:
        return f"{self.store_id}#{self.chunk_index:03d}"


def chunk_items(items: list[T], size: int) -> list[list[T]]:
    """Split ``items`` into chunks of ``size`` (size<=0 → a single chunk)."""
    if size <= 0:
        return [list(items)]
    return [items[i : i + size] for i in range(0, len(items), size)]


def yield_ok(n_items: int, n_raws: int, thresholds: GateThresholds) -> bool:
    """Store-level parser sanity: enough raws survived normalize?"""
    if n_raws <= 0:
        return True
    return (n_items / n_raws) >= thresholds.min_yield


def gate_batch(
    items: list[NormalizedItem],
    *,
    store_id: str,
    chunk_index: int,
    thresholds: GateThresholds = GateThresholds(),
    repo_root: Path = REPO_ROOT,
    check_images: bool = True,
) -> BatchGateResult:
    """Run row-level checks on one chunk; pass only when no error-level issue."""
    report = check_frames(
        to_catalog_frame(items),
        to_links_frame(items),
        repo_root=repo_root,
        check_images=check_images,
    )
    blocking = sorted({issue.code for issue in report.issues if issue.level == "error"})
    unisex_share = (
        sum(1 for it in items if it.gender == "unisex") / len(items) if items else 0.0
    )
    metrics = {"unisex_share": round(unisex_share, 4)}
    return BatchGateResult(
        store_id=store_id,
        chunk_index=chunk_index,
        item_count=len(items),
        passed=not blocking,
        report=report,
        metrics=metrics,
        blocking_codes=blocking,
    )


def write_quarantine(
    result: BatchGateResult,
    items: list[NormalizedItem],
    *,
    quarantine_dir: Path = QUARANTINE_DIR,
) -> Path:
    """Persist a failed batch's frames for later inspection. Returns the dir."""
    out_dir = quarantine_dir / result.batch_id.replace("#", "__")
    out_dir.mkdir(parents=True, exist_ok=True)
    to_catalog_frame(items).to_parquet(out_dir / "catalog.parquet", index=False)
    to_links_frame(items).to_parquet(out_dir / "links.parquet", index=False)
    return out_dir


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/data/scrape/test_batch_gate.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/batch_gate.py tests/data/scrape/test_batch_gate.py
git commit -m "feat(scrape): per-batch quality gate (chunk + check_frames + quarantine)"
```

---

### Task 4: Module `manifest.py`

**Files:**
- Create: `scripts/data/scrape/manifest.py`
- Test: `tests/data/scrape/test_manifest.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/data/scrape/test_manifest.py`:

```python
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
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.data.scrape.manifest'`

- [ ] **Step 3: Viết module**

Tạo `scripts/data/scrape/manifest.py`:

```python
"""Scrape manifest: per-batch status for incremental, resumable scraping.

Records which (store, chunk) batches passed the gate and which were quarantined,
so ``run --rescrape-failed`` can re-run only the quality-gate failures.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.data.scrape.base import CATALOG_DIR
from scripts.data.scrape.batch_gate import BatchGateResult

MANIFEST_PATH: Path = CATALOG_DIR / "scrape_manifest.json"


@dataclass
class BatchRecord:
    store_id: str
    chunk_index: int
    status: str  # "passed" | "quarantined"
    item_count: int
    blocking_codes: list[str]
    metrics: dict[str, float]
    updated_at: str
    raw_count: int = 0

    @property
    def batch_id(self) -> str:
        return f"{self.store_id}#{self.chunk_index:03d}"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, BatchRecord]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: BatchRecord(**value) for key, value in raw.items()}


def save_manifest(records: dict[str, BatchRecord], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: asdict(rec) for key, rec in records.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_result(
    records: dict[str, BatchRecord],
    result: BatchGateResult,
    *,
    status: str,
    now: str,
    raw_count: int = 0,
) -> None:
    """Upsert a batch record from a gate result (mutates ``records``)."""
    records[result.batch_id] = BatchRecord(
        store_id=result.store_id,
        chunk_index=result.chunk_index,
        status=status,
        item_count=result.item_count,
        blocking_codes=list(result.blocking_codes),
        metrics=dict(result.metrics),
        updated_at=now,
        raw_count=raw_count,
    )


def failed_batches(records: dict[str, BatchRecord]) -> list[str]:
    """batch_ids whose status is not ``passed`` (sorted)."""
    return sorted(bid for bid, rec in records.items() if rec.status != "passed")
```

> Lưu ý: `BatchRecord` có field `raw_count` đặt cuối (có default) để `BatchRecord(**v)` đọc được manifest cũ thiếu khóa này. `asdict` bỏ qua `@property batch_id`.

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/data/scrape/test_manifest.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/manifest.py tests/data/scrape/test_manifest.py
git commit -m "feat(scrape): scrape manifest for batch status + failed-batch query"
```

---

### Task 5: Tích hợp gate vào `run.py` (`gate_and_promote` + flags)

**Files:**
- Modify: `scripts/data/scrape/run.py` (imports `:24-30`; `run_store:51`; `main:104`)
- Test: `tests/data/scrape/test_run_gate.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/data/scrape/test_run_gate.py`:

```python
import scripts.data.scrape.normalize as normalize
from scripts.data.scrape.batch_gate import GateThresholds
from scripts.data.scrape.config import StoreConfig
from scripts.data.scrape.run import gate_and_promote


def _store() -> StoreConfig:
    return StoreConfig(
        store_id="dirtycoins",
        store_name="Dirty Coins",
        website="https://dirtycoins.vn",
        platform="shopify_like",
        store_type="local_boutique",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("streetwear",),
    )


def _item(item_id: str, *, category: str = "top") -> normalize.NormalizedItem:
    return normalize.NormalizedItem(
        item_id=item_id,
        category=category,
        source_product_type="",
        gender="unisex",
        formality="casual",
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        image_url="https://cdn/x.jpg",
        title_vi="Áo thun",
        desc_vi="cotton",
        colors=["đen"],
        collected_date="2026-06-01",
        collector="unit",
        store_id="dirtycoins",
        source_product_id=item_id,
        product_url=f"https://dirtycoins.vn/p/{item_id}",
        price_vnd=199000,
        sale_price_vnd=None,
        sku="SKU",
        in_stock=True,
        available_sizes=["M"],
        sizes_in_stock=["M"],
    )


def test_gate_and_promote_routes_good_and_bad_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    import pandas as pd

    # batch_size=1 → 2 chunks: one valid, one invalid-category
    good = _item("item_custom_00001")
    bad = _item("item_custom_00002", category="not_a_cat")
    records: dict = {}
    promoted = gate_and_promote(
        _store(),
        [good, bad],
        raw_count=2,
        thresholds=GateThresholds(batch_size=1),
        download=False,
        client=None,
        repo_root=tmp_path,
        manifest=records,
        now="2026-06-01T00:00:00",
        check_images=False,
        quarantine_dir=tmp_path / "quarantine",
    )

    assert promoted == 1
    catalog = pd.read_parquet(tmp_path / "catalog_metadata.parquet")
    assert catalog["item_id"].tolist() == ["item_custom_00001"]  # only the good chunk merged
    assert records["dirtycoins#000"].status == "passed"
    assert records["dirtycoins#001"].status == "quarantined"
    assert (tmp_path / "quarantine" / "dirtycoins__001" / "catalog.parquet").exists()


def test_gate_and_promote_quarantines_whole_store_on_low_yield(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    records: dict = {}
    promoted = gate_and_promote(
        _store(),
        [_item("item_custom_00001")],
        raw_count=100,  # yield 1/100 < 0.30 → store-level fail
        thresholds=GateThresholds(batch_size=250, min_yield=0.30),
        download=False,
        client=None,
        repo_root=tmp_path,
        manifest=records,
        now="2026-06-01T00:00:00",
        check_images=False,
        quarantine_dir=tmp_path / "quarantine",
    )
    assert promoted == 0
    assert not (tmp_path / "catalog_metadata.parquet").exists()
    assert records["dirtycoins#ALL"].status == "quarantined"
    assert "low_yield" in records["dirtycoins#ALL"].blocking_codes
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_run_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'gate_and_promote'`

- [ ] **Step 3: Thêm imports vào `run.py`**

Sau khối import hiện có (sau `:30`):

```python
from .batch_gate import (
    GateThresholds,
    chunk_items,
    gate_batch,
    now_iso,
    write_quarantine,
)
from .batch_gate import QUARANTINE_DIR
from .manifest import BatchRecord, MANIFEST_PATH, failed_batches, load_manifest, record_result, save_manifest
```

- [ ] **Step 4: Thêm `gate_and_promote` + store-level low-yield branch**

Thêm hàm mới trong `run.py` (trước `run_store`):

```python
def gate_and_promote(
    store: StoreConfig,
    items: list,
    raw_count: int,
    *,
    thresholds: GateThresholds,
    download: bool,
    client,
    repo_root,
    manifest: dict,
    now: str,
    check_images: bool = True,
    quarantine_dir=QUARANTINE_DIR,
) -> int:
    """Chunk → per-chunk gate → promote (write_frames) or quarantine. Returns promoted count.

    A store-level low yield (parser broke, dropped too much) quarantines the whole
    store as ``<store>#ALL`` and promotes nothing.
    """
    from .batch_gate import yield_ok

    if not yield_ok(len(items), raw_count, thresholds):
        result = gate_batch(
            items, store_id=store.store_id, chunk_index=0, thresholds=thresholds,
            repo_root=repo_root, check_images=check_images,
        )
        manifest[f"{store.store_id}#ALL"] = BatchRecord(
            store_id=store.store_id,
            chunk_index=-1,
            status="quarantined",
            item_count=len(items),
            blocking_codes=["low_yield"],
            metrics={"yield": round(len(items) / raw_count, 4) if raw_count else 1.0},
            updated_at=now,
            raw_count=raw_count,
        )
        if items:
            write_quarantine(result, items, quarantine_dir=quarantine_dir)
        logger.warning(
            "[%s] low yield %d/%d → whole store quarantined", store.store_id, len(items), raw_count
        )
        return 0

    promoted = 0
    for idx, chunk in enumerate(chunk_items(items, thresholds.batch_size)):
        if download:
            ok_ids = download_all(chunk, client=client)
            chunk = [it for it in chunk if it.item_id in ok_ids]
        if not chunk:
            continue
        result = gate_batch(
            chunk,
            store_id=store.store_id,
            chunk_index=idx,
            thresholds=thresholds,
            repo_root=repo_root,
            check_images=check_images,
        )
        if result.passed:
            write_frames(chunk)
            promoted += len(chunk)
            status = "passed"
        else:
            write_quarantine(result, chunk, quarantine_dir=quarantine_dir)
            status = "quarantined"
            logger.warning(
                "[%s] chunk %d quarantined: %s",
                store.store_id,
                idx,
                ",".join(result.blocking_codes),
            )
        record_result(manifest, result, status=status, now=now)
    return promoted
```

- [ ] **Step 5: Chạy test xác nhận PASS**

Run: `uv run pytest tests/data/scrape/test_run_gate.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Nối `gate_and_promote` vào `run_store` + flags trong `main`**

Trong `run_store`, thay nhánh ghi cuối (`if download: ... write_frames(items); return len(items)`) bằng đường gate khi bật. Đổi chữ ký `run_store` thêm tham số:

```python
def run_store(
    store: StoreConfig,
    *,
    use_cache: bool,
    limit: int | None,
    download: bool,
    collector: str,
    offline: bool = False,
    dry_run: bool = False,
    gate: bool = True,
    thresholds: GateThresholds = GateThresholds(),
    manifest: dict | None = None,
    only_chunks: set[int] | None = None,
) -> int:
```

Trong thân, sau khi có `items` (và xử lý `dry_run` như cũ), thay khối download+write_frames bằng:

```python
        raw_count = len(raws)
        if not gate:
            if download:
                ok_ids = download_all(items, client=client)
                items = [it for it in items if it.item_id in ok_ids]
            if not items:
                return 0
            write_frames(items)
            return len(items)

        if only_chunks is not None:
            chunks = chunk_items(items, thresholds.batch_size)
            items = [it for idx in sorted(only_chunks) if idx < len(chunks) for it in chunks[idx]]
            raw_count = len(items)  # re-scrape mode: yield gate not re-applied to subset
            if not items:
                return 0

        return gate_and_promote(
            store,
            items,
            raw_count,
            thresholds=thresholds,
            download=download,
            client=client,
            repo_root=REPO_ROOT,
            manifest=manifest if manifest is not None else {},
            now=now_iso(),
        )
```

Thêm import `REPO_ROOT`: trong khối import `from .base import new_client` đổi thành:

```python
from .base import REPO_ROOT, new_client
```

Trong `main`, thêm args và load/save manifest:

```python
    p.add_argument("--batch-size", type=int, default=250, help="Items per quality-gated batch")
    p.add_argument("--min-yield", type=float, default=0.30, help="Min normalized/raw ratio per store")
    p.add_argument("--no-gate", action="store_true", help="Disable quality gate (legacy direct write)")
    p.add_argument(
        "--rescrape-failed",
        action="store_true",
        help="Only re-run store/chunks marked quality-failed in the manifest",
    )
```

Và phần điều phối trong `main` (thay vòng lặp store hiện tại):

```python
    thresholds = GateThresholds(batch_size=args.batch_size, min_yield=args.min_yield)
    manifest = load_manifest()

    if args.rescrape_failed:
        targets = failed_batches(manifest)
        if not targets:
            logger.info("no quality-failed batches in manifest — nothing to re-scrape")
            return 0
        by_store: dict[str, set[int]] = {}
        for bid in targets:
            store_id, _, chunk = bid.partition("#")
            by_store.setdefault(store_id, set())
            if chunk != "ALL":
                by_store[store_id].add(int(chunk))
        stores = [STORES_BY_ID[s] for s in by_store if s in STORES_BY_ID]
        only_for = {s.store_id: (by_store[s.store_id] or None) for s in stores}
    else:
        stores = _select_stores(args.store)
        only_for = {}

    total = 0
    summary: list[tuple[str, int]] = []
    for s in stores:
        n = run_store(
            s,
            use_cache=True,
            limit=args.limit,
            download=not args.no_images,
            collector=args.collector,
            offline=args.offline,
            dry_run=args.dry_run,
            gate=not args.no_gate,
            thresholds=thresholds,
            manifest=manifest,
            only_chunks=only_for.get(s.store_id),
        )
        total += n
        summary.append((s.store_id, n))

    if not args.dry_run and not args.no_gate:
        save_manifest(manifest)
        bad = failed_batches(manifest)
        if bad:
            logger.warning("quarantined batches (%d): %s", len(bad), ", ".join(bad))
```

(Giữ nguyên phần log `summary` + `return 0 if total > 0 else 1` cuối hàm.)

- [ ] **Step 7: Chạy lại test gate + smoke import**

Run: `uv run pytest tests/data/scrape/test_run_gate.py -v`
Run: `uv run python -c "import scripts.data.scrape.run"`
Expected: test PASS; import không lỗi.

- [ ] **Step 8: Commit**

```bash
git add scripts/data/scrape/run.py tests/data/scrape/test_run_gate.py
git commit -m "feat(scrape): batched run with quality gate, quarantine, --rescrape-failed"
```

---

### Task 6: Full check + docs

- [ ] **Step 1: Full test + lint**

Run: `uv run pytest -q`
Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests && uv run mypy src`
Expected: tất cả xanh. (Nếu ruff báo import order → `uv run ruff check --fix .` rồi chạy lại.)

- [ ] **Step 2: Smoke chạy gate trên 1 store (offline, cache)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.run --store dirtycoins --offline --no-images --batch-size 100
```
Expected: log có dòng promote/quarantine per chunk; sinh `data/custom/catalog/scrape_manifest.json`. (`--no-images` ⇒ gate bỏ check ảnh — xem ghi chú dưới.)

> ⚠️ **Ghi chú `--no-images` + gate:** khi bỏ tải ảnh, gate vẫn check ảnh và sẽ quarantine. Trong `run_store`, truyền `check_images=not no_images` xuống `gate_and_promote` để smoke `--no-images` không quarantine oan. **Bổ sung ở Step 3 nếu chưa có.**

- [ ] **Step 3: Truyền `check_images` theo `--no-images`**

Trong `run_store`, lời gọi `gate_and_promote(...)` thêm `check_images=download` (download=False khi `--no-images` ⇒ skip image check). Sửa dòng gọi:

```python
        return gate_and_promote(
            store,
            items,
            raw_count,
            thresholds=thresholds,
            download=download,
            client=client,
            repo_root=REPO_ROOT,
            manifest=manifest if manifest is not None else {},
            now=now_iso(),
            check_images=download,
        )
```

Chạy lại: `uv run pytest tests/data/scrape/test_run_gate.py -q` → PASS.

- [ ] **Step 4: Docs**

`scripts/data/scrape/README.md` — thêm mục:

```markdown
## Batched scrape with quality gate

Mỗi store được chia thành batch `--batch-size` item; mỗi batch qua quality gate
(`check_frames`) trước khi merge. Batch lỗi bị quarantine vào
`data/custom/catalog/quarantine/<store>__<chunk>/` và ghi `scrape_manifest.json`
— KHÔNG nhiễm catalog chính.

```bash
# scrape có gate (mặc định), batch 250 item
uv run python -m scripts.data.scrape.run --batch-size 250
# agent chỉ chạy lại các batch quality-failed
uv run python -m scripts.data.scrape.run --rescrape-failed
# tắt gate (ghi trực tiếp như cũ)
uv run python -m scripts.data.scrape.run --no-gate
```

Gate quarantine một batch khi phát hiện **lỗi chất lượng data**: metadata sai/thiếu
(sai category, thiếu title/desc, ảnh lỗi, dup, url/price/join sai, v.v.) hoặc
store có yield (item/raw) < `--min-yield`.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/run.py scripts/data/scrape/README.md
git commit -m "docs(scrape): batched gate usage + check_images wiring"
```

---

## Self-Review

**1. Spec coverage**
- Chia scrape thành nhiều batch → `chunk_items` + per-chunk gate (Task 3, 5). ✔
- Quality gate kiểm tra **chất lượng data** → `check_frames` reuse + store-level `yield_ok` (Task 1, 3). ✔
- `failed` được định nghĩa rõ là **quality-failed** (data sai/thiếu/không khớp ảnh), không phải infra/test fail. ✔
- Phát hiện vấn đề trước khi merge → gate chạy trước `write_frames`; chỉ promote batch đạt (Task 5). ✔
- Re-scrape nếu cần → quarantine + `scrape_manifest.json` + `--rescrape-failed` chạy lại đúng batch quality-failed (Task 4, 5). ✔
- Coding agent owns loop session + regression-test-writing; user không cần can thiệp thủ công trong quá trình. ✔
- Tránh "scrape hết rồi mới lỗi" → batch đạt promote ngay, batch lỗi cô lập, không nhiễm (Task 5). ✔

**2. Placeholder scan** — mọi code step có code thật + lệnh + expected. Không TODO/“xử lý phù hợp”.

**3. Type consistency** — `BatchGateResult.batch_id` (`store#NNN`) khớp `BatchRecord.batch_id` và key manifest; `gate_batch`/`gate_and_promote`/`record_result` cùng chữ ký field; `to_catalog_frame`/`to_links_frame` dùng chung bởi write_frames + gate + quarantine (DRY); `check_frames(..., check_images)` dùng nhất quán ở gate.

## Out of scope (follow-up riêng)
1. **Thêm enum-validation gender/formality vào `quality.py`** (`CATALOG_COLUMNS` hiện thiếu gender/formality). Cần cập nhật fixture test_quality kèm theo → tách plan riêng để không phình task này.
2. **True page-streaming** (fetch từng trang, gate rồi mới fetch trang sau) — chặn sớm hơn cho store cực lớn. Hiện chunk-sau-normalize đã đủ vì re-fetch dùng cache; nâng cấp sau nếu cần.
3. **Auto-retry transient network errors** trước khi quarantine quality-fail. Hiện MVP vẫn dùng agent-managed rerun loop (`--rescrape-failed`), không yêu cầu human rerun.

## Lưu ý khi thực thi
- `min_yield`, `batch_size` là giá trị khởi điểm — calibrate sau lần chạy thật đầu tiên (xem phân bố yield per store trong log/manifest).
- Re-scrape ổn định nhờ `existing_link_map` trong `normalize_products` (item_id không đổi) — chunk_index ổn định vì thứ tự upstream ổn định + cache.
- Gate cố ý nghiêng về *quarantine khi nghi ngờ*; agent nên inspect `quarantine/<batch>/`, codify lỗi thành regression test, rồi rerun tự động. User không cần xem thủ công giữa chừng.
