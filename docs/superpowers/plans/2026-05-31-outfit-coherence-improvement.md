# Outfit Coherence Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ngăn outfit "lạc quẻ" trong cùng một gender (vd: *blazer + quần short thể thao + giày tây*) bằng cách gán mỗi item một mức **formality** rồi ép outfit chỉ ghép các item nằm trong cùng một dải formality.

**Architecture:** Thêm một trục thuộc tính item mới — `formality` (ordinal: `athletic < casual < smart_casual < formal`) — đi đúng theo pattern `gender` đã có (`gender_map.py` → `NormalizedItem.gender` → cột parquet → `ItemRecord.gender` → `_combo_gender` trong generation). Generation thêm một hard-filter `_is_coherent` chạy song song `_combo_gender`: combo chỉ được dựng khi vừa đồng gender vừa coherent về formality. QA gate trong `evaluation.py` đếm số outfit lệch formality để bắt regression.

**Tech Stack:** Python 3.13, `uv`, pandas (parquet), pytest, dataclasses. Không thêm dependency mới.

---

## Bối cảnh & phạm vi

Đã kiểm chứng bằng probe trên KB hiện tại (`generated_outfits.parquet`, 1000 outfits): **0 outfit trộn men+women, 0 outfit chứa item kid** — commit `66072ca` (gender-aware) đã chặn đúng. Vấn đề "thiếu logic" còn lại nằm ở chỗ khác:

- `HeuristicOutfitScorer` (`src/outfitmatch/kb/scoring.py:22`) chỉ là **placeholder** (thưởng đúng slot category + giá + lặp màu + có URL); nó **không hiểu** độ trang trọng/phong cách.
- Ràng buộc generation (`generation.py:89` `_base_combinations`) chỉ ép: cấu trúc category + đồng gender. **Không** có nhất quán formality → tổ hợp hợp-lệ-category nhưng lạc-quẻ vẫn lọt.

**Plan này tập trung trục `formality`** — đòn bẩy ROI cao nhất, deterministic, làm được ngay sau khi scrape xong.

**Out of scope (xem cuối file — plan riêng):** (1) wire OutfitTransformer-labse thật vào `rescore_outfits`; (2) trục `season` (coat + shorts) — dùng lại y hệt khung `_is_coherent`; (3) repair kid bị tag `unisex` qua tín hiệu size (thuộc plan size `2026-05-31-item-size-handling.md`).

> ⚠️ **Thứ tự với việc scrape:** Bạn đang scrape data mới. Cần hoàn tất **Task 1–4 trước** khi chạy lượt `normalize` cuối, để `catalog_metadata.parquet` có sẵn cột `formality`. Nếu scrape xong trước, chạy lại normalize offline (Task 7) để backfill.

---

## File Structure

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/vocab.py` | Enum `FORMALITY` + ladder + helper `formality_span_ok` (single source of truth) | Modify |
| `scripts/data/scrape/formality_map.py` | `infer_formality()` rule-based, mirror `gender_map.py` | **Create** |
| `scripts/data/scrape/normalize.py` | Gán `formality` cho mỗi item, ghi cột catalog | Modify |
| `src/outfitmatch/kb/schema.py` | Field `ItemRecord.formality` | Modify |
| `src/outfitmatch/kb/catalog.py` | Nạp `formality` vào `ItemRecord` | Modify |
| `src/outfitmatch/kb/generation.py` | `_is_coherent` + `_is_valid_combo`, hard-filter combos | Modify |
| `src/outfitmatch/kb/evaluation.py` | `formality_clash_count` trong `OutfitBuildReport` | Modify |
| `scripts/data/kb/generate_outfits.py` | Truyền `item_formality` vào report | Modify |
| `tests/test_vocab.py`, `tests/data/scrape/test_formality_map.py`, `tests/data/scrape/test_normalize.py`, `tests/kb/test_kb_catalog.py`, `tests/kb/test_kb_generation.py`, `tests/kb/test_kb_evaluation.py` | Test | Modify/Create |
| `Kien_truc_v3.1.md`, `docs/datasets/STORE_CATALOG_VN.md` | Tài liệu | Modify |

**Bất biến giữ nguyên:** `OutfitRecord` schema và `OutfitTransformer` không đụng tới. `formality` là thuộc tính item dùng lúc build, không index lên Qdrant.

---

### Task 1: Enum `FORMALITY` + helper trong vocab

**Files:**
- Modify: `src/outfitmatch/vocab.py` (tuple sau `SKIN_TONE:82`, set sau `SKIN_TONE_SET:92`, labels sau `SKIN_TONE_LABELS_VI:150`, helper ở cuối file sau `validate_enum_values`)
- Test: `tests/test_vocab.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào import block đầu `tests/test_vocab.py` (trong `from outfitmatch.vocab import (...)`):

