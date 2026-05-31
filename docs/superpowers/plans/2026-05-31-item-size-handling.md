# Item Size Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cứu thông tin size từ scraper về `ItemRecord`, giữ `OutfitRecord` size-agnostic, và thêm bộ resolver rule-based body→size chạy ở runtime (Tầng 4) có chống hallucinate.

**Architecture:** Size được tách thành 3 vai trò độc lập: (1) *catalog fact* — tập size có thật của từng item, lưu trong `item_store_links.parquet` rồi nạp vào `ItemRecord.store`; (2) *template* — `OutfitRecord` KHÔNG mang size vì OutfitTransformer chỉ chấm compatibility thị giác và một outfit dùng lại cho nhiều người; (3) *runtime decision* — `suggest_size(category, gender, height, weight, available_sizes)` map body sang alpha-size rồi giao với tập size còn hàng, Qwen3-VL chỉ *trình bày* size và bị validate trong tập size có thật.

**Tech Stack:** Python 3.13, `uv`, pandas (parquet), pytest, dataclasses. Không thêm dependency mới.

---

## Bối cảnh & quyết định chốt

Trạng thái hiện tại (đã kiểm chứng trong code):

- `RawProduct.variants` (`scripts/data/scrape/shopify.py:48`) **có** size trong các field `option1/option2/option3`, nhưng `normalize.py` chỉ trích `price`/`sku`/`in_stock` rồi **bỏ size**.
- `catalog_metadata.parquet` (5845 items) và `item_store_links.parquet` **không có** cột size.
- `ItemRecord` (`src/outfitmatch/kb/schema.py:9`) và `OutfitRecord` (`:21`) **không có** field size.
- `_infer_colors` (`normalize.py:79`) đã có heuristic *loại bỏ* chuỗi giống size khỏi colors → ta viết hàm nghịch đảo để *giữ lại* size.

Quyết định MVP (người dùng đã chốt): **"gợi ý size theo body (rule-based)"**.

Phạm vi sizing MVP: chỉ map body→size cho **alpha-size categories** (`top`, `dress`, `outerwear`). Bottoms (số eo) và shoes (EU) chỉ hiển thị `available_sizes`, không suy ra từ body trong MVP.

> ⚠️ Catalog hiện tại đã mất size. Sau khi code xong cần **backfill** bằng cách chạy lại normalize offline trên raw cache (Task 6) — không cần gọi mạng.

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `scripts/data/scrape/normalize.py` | Trích `available_sizes` + `sizes_in_stock` từ variants, ghi vào link parquet | Modify |
| `src/outfitmatch/kb/catalog.py` | Nạp 2 trường size vào `ItemRecord.store` | Modify |
| `src/outfitmatch/quiz/sizing.py` | Resolver body→size, deterministic, rule-based | **Create** |
| `src/outfitmatch/stylist/validation.py` | Guard chống Qwen bịa size | Modify |
| `src/outfitmatch/pipeline.py` | Thêm field `suggested_sizes` vào `RecommendResult` (điểm tích hợp Sprint 8) | Modify |
| `docs/datasets/STORE_CATALOG_VN.md`, `Kien_truc_v3.1.md` | Ghi schema size + ghi chú Tầng 4 | Modify |
| `tests/data/scrape/test_normalize.py` | Test trích size | Modify |
| `tests/kb/test_kb_catalog.py` | Test nạp size vào store | Modify |
| `tests/quiz/test_sizing.py` | Test resolver | **Create** |
| `tests/test_stylist.py` | Test guard size | Modify |
| `tests/test_pipeline_v31.py` | Test field mới | Modify |

**Nguyên tắc giữ nguyên:** `OutfitRecord` và `OutfitTransformer` KHÔNG đụng tới — đây là quyết định kiến trúc quan trọng nhất.

---

### Task 1: Trích size từ variants trong normalize

**Files:**
- Modify: `scripts/data/scrape/normalize.py` (`LINK_COLUMNS:38`, thêm `_infer_sizes` cạnh `_infer_colors:79`, `NormalizedItem:119`, `normalize_products:206`, `write_frames` link_rows `:255`)
- Test: `tests/data/scrape/test_normalize.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/data/scrape/test_normalize.py`:

```python
def test_extracts_sizes_from_variants():
    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    it = items[0]
    # _raw() variants: (Trắng, M, available) + (Navy, L, not available)
    assert it.available_sizes == ["M", "L"]
    assert it.sizes_in_stock == ["M"]


def test_free_size_is_captured():
    raw = _raw(variants=[{"sku": "F", "price": "299000", "available": True, "option1": "Free size"}])
    items = normalize_products([raw], _store(), start_index=1, existing_link_map={})
    assert items[0].available_sizes == ["FREE SIZE"]


def test_write_frames_includes_size_columns(tmp_path, monkeypatch):
    import json

    import pandas as pd

    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    items = normalize_products([_raw()], _store(), existing_link_map={})
    write_frames(items)

    links = pd.read_parquet(tmp_path / "item_store_links.parquet")
    assert "available_sizes" in links.columns
    assert "sizes_in_stock" in links.columns
    assert json.loads(links.loc[0, "available_sizes"]) == ["M", "L"]
    assert json.loads(links.loc[0, "sizes_in_stock"]) == ["M"]
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_normalize.py::test_extracts_sizes_from_variants -v`
Expected: FAIL — `AttributeError: 'NormalizedItem' object has no attribute 'available_sizes'`

- [ ] **Step 3: Thêm `_infer_sizes` helper**

Chèn ngay sau `_infer_colors` (sau dòng `:98` trong `normalize.py`):

```python
# Inverse of _infer_colors: KEEP option strings that look like a size label.
_SIZE_LIKE_RE = re.compile(r"[XSMLxsml0-9.\-/ ]{1,8}")


def _looks_like_size(val: str) -> bool:
    v = val.strip()
    if not v:
        return False
    low = v.lower()
    if "size" in low or "kích" in low or "free" in low:
        return True
    return bool(_SIZE_LIKE_RE.fullmatch(v))


def _infer_sizes(variants: list[dict]) -> tuple[list[str], list[str]]:
    """Pull size labels from variant option fields.

    Returns (available_sizes, sizes_in_stock); the second is the subset whose
    variant has ``available == True``. Order of first appearance is preserved.
    Labels are upper-cased so "m"/"M" collapse. The inverse of _infer_colors.
    """
    all_sizes: list[str] = []
    in_stock: list[str] = []
    seen: set[str] = set()
    seen_stock: set[str] = set()
    for v in variants:
        for k in ("option1", "option2", "option3"):
            val = (v.get(k) or "").strip()
            if not val or not _looks_like_size(val):
                continue
            norm = val.upper()
            if norm not in seen:
                seen.add(norm)
                all_sizes.append(norm)
            if bool(v.get("available")) and norm not in seen_stock:
                seen_stock.add(norm)
                in_stock.append(norm)
    return all_sizes, in_stock
```

- [ ] **Step 4: Thêm 2 field vào `NormalizedItem`**

Sửa `NormalizedItem` (`:119`), thêm 2 dòng cuối dataclass sau `in_stock: bool`:

```python
    in_stock: bool
    available_sizes: list[str]  # all size options seen across variants (upper-cased)
    sizes_in_stock: list[str]   # subset of available_sizes with available == True
```

- [ ] **Step 5: Set 2 field trong `normalize_products`**

Trong `normalize_products`, ngay trước khi `items.append(...)` (trước dòng `:206`), thêm:

```python
        available_sizes, sizes_in_stock = _infer_sizes(raw.variants)
```

Và trong constructor `NormalizedItem(...)`, thêm 2 kwargs sau `in_stock=raw.any_in_stock,`:

```python
                in_stock=raw.any_in_stock,
                available_sizes=available_sizes,
                sizes_in_stock=sizes_in_stock,
```

- [ ] **Step 6: Ghi 2 cột vào link parquet**

Cập nhật `LINK_COLUMNS` (`:38`), thêm 2 phần tử cuối tuple:

```python
    "sku",
    "in_stock",
    "available_sizes",
    "sizes_in_stock",
)
```

Trong `write_frames`, thêm 2 key cuối mỗi dict của `link_rows` (sau `"in_stock": bool(it.in_stock),`):

```python
            "in_stock": bool(it.in_stock),
            "available_sizes": json.dumps(it.available_sizes, ensure_ascii=False),
            "sizes_in_stock": json.dumps(it.sizes_in_stock, ensure_ascii=False),
```

- [ ] **Step 7: Chạy test xác nhận PASS (kể cả test cũ)**