```python
    FORMALITY,
    FORMALITY_LABELS_VI,
    FORMALITY_SET,
    formality_span_ok,
```

Thêm test:

```python
def test_formality_enum_labels_and_sets():
    assert frozenset(FORMALITY) == FORMALITY_SET
    for v in FORMALITY:
        assert v == v.lower() and " " not in v, f"Bad enum value: {v!r}"
        assert v in FORMALITY_LABELS_VI, f"Missing VI label: {v!r}"


def test_formality_span_ok():
    assert formality_span_ok(["casual", "smart_casual"]) is True   # adjacent → ok
    assert formality_span_ok(["athletic", "formal"]) is False       # 3 apart
    assert formality_span_ok(["casual", "formal"]) is False         # 2 apart
    assert formality_span_ok([]) is True                            # empty → ok
    assert formality_span_ok(["casual", "bogus"]) is True           # unknown ignored
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_vocab.py::test_formality_span_ok -v`
Expected: FAIL — `ImportError: cannot import name 'FORMALITY'`

- [ ] **Step 3: Thêm tuple `FORMALITY`**

Ngay sau khối `SKIN_TONE` (sau dòng `:82` trong `vocab.py`):

```python
FORMALITY: tuple[str, ...] = (
    "athletic",
    "casual",
    "smart_casual",
    "formal",
)
```

- [ ] **Step 4: Thêm `FORMALITY_SET`**

Sau `SKIN_TONE_SET` (sau `:92`):

```python
FORMALITY_SET: frozenset[str] = frozenset(FORMALITY)
```

- [ ] **Step 5: Thêm labels VI**

Sau `SKIN_TONE_LABELS_VI` (sau `:150`):

```python
FORMALITY_LABELS_VI: dict[str, str] = {
    "athletic": "thể thao",
    "casual": "thường ngày",
    "smart_casual": "lịch sự nhẹ",
    "formal": "trang trọng",
}
```

- [ ] **Step 6: Thêm ladder + helper ở cuối file**

Sau hàm `validate_enum_values` (cuối `vocab.py`):

```python
# Formality ladder for outfit-coherence filtering. Items in one outfit must stay
# within FORMALITY_TOLERANCE steps on this ordinal ladder
# (athletic < casual < smart_casual < formal); otherwise the combo is incoherent
# (e.g. blazer + gym shorts). Only FORMALITY_RELEVANT_CATEGORIES participate;
# bags/accessories are style-neutral and ignored.
FORMALITY_RANK: dict[str, int] = {name: i for i, name in enumerate(FORMALITY)}
FORMALITY_RELEVANT_CATEGORIES: frozenset[str] = frozenset(
    {"top", "bottom", "dress", "shoes", "outerwear"}
)
FORMALITY_TOLERANCE: int = 1


def formality_span_ok(formalities: list[str], tolerance: int = FORMALITY_TOLERANCE) -> bool:
    """True if all formalities sit within ``tolerance`` steps on the ladder.

    Unknown values are ignored; an empty / all-unknown list is considered OK.
    """
    ranks = [FORMALITY_RANK[f] for f in formalities if f in FORMALITY_RANK]
    if not ranks:
        return True
    return max(ranks) - min(ranks) <= tolerance
```

- [ ] **Step 7: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_vocab.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 8: Commit**

```bash
git add src/outfitmatch/vocab.py tests/test_vocab.py
git commit -m "feat(vocab): add FORMALITY enum + formality_span_ok coherence helper"
```

---

### Task 2: Tagger `infer_formality`

**Files:**
- Create: `scripts/data/scrape/formality_map.py`
- Test: `tests/data/scrape/test_formality_map.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/data/scrape/test_formality_map.py`:

```python
from outfitmatch.vocab import FORMALITY_SET
from scripts.data.scrape.formality_map import infer_formality


def test_athletic():
    assert infer_formality("Quần Thể Thao Nam") == "athletic"
    assert infer_formality("Giày Sneaker Running") == "athletic"
    assert infer_formality("Áo Bra Tập Luyện") == "athletic"


def test_formal():
    assert infer_formality("Áo Vest Nam Công Sở") == "formal"
    assert infer_formality("Đầm Dạ Hội Sang Trọng") == "formal"
    assert infer_formality("Giày Tây Da Bò") == "formal"


def test_smart_casual():
    assert infer_formality("Áo Polo Nam") == "smart_casual"
    assert infer_formality("Áo Sơ Mi Trắng Basic") == "smart_casual"
    assert infer_formality("Giày Cao Gót 5cm") == "smart_casual"


def test_casual_default():
    assert infer_formality("Áo Thun Cotton Basic") == "casual"
    assert infer_formality("Quần Jeans Rách Gối") == "casual"
    assert infer_formality("Hoodie Nỉ Bông") == "casual"


def test_athletic_beats_formal_when_both_present():
    # priority guarantee: a sporty item wins over a formal-sounding token
    assert infer_formality("Áo Thể Thao In Blazer Print") == "athletic"


def test_always_valid_enum():
    for t in ["Áo Vest", "Quần Thể Thao", "Sơ Mi", "Random Thing"]:
        assert infer_formality(t) in FORMALITY_SET
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_formality_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.data.scrape.formality_map'`

- [ ] **Step 3: Viết module**

Tạo `scripts/data/scrape/formality_map.py`:

```python
"""Infer dress formality for a catalog item.

Why this exists:
    Outfit generation combines items by category + gender only. Without a
    formality signal it pairs a blazer with gym shorts. This assigns each item a
    coarse formality so generation can keep one outfit inside a sensible band.

Returns one of FORMALITY: ``athletic | casual | smart_casual | formal``.
``casual`` is the safe fallback. Keyword rules, same spirit as gender_map.py —
tune the marker lists as the catalog grows. Tested standalone — see
tests/data/scrape/test_formality_map.py.
"""

from __future__ import annotations

from outfitmatch.vocab import FORMALITY_SET

# Strong activewear signals (checked first — a sporty item is athletic even if a
# formal-sounding token also appears).
ATHLETIC_MARKERS: tuple[str, ...] = (
    "thể thao",
    "sport",
    "gym",
    "jogger",
    "training",
    "running",
    "legging",
    "tập luyện",
    "active",
    "yoga",
    "sneaker",
    "giày chạy",
)
# Strong formal / occasion-wear signals.
FORMAL_MARKERS: tuple[str, ...] = (
    "vest",
    "veston",
    "blazer",
    "suit",
    "tuxedo",
    "áo dài",
    "dạ hội",
    "dự tiệc",
    "công sở",
    "lễ phục",
    "giày tây",
)
# Smart-casual: between casual and formal.
SMART_CASUAL_MARKERS: tuple[str, ...] = (
    "polo",
    "sơ mi",
    "chinos",
    "chino",
    "cardigan",
    "blouse",
    "quần tây",
    "quần âu",
    "cao gót",
    "loafer",
)


def infer_formality(
    title: str,
    product_type: str = "",
    category: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Best-effort dress formality → one of FORMALITY. Default ``casual``."""
    text = f"{title} {product_type} {' '.join(tags or [])}".lower()
    if any(m in text for m in ATHLETIC_MARKERS):
        return "athletic"
    if any(m in text for m in FORMAL_MARKERS):
        return "formal"
    if any(m in text for m in SMART_CASUAL_MARKERS):
        return "smart_casual"
    result = "casual"
    assert result in FORMALITY_SET
    return result
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/data/scrape/test_formality_map.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/scrape/formality_map.py tests/data/scrape/test_formality_map.py
git commit -m "feat(scrape): rule-based infer_formality tagger"
```