Run: `uv run pytest tests/data/scrape/test_normalize.py -v`
Expected: PASS toàn bộ (test cũ `test_happy_path` vẫn xanh vì colors không đổi).

- [ ] **Step 8: Commit**

```bash
git add scripts/data/scrape/normalize.py tests/data/scrape/test_normalize.py
git commit -m "feat(scrape): capture available_sizes + sizes_in_stock from variants"
```

---

### Task 2: Nạp size vào `ItemRecord.store`

**Files:**
- Modify: `src/outfitmatch/kb/catalog.py` (`load_catalog_items` store dict `:73-84`)
- Test: `tests/kb/test_kb_catalog.py`

- [ ] **Step 1: Viết test thất bại**

Sửa `_write_catalog` trong `tests/kb/test_kb_catalog.py` — thêm 2 cột vào MỖI dict của link DataFrame (`:49-78`). Ví dụ cho `item_1`:

```python
            {
                "item_id": "item_1",
                "store_id": "yody_vn",
                "source_product_id": "p1",
                "product_url": "https://yody.vn/p1",
                "price_vnd": 100000,
                "sale_price_vnd": None,
                "sku": "SKU1",
                "in_stock": True,
                "available_sizes": '["S", "M", "L"]',
                "sizes_in_stock": '["M", "L"]',
            },
```

(Thêm `"available_sizes"`/`"sizes_in_stock"` tương tự cho `item_2`, `item_3` — giá trị bất kỳ, ví dụ `'["29", "30"]'`/`'[]'`.)

Thêm test mới:

```python
def test_load_catalog_items_includes_sizes(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    assert items[0].store["available_sizes"] == ["S", "M", "L"]
    assert items[0].store["sizes_in_stock"] == ["M", "L"]
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/kb/test_kb_catalog.py::test_load_catalog_items_includes_sizes -v`
Expected: FAIL — `KeyError: 'available_sizes'`

- [ ] **Step 3: Nạp size vào store dict**

Trong `load_catalog_items`, thêm 2 key cuối dict `store=` (sau `"colors": _parse_colors(row.get("colors")),`). Tái dùng `_parse_colors` (nó là parser JSON-list-of-strings tổng quát):

```python
                    "colors": _parse_colors(row.get("colors")),
                    "available_sizes": _parse_colors(row.get("available_sizes")),
                    "sizes_in_stock": _parse_colors(row.get("sizes_in_stock")),
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_kb_catalog.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/kb/catalog.py tests/kb/test_kb_catalog.py
git commit -m "feat(kb): load available_sizes/sizes_in_stock into ItemRecord.store"
```

---

### Task 3: Resolver body→size (`quiz/sizing.py`)

**Files:**
- Create: `src/outfitmatch/quiz/sizing.py`
- Test: `tests/quiz/test_sizing.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/quiz/test_sizing.py`:

```python
from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord
from outfitmatch.quiz.sizing import suggest_size, suggest_sizes_for_outfit


def test_suggest_size_women_medium():
    assert suggest_size("top", "women", 160, 55, ["S", "M", "L"]) == "M"


def test_suggest_size_men_large():
    assert suggest_size("top", "men", 175, 72, ["S", "M", "L", "XL"]) == "L"


def test_suggest_size_falls_back_to_nearest_available():
    # base = M but only S/L stocked → nearest, prefer smaller on tie → S
    assert suggest_size("top", "women", 160, 55, ["S", "L"]) == "S"


def test_suggest_size_none_for_non_alpha_category():
    assert suggest_size("bottom", "men", 175, 70, ["29", "30", "31"]) is None
    assert suggest_size("shoes", "women", 160, 55, ["38", "39"]) is None


def test_suggest_size_none_when_no_body_info():
    assert suggest_size("top", "women", None, None, ["S", "M"]) is None


def test_suggest_size_none_when_no_available_sizes():
    assert suggest_size("dress", "women", 160, 55, []) is None


def _item(item_id: str, category: str, gender: str, store: dict) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path="",
        item_embedding=[],
        gender=gender,
        store=store,
    )


def test_suggest_sizes_for_outfit_skips_unresolved():
    top = _item("i1", "top", "women", {"sizes_in_stock": ["M", "L"]})
    shoe = _item("i2", "shoes", "women", {"available_sizes": ["38", "39"]})
    result = suggest_sizes_for_outfit([top, shoe], 160, 55)
    assert result == {"i1": "M"}  # shoe is non-alpha → skipped
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/quiz/test_sizing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outfitmatch.quiz.sizing'`