---

### Task 3: Gán `formality` trong normalize

**Files:**
- Modify: `scripts/data/scrape/normalize.py` (import; `NormalizedItem:119`; constructor `:206`; `write_frames` cat_rows `:240`)
- Test: `tests/data/scrape/test_normalize.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/data/scrape/test_normalize.py`:

```python
def test_infers_formality():
    items = normalize_products([_raw()], _store(), start_index=1, existing_link_map={})
    assert items[0].formality == "casual"  # "Áo thun cotton basic" → casual


def test_formality_written_to_catalog(tmp_path, monkeypatch):
    import pandas as pd

    monkeypatch.setattr(normalize, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "CATALOG_PARQUET", tmp_path / "catalog_metadata.parquet")
    monkeypatch.setattr(normalize, "LINKS_PARQUET", tmp_path / "item_store_links.parquet")

    write_frames(normalize_products([_raw()], _store(), existing_link_map={}))
    cat = pd.read_parquet(tmp_path / "catalog_metadata.parquet")
    assert "formality" in cat.columns
    assert cat.loc[0, "formality"] == "casual"
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/data/scrape/test_normalize.py::test_infers_formality -v`
Expected: FAIL — `AttributeError: 'NormalizedItem' object has no attribute 'formality'`

- [ ] **Step 3: Import tagger**

Thêm cạnh các import `.` khác (sau dòng `:32` `from .gender_map import infer_gender`):

```python
from .formality_map import infer_formality
```

- [ ] **Step 4: Thêm field vào `NormalizedItem`**

Trong `NormalizedItem` (`:119`), thêm `formality` ngay sau `gender`:

```python
    gender: str  # GENDER enum value (men|women|unisex|kid)
    formality: str  # FORMALITY enum value (athletic|casual|smart_casual|formal)
```

- [ ] **Step 5: Set `formality` trong `normalize_products`**

Trong constructor `NormalizedItem(...)` (`:206`), thêm ngay sau dòng `gender=...`:

```python
                gender=infer_gender(raw.title, raw.product_type, store.store_id, category),
                formality=infer_formality(raw.title, raw.product_type, category, raw.tags),
```

- [ ] **Step 6: Ghi cột vào catalog parquet**

Trong `write_frames`, mỗi dict của `cat_rows` (`:240`), thêm `"formality"` ngay sau `"gender"`:

```python
            "gender": it.gender,
            "formality": it.formality,
```

- [ ] **Step 7: Chạy test xác nhận PASS (kể cả test cũ)**

Run: `uv run pytest tests/data/scrape/test_normalize.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 8: Commit**

```bash
git add scripts/data/scrape/normalize.py tests/data/scrape/test_normalize.py
git commit -m "feat(scrape): tag item formality into catalog_metadata"
```

---

### Task 4: Nạp `formality` vào `ItemRecord`

**Files:**
- Modify: `src/outfitmatch/kb/schema.py` (`ItemRecord:9`)
- Modify: `src/outfitmatch/kb/catalog.py` (import `:14`; `load_catalog_items` `:55-86`)
- Test: `tests/kb/test_kb_catalog.py`

- [ ] **Step 1: Viết test thất bại**

Trong `tests/kb/test_kb_catalog.py`, thêm cột `formality` vào catalog DataFrame của `_write_catalog` (`:13-46`) — `item_1` = `"formal"`, `item_2`/`item_3` = `"casual"`:

```python
            {
                "item_id": "item_1",
                "category": "top",
                "image_path": "data/custom/catalog/images/item_1.jpg",
                "title_vi": "Áo trắng",
                "desc_vi": "Cotton",
                "colors": '["Trắng"]',
                "collected_date": "2026-05-30",
                "collector": "unit",
                "formality": "formal",
            },
```

(Thêm `"formality": "casual"` cho `item_2` và `item_3` tương tự.)

Thêm test:

```python
def test_load_catalog_items_reads_formality(tmp_path):
    catalog_path, links_path = _write_catalog(tmp_path)
    items = load_catalog_items(catalog_path, links_path)
    assert items[0].formality == "formal"
    assert items[1].formality == "casual"
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/kb/test_kb_catalog.py::test_load_catalog_items_reads_formality -v`
Expected: FAIL — `AttributeError: 'ItemRecord' object has no attribute 'formality'`

- [ ] **Step 3: Thêm field vào `ItemRecord`**

Trong `src/outfitmatch/kb/schema.py`, thêm sau `gender` (`:17`):

```python
    gender: str = "unisex"  # GENDER enum value (men|women|unisex|kid)
    formality: str = "casual"  # FORMALITY enum value — used by outfit-coherence filter
```

- [ ] **Step 4: Nạp `formality` trong `load_catalog_items`**

Cập nhật import (`:14`):

```python
from outfitmatch.vocab import FORMALITY_SET, GENDER_SET, ITEM_CATEGORY_SET
```

Trong vòng lặp `load_catalog_items`, ngay sau khối xử lý `gender` (sau `:61`), thêm:

```python
        formality = str(row.get("formality") or "casual")
        if formality not in FORMALITY_SET:
            formality = "casual"
```

Và trong constructor `ItemRecord(...)`, thêm sau `gender=gender,` (`:72`):

```python
                gender=gender,
                formality=formality,
```

- [ ] **Step 5: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_kb_catalog.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add src/outfitmatch/kb/schema.py src/outfitmatch/kb/catalog.py tests/kb/test_kb_catalog.py
git commit -m "feat(kb): load item formality into ItemRecord"
```

---

### Task 5: Hard-filter coherence trong generation

**Files:**
- Modify: `src/outfitmatch/kb/generation.py` (import `:20`; helper sau `_combo_gender:36`; `_base_combinations:97,103`; `_with_optional_items:120`)
- Test: `tests/kb/test_kb_generation.py`

- [ ] **Step 1: Viết test thất bại**

Trong `tests/kb/test_kb_generation.py`, thêm `formality` param vào helper `_item` (`:7`):

```python
def _item(
    item_id: str,
    category: str,
    price: int,
    emb: list[float] | None = None,
    gender: str = "unisex",
    formality: str = "casual",
) -> ItemRecord:
    return ItemRecord(
        item_id=item_id,
        category=category,
        image_path=f"data/custom/catalog/images/{item_id}.jpg",
        item_embedding=emb or [1.0, 0.0],
        gender=gender,
        formality=formality,
        store={
            "store_id": "test_store",
            "store_name": "Test Store",
            "product_url": f"https://test.vn/{item_id}",
            "price_vnd": price,
            "in_stock": True,
        },
    )
```

Cập nhật import (`:3`) và thêm test:

```python
from outfitmatch.kb.generation import (
    _base_combinations,
    _is_coherent,
    generate_fitb_beam,
    generate_random_scored,
)
```

```python
def test_is_coherent_blocks_formality_clash():
    blazer = _item("blz", "top", 100_000, formality="formal")
    gym = _item("gym", "bottom", 100_000, formality="athletic")
    shoe = _item("sh", "shoes", 100_000, formality="formal")
    assert _is_coherent([blazer, gym, shoe]) is False


def test_is_coherent_allows_adjacent_bands():
    polo = _item("p", "top", 100_000, formality="smart_casual")
    chino = _item("c", "bottom", 100_000, formality="casual")
    loafer = _item("l", "shoes", 100_000, formality="smart_casual")
    assert _is_coherent([polo, chino, loafer]) is True


def test_is_coherent_ignores_accessory_formality():
    top = _item("t", "top", 100_000, formality="casual")
    bottom = _item("b", "bottom", 100_000, formality="casual")
    shoe = _item("s", "shoes", 100_000, formality="casual")
    formal_bag = _item("bag", "bag", 100_000, formality="formal")  # not relevant cat
    assert _is_coherent([top, bottom, shoe, formal_bag]) is True


def test_base_combinations_excludes_formality_clash():
    catalog = {
        "top": [_item("formal_top", "top", 100_000, formality="formal")],
        "bottom": [_item("athletic_bottom", "bottom", 100_000, formality="athletic")],
        "shoes": [_item("formal_shoe", "shoes", 100_000, formality="formal")],
    }
    assert _base_combinations(catalog) == []  # only clashing combo → nothing built
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/kb/test_kb_generation.py::test_is_coherent_blocks_formality_clash -v`
Expected: FAIL — `ImportError: cannot import name '_is_coherent'`