- [ ] **Step 3: Viết module**

Tạo `src/outfitmatch/quiz/sizing.py`:

```python
"""Body→size suggestion (v3.1-lite Tầng 4).

Maps quiz height/weight to a recommended alpha clothing size, then intersects
with the item's actually-available sizes. Deterministic and rule-based — same
spirit as rerank.py. Numeric/footwear sizing is out of scope for the MVP; only
alpha-sized garment categories get a body-derived suggestion.

The band tables are STARTER values loosely calibrated to VN chain-store charts
(YODY / Canifa); tune in Sprint 8 against real per-store size charts.
"""

from __future__ import annotations

from outfitmatch.kb.schema import ItemRecord

# Categories that use alpha sizing (S/M/L...). Bottoms (waist numbers) and shoes
# (EU numbers) are NOT mapped from body in the MVP.
ALPHA_SIZE_CATEGORIES: frozenset[str] = frozenset({"top", "dress", "outerwear"})

# Ordered alpha-size ladder. Index distance == size distance.
_SIZE_LADDER: tuple[str, ...] = ("XS", "S", "M", "L", "XL", "XXL")

# (weight_kg upper-bound inclusive, ladder index). First matching band wins;
# above the last bound → last ladder index (XXL).
_WOMEN_WEIGHT_BANDS: tuple[tuple[int, int], ...] = (
    (43, 0),  # <=43 → XS
    (50, 1),  # <=50 → S
    (58, 2),  # <=58 → M
    (67, 3),  # <=67 → L
    (76, 4),  # <=76 → XL
)
_MEN_WEIGHT_BANDS: tuple[tuple[int, int], ...] = (
    (55, 1),  # <=55 → S
    (65, 2),  # <=65 → M
    (75, 3),  # <=75 → L
    (85, 4),  # <=85 → XL
)


def _base_index(gender: str, weight_kg: int) -> int:
    bands = _MEN_WEIGHT_BANDS if gender == "men" else _WOMEN_WEIGHT_BANDS
    for upper, idx in bands:
        if weight_kg <= upper:
            return idx
    return len(_SIZE_LADDER) - 1


def _height_nudge(gender: str, height_cm: int) -> int:
    tall, short = (183, 160) if gender == "men" else (175, 150)
    if height_cm >= tall:
        return 1
    if height_cm <= short:
        return -1
    return 0


def suggest_size(
    category: str,
    gender: str,
    height_cm: int | None,
    weight_kg: int | None,
    available_sizes: list[str],
) -> str | None:
    """Return the best available alpha size for an item, or None.

    None means: not an alpha-sized category, missing body info, or no overlap
    between the recommended size (+ nearest neighbours) and ``available_sizes``.
    Callers should then fall back to showing ``available_sizes`` verbatim.
    On a tie distance the SMALLER size is preferred.
    """
    if category not in ALPHA_SIZE_CATEGORIES:
        return None
    if height_cm is None or weight_kg is None:
        return None
    avail = {s.upper() for s in available_sizes}
    if not avail:
        return None

    idx = _base_index(gender, weight_kg) + _height_nudge(gender, height_cm)
    idx = max(0, min(idx, len(_SIZE_LADDER) - 1))

    for dist in range(len(_SIZE_LADDER)):
        for cand in (idx - dist, idx + dist):  # smaller side first → tie favours smaller
            if 0 <= cand < len(_SIZE_LADDER) and _SIZE_LADDER[cand] in avail:
                return _SIZE_LADDER[cand]
    return None


def suggest_sizes_for_outfit(
    items: list[ItemRecord],
    height_cm: int | None,
    weight_kg: int | None,
) -> dict[str, str]:
    """item_id → suggested size, only for items where a size could be resolved.

    Prefers in-stock sizes; falls back to all available sizes when stock is
    unknown. Items with no resolvable size are omitted (caller shows the raw
    available_sizes for those).
    """
    out: dict[str, str] = {}
    for item in items:
        avail = [
            str(s)
            for s in (item.store.get("sizes_in_stock") or item.store.get("available_sizes") or [])
        ]
        size = suggest_size(item.category, item.gender, height_cm, weight_kg, avail)
        if size is not None:
            out[item.item_id] = size
    return out
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/quiz/test_sizing.py -v`
Expected: PASS toàn bộ.