- [ ] **Step 3: Import helper vocab**

Trong `generation.py`, sau dòng `:20` `from outfitmatch.kb.schema import OutfitRecord`:

```python
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, formality_span_ok
```

- [ ] **Step 4: Thêm `_is_coherent` + `_is_valid_combo`**

Ngay sau `_combo_gender` (sau `:36`):

```python
def _is_coherent(items: list[ItemRecord]) -> bool:
    """True if the outfit's core garments stay within one formality band.

    Only FORMALITY_RELEVANT_CATEGORIES (top/bottom/dress/shoes/outerwear) count;
    bags/accessories are style-neutral and ignored. Blocks combos like
    blazer + gym shorts.
    """
    formalities = [
        item.formality for item in items if item.category in FORMALITY_RELEVANT_CATEGORIES
    ]
    return formality_span_ok(formalities)


def _is_valid_combo(items: list[ItemRecord]) -> bool:
    """A combo is buildable only if gender-consistent AND formality-coherent."""
    return _combo_gender(items) is not None and _is_coherent(items)
```

- [ ] **Step 5: Thay 3 call-site trong `_base_combinations` và `_with_optional_items`**

`_base_combinations` (`:97` và `:103`):

```python
        if _is_valid_combo([top, bottom, shoes]):
            combos.append([top, bottom, shoes])
```
```python
        if _is_valid_combo([dress, shoes]):
            combos.append([dress, shoes])
```

`_with_optional_items` (`:120`):

```python
            if _is_valid_combo([*items, choice]):
                items.append(choice)
```

- [ ] **Step 6: Chạy test xác nhận PASS (kể cả test gender cũ)**

Run: `uv run pytest tests/kb/test_kb_generation.py -v`
Expected: PASS toàn bộ. (Test gender cũ dùng `_item` mặc định `formality="casual"` → luôn coherent → không đổi hành vi.)

- [ ] **Step 7: Commit**

```bash
git add src/outfitmatch/kb/generation.py tests/kb/test_kb_generation.py
git commit -m "feat(kb): formality-coherence hard-filter in outfit generation"
```

---

### Task 6: QA gate — đếm formality clash

**Files:**
- Modify: `src/outfitmatch/kb/evaluation.py` (import `:11`; `OutfitBuildReport:15`; helper sau `_count_mixed_gender:64`; `evaluate_outfit_frame:67`; `summarize_outfit_report:110`)
- Modify: `scripts/data/kb/generate_outfits.py` (`:101-106`)
- Test: `tests/kb/test_kb_evaluation.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/kb/test_kb_evaluation.py`:

```python
def test_formality_clash_counted():
    import json

    import pandas as pd

    from outfitmatch.kb.evaluation import evaluate_outfit_frame

    frame = pd.DataFrame(
        [
            {
                "outfit_id": "OF_00001",
                "item_ids": json.dumps(["a", "b", "c"]),
                "categories": json.dumps(["top", "bottom", "shoes"]),
                "gender": "men",
                "gen_method": "random_scored",
                "price_tier": "mid",
                "compatibility_score": 0.5,
            }
        ]
    )
    clash = {"a": "formal", "b": "athletic", "c": "formal"}
    rep = evaluate_outfit_frame(frame, price_tier_targets={"mid": 1.0}, item_formality=clash)
    assert rep.formality_clash_count == 1

    ok = {"a": "casual", "b": "casual", "c": "casual"}
    rep2 = evaluate_outfit_frame(frame, price_tier_targets={"mid": 1.0}, item_formality=ok)
    assert rep2.formality_clash_count == 0
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/kb/test_kb_evaluation.py::test_formality_clash_counted -v`
Expected: FAIL — `TypeError: evaluate_outfit_frame() got an unexpected keyword argument 'item_formality'`

- [ ] **Step 3: Import vocab helper**

Cập nhật import trong `evaluation.py` (`:11`):

```python
from outfitmatch.vocab import FORMALITY_RELEVANT_CATEGORIES, PRICE_TIER, formality_span_ok
```

- [ ] **Step 4: Thêm field vào `OutfitBuildReport`**

Trong dataclass (`:15`), thêm sau `mixed_gender_count: int`:

```python
    mixed_gender_count: int
    formality_clash_count: int
```

- [ ] **Step 5: Thêm helper đếm clash**

Ngay sau `_count_mixed_gender` (sau `:64`):

```python
def _count_formality_clash(frame: pd.DataFrame, item_formality: dict[str, str]) -> int:
    """Outfits whose core garments span more than one formality band.

    Uses the parallel ``item_ids`` / ``categories`` JSON columns; only
    FORMALITY_RELEVANT_CATEGORIES participate. Unknown items default to ``casual``.
    """
    if "item_ids" not in frame or "categories" not in frame:
        return 0
    clashes = 0
    for raw_ids, raw_cats in zip(frame["item_ids"], frame["categories"]):
        ids = _loads_list(raw_ids)
        cats = _loads_list(raw_cats)
        formalities = [
            item_formality.get(iid, "casual")
            for iid, cat in zip(ids, cats)
            if cat in FORMALITY_RELEVANT_CATEGORIES
        ]
        if not formality_span_ok(formalities):
            clashes += 1
    return clashes
```

- [ ] **Step 6: Wire vào `evaluate_outfit_frame`**

Thêm param (sau `item_gender` trong signature `:71`):

```python
    item_gender: dict[str, str] | None = None,
    item_formality: dict[str, str] | None = None,
```

Trong `return OutfitBuildReport(...)`, thêm sau `mixed_gender_count=...` (`:100`):

```python
        mixed_gender_count=_count_mixed_gender(frame, item_gender or {}),
        formality_clash_count=_count_formality_clash(frame, item_formality or {}),
```

- [ ] **Step 7: Thêm dòng vào `summarize_outfit_report`**

Trong list của `summarize_outfit_report` (`:110`), thêm sau dòng `mixed_gender_outfits`:

```python
            f"mixed_gender_outfits: {report.mixed_gender_count}",
            f"formality_clash_outfits: {report.formality_clash_count}",
```

- [ ] **Step 8: Truyền `item_formality` từ `generate_outfits`**

Trong `scripts/data/kb/generate_outfits.py` (`:101`), thêm map và truyền vào:

```python
    item_gender = {item.item_id: item.gender for item in items}
    item_formality = {item.item_id: item.formality for item in items}
    outfit_report = evaluate_outfit_frame(
        pd.read_parquet(args.output),
        price_tier_targets=args.price_tier_targets,
        item_gender=item_gender,
        item_formality=item_formality,
    )
```

- [ ] **Step 9: Chạy test xác nhận PASS**

Run: `uv run pytest tests/kb/test_kb_evaluation.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 10: Commit**

```bash
git add src/outfitmatch/kb/evaluation.py scripts/data/kb/generate_outfits.py tests/kb/test_kb_evaluation.py
git commit -m "feat(kb): formality_clash_count QA metric in outfit build report"
```

---

### Task 7: Full check + regenerate + docs

Không có test tự động — bước vận hành + tài liệu.

- [ ] **Step 1: Full test + lint**

Run: `uv run pytest -q` và `make lint`
Expected: tất cả xanh.

- [ ] **Step 2: Backfill `formality` vào catalog (offline)**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.scrape.run --offline --no-images
```
Expected: log `wrote N catalog rows`; thoát code 0.