> Kiểm tra logic `test_suggest_size_men_large`: nam 72kg → band `<=75 → L(3)`; cao 175 (< tall 183, > short 160) → nudge 0 → idx 3 → "L". ✔

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/quiz/sizing.py tests/quiz/test_sizing.py
git commit -m "feat(quiz): rule-based body->size resolver (alpha categories)"
```

---

### Task 4: Guard chống Qwen bịa size

**Files:**
- Modify: `src/outfitmatch/stylist/validation.py`
- Test: `tests/test_stylist.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_stylist.py` (cập nhật import dòng `:3`):

```python
from outfitmatch.stylist.validation import (
    extract_outfit_ids,
    extract_size_mentions,
    validate_response,
    validate_sizes,
)
```

```python
def test_extract_size_mentions_finds_sizes():
    assert extract_size_mentions("Bạn nên chọn size M hoặc size L.") == ["M", "L"]
    assert extract_size_mentions("Mình gợi ý cỡ XL nhé.") == ["XL"]


def test_validate_sizes_all_valid():
    ok, invalid = validate_sizes("Gợi ý size M cho bạn.", {"S", "M", "L"})
    assert ok is True
    assert invalid == []


def test_validate_sizes_detects_hallucination():
    ok, invalid = validate_sizes("Bạn mặc size XXL nhé.", {"S", "M"})
    assert ok is False
    assert "XXL" in invalid


def test_validate_sizes_ignores_non_size_text():
    ok, invalid = validate_sizes("Mình nghĩ bộ này hợp với bạn.", {"S"})
    assert ok is True
    assert invalid == []
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_stylist.py::test_extract_size_mentions_finds_sizes -v`
Expected: FAIL — `ImportError: cannot import name 'extract_size_mentions'`

- [ ] **Step 3: Thêm guard vào `validation.py`**

Thêm cuối `src/outfitmatch/stylist/validation.py`:

```python
# Size only counts when explicitly written as "size X" / "cỡ X" — keeps false
# positives near zero (avoids matching stray letters in Vietnamese prose).
_SIZE_MENTION_RE = re.compile(r"\b(?:size|cỡ)\s+([A-Za-z]{1,3}|\d{1,3})\b", re.IGNORECASE)


def extract_size_mentions(text: str) -> list[str]:
    """Return size tokens written as 'size X' / 'cỡ X' (upper-cased), in order."""
    return [m.group(1).upper() for m in _SIZE_MENTION_RE.finditer(text)]


def validate_sizes(response: str, available_sizes: Collection[str]) -> tuple[bool, list[str]]:
    """Check every 'size X' mention exists in the item's available sizes.

    Same anti-hallucination guard as validate_response, applied to sizes: the
    model may PRESENT a size but must never invent one the store doesn't carry.

    Returns (is_valid, invalid_sizes).
    """
    allowed = {str(s).upper() for s in available_sizes}
    found = extract_size_mentions(response)
    invalid = [s for s in found if s not in allowed]
    return len(invalid) == 0, invalid
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_stylist.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/stylist/validation.py tests/test_stylist.py
git commit -m "feat(stylist): validate_sizes guard against hallucinated sizes"
```

---

### Task 5: Field `suggested_sizes` trên `RecommendResult`

**Files:**
- Modify: `src/outfitmatch/pipeline.py` (`RecommendResult:44`)
- Test: `tests/test_pipeline_v31.py`

Đây là điểm tích hợp cho Sprint 8: pipeline vẫn `raise NotImplementedError`, nhưng schema kết quả đã sẵn sàng mang map `item_id → size`. (`field` đã được import sẵn ở `pipeline.py:19`.)

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_pipeline_v31.py`:

```python
def test_recommend_result_has_suggested_sizes_default():
    result = RecommendResult(outfits=[], body_shape="rectangle", occasion="office")
    assert result.suggested_sizes == {}
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_pipeline_v31.py::test_recommend_result_has_suggested_sizes_default -v`
Expected: FAIL — `TypeError`/`AttributeError` (field chưa tồn tại)

- [ ] **Step 3: Thêm field**

Trong `RecommendResult`, thêm dòng cuối (sau `latency_ms: float = 0.0`):