- [ ] **Step 3: Xác minh cột `formality` có và phân bố hợp lý**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -c "import pandas as pd; df=pd.read_parquet('data/custom/catalog/catalog_metadata.parquet'); print('formality' in df.columns); print(df['formality'].value_counts().to_dict())"
```
Expected: `True` và phân bố 4 mức (casual chiếm đa số, có athletic/smart_casual/formal).

- [ ] **Step 4: Regenerate KB và kiểm tra clash = 0**

Run:
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m scripts.data.kb.generate_outfits --n-outfits 1000 --limit-per-category 60
```
Expected: trong "outfit build report" log có dòng `formality_clash_outfits: 0` (hard-filter đảm bảo 0).

- [ ] **Step 5: Cập nhật docs**

`docs/datasets/STORE_CATALOG_VN.md` §4 (schema `catalog_metadata`), thêm dòng:

```markdown
| `formality` | str | Mức trang trọng: `athletic` / `casual` / `smart_casual` / `formal`. Suy ra từ title/product_type. Dùng cho coherence-filter lúc build outfit. |
```

`Kien_truc_v3.1.md` §3.4 (Tầng 1 generation), thêm đoạn:

```markdown
- **Coherence filter.** Ngoài đồng gender, generation ép mỗi outfit nằm trong cùng
  dải formality (athletic < casual < smart_casual < formal, tolerance 1 bậc) qua
  `_is_valid_combo`. Chặn tổ hợp lạc quẻ (vd: blazer + quần short thể thao). QA gate
  `formality_clash_outfits` trong build report bắt regression.
```

- [ ] **Step 6: Commit**

```bash
git add data/custom/catalog/catalog_metadata.parquet data/custom/outfits/generated_outfits.parquet docs/datasets/STORE_CATALOG_VN.md Kien_truc_v3.1.md
git commit -m "data(kb): regenerate KB with formality coherence; docs"
```

---

## Self-Review

**1. Spec coverage**
- Item formality attribute (foundation) → Task 1 (vocab), 2 (tagger), 3 (normalize), 4 (ItemRecord). ✔
- Hard-filter coherence trong generation → Task 5 (`_is_coherent`/`_is_valid_combo`, cả `_base_combinations` lẫn `_with_optional_items`). ✔
- QA gate chống regression → Task 6. ✔
- Backfill + verify + docs → Task 7. ✔
- `OutfitRecord`/OT không đụng → không có task chạm (cố ý). ✔

**2. Placeholder scan** — không có TBD/"xử lý phù hợp"; mọi code step có code thật + lệnh + expected.

**3. Type consistency** — `formality` (str) xuyên suốt NormalizedItem → cột parquet → ItemRecord; helper `formality_span_ok`, constant `FORMALITY_RELEVANT_CATEGORIES`/`FORMALITY_RANK`/`FORMALITY_TOLERANCE` ở vocab dùng chung bởi generation + evaluation (DRY); `_is_coherent`/`_is_valid_combo` nhất quán. Field `formality_clash_count` khớp giữa dataclass, evaluate, summarize, test.

## Out of scope — plan/việc riêng

1. **OT-labse scorer thật** thay `HeuristicOutfitScorer` (`scoring.py`). Đây là đòn bẩy coherence *thị giác* và là yêu cầu grading (FITB acc, Compat AUC). Lưu ý: OT **không** biết gender/dịp → formality-filter (plan này) + gender-filter vẫn phải là hard pre-filter, OT chỉ xếp hạng trong tập hợp lệ.
2. **Trục `season`** (áo phao + quần đùi): tái dùng y hệt khung — thêm `SEASON` mục đích coherence + `infer_season` + nhánh trong `_is_coherent`.
3. **Repair kid bị tag `unisex`** qua tín hiệu size (age/cm) — thuộc plan `2026-05-31-item-size-handling.md` (cần `available_sizes`).

## Lưu ý khi thực thi
- `FORMALITY_TOLERANCE = 1` cố ý nghiêng về *loại bỏ* combo biên (sneaker + sơ mi → loại). Nới lên 2 nếu thấy KB quá ít outfit.
- Tagger keyword sẽ sai một số ca; tolerance 1 + default `casual` khiến hệ thống chịu lỗi tốt. Calibrate marker list khi xem phân bố thật (Task 7 Step 3).