```python
    latency_ms: float = 0.0
    suggested_sizes: dict[str, str] = field(default_factory=dict)  # item_id → recommended size
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_pipeline_v31.py -v`
Expected: PASS (kể cả `test_recommend_result_structure` cũ).

- [ ] **Step 5: Commit**

```bash
git add src/outfitmatch/pipeline.py tests/test_pipeline_v31.py
git commit -m "feat(pipeline): add suggested_sizes field to RecommendResult"
```

---

### Task 6: Backfill catalog + cập nhật docs

**Files:**
- Data: `data/custom/catalog/item_store_links.parquet` (regenerate)
- Modify: `docs/datasets/STORE_CATALOG_VN.md`, `Kien_truc_v3.1.md`

Không có test tự động — đây là bước vận hành + tài liệu.

- [ ] **Step 1: Chạy full test + lint trước khi backfill**

Run: `uv run pytest -q` và `make lint`
Expected: tất cả xanh.

- [ ] **Step 2: Backfill size từ raw cache (offline, không gọi mạng)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.run --offline --no-images
```
Expected: log `wrote N catalog rows / N link rows`; lệnh thoát code 0.

- [ ] **Step 3: Xác minh size đã có trong parquet**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -c "import pandas as pd; df=pd.read_parquet('data/custom/catalog/item_store_links.parquet'); print('available_sizes' in df.columns); print(df['available_sizes'].head().tolist())"
```
Expected: `True` và in ra vài list size không rỗng (vd `["S","M","L"]`).

- [ ] **Step 4: Cập nhật docs**

Trong `docs/datasets/STORE_CATALOG_VN.md` §4 (schema `item_store_links`), thêm 2 dòng mô tả cột:

```markdown
| `available_sizes` | JSON list[str] | Tất cả size store niêm yết (upper-cased), trích từ variant options. |
| `sizes_in_stock`  | JSON list[str] | Subset còn hàng (variant.available == True). |
```

Trong `Kien_truc_v3.1.md` §4 (Tầng 4), thêm đoạn:

```markdown
- **Size gợi ý (runtime).** `quiz/sizing.py` map (height, weight, gender) → alpha-size
  cho `top`/`dress`/`outerwear`, giao với `available_sizes` của item. Qwen3-VL chỉ trình
  bày size; `validate_sizes` chặn size không có thật. OutfitRecord giữ size-agnostic
  (OT chấm visual; outfit là template tái dùng cho nhiều người).
```

- [ ] **Step 5: Commit**

```bash
git add data/custom/catalog/item_store_links.parquet docs/datasets/STORE_CATALOG_VN.md Kien_truc_v3.1.md
git commit -m "data(kb): backfill item sizes; docs for size handling"
```

---

## Self-Review

**1. Spec coverage**
- Cứu size về item (catalog fact) → Task 1 (scrape) + Task 2 (load). ✔
- OutfitRecord giữ size-agnostic → KHÔNG có task đụng `kb/schema.py` `OutfitRecord` (cố ý). ✔
- Runtime body→size, category-aware, intersect available → Task 3. ✔
- Qwen trình bày + validate trong tập size thật → Task 4. ✔
- Điểm tích hợp pipeline → Task 5. ✔
- Backfill dữ liệu đã mất + docs → Task 6. ✔

**2. Placeholder scan** — không có "TBD/TODO/xử lý lỗi phù hợp"; mọi step code đều có code thật.

**3. Type consistency** — tên nhất quán xuyên suốt: field `available_sizes`/`sizes_in_stock`; hàm `suggest_size`, `suggest_sizes_for_outfit`, `extract_size_mentions`, `validate_sizes`; `_SIZE_LADDER`, `ALPHA_SIZE_CATEGORIES`. Constructor `NormalizedItem` và `ItemRecord.store` khớp tên cột parquet.

## Lưu ý khi thực thi
- **Không** thêm size vào `OutfitRecord` hay đưa vào OutfitTransformer — đó là phản-pattern (nổ tổ hợp KB + nhiễu điểm visual).
- Band weight/height trong `sizing.py` là giá trị khởi điểm; calibrate ở Sprint 8 theo size chart từng store.
- Bottoms/shoes có thể thêm map số eo/EU ở vòng sau — kiến trúc đã sẵn (`available_sizes` luôn có sẵn để hiển thị).
