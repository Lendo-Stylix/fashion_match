# Outfit Graph KB — Design Spec (Sub-project 1: Graph construction + storage)

**Status:** Approved design (brainstorming). Next: `writing-plans` → implementation.
**Date:** 2026-06-01
**Scope of this spec:** *chỉ* sub-project 1 — dựng graph từ catalog và lưu. Traversal retrieval (Tầng 3) và grading redefinition là 2 spec riêng (xem §9 Decomposition).

---

## 1. Goal

Chuyển Outfit Knowledge Base từ **outfit vật chất hoá** (`OutfitRecord` cố định: top+bottom+shoes, index lên Qdrant `outfits`) sang **graph item-compatibility**: node = item, edge = "phối được". Mục tiêu người dùng đặt ra:

1. **Extensible** — outfit ban đầu không bắt buộc có giày (data giày hiện chỉ 122 adult); khi thu thập thêm giày, chỉ thêm node + edge, **không build lại KB**.
2. **Diversity** — mọi item là node nên traversal chạm tới toàn catalog, thoát cảnh 1000 outfit chỉ dùng 189/4694 item (4%) của pipeline materialized.
3. **Coherence là bất biến của graph** — edge chỉ sinh khi đồng gender + coherent formality, nên cấu trúc tagging mới (`gender`, `formality`) được nhúng thẳng vào cạnh thay vì là filter rời lúc generate.

Sub-project 1 dừng ở: **build graph + lưu + interface cho traversal**. Không đụng retrieval/grading.

## 2. Bối cảnh (đã kiểm chứng trong code & data)

- Catalog hiện tại: 5618 item, quality gate `check_catalog()` = 0 error, 5618/5618 ảnh tồn tại. Tag mới đã có: `gender` (men 2549/women 1873/kid 696/unisex 500), `formality` (casual 3374/smart_casual 1701/athletic 398/formal 145).
- **Shoes là nút thắt:** 133 (122 adult: 84 men/25 women/13 unisex). Pipeline materialized ép mỗi outfit có shoes → diversity sụp (27 giày khác nhau cho 1000 outfit, 1 đôi vào 72 outfit).
- Đã có sẵn, **tái dùng**: `_combo_gender` (`generation.py:26`), `formality_span_ok` + `FORMALITY_RELEVANT_CATEGORIES` (`vocab.py`), `load_catalog_items`/`group_items_by_category` (`catalog.py`), `extract_item_embeddings`/`HeuristicOutfitScorer.encode_item` (`embedding.py`/`scoring.py`), Qdrant pattern (`qdrant_index.py`: UUID5 point id, payload KEYWORD index, `:memory:`/`path://` cho test).
- **OT-labse scorer thật chưa wire** (placeholder `HeuristicOutfitScorer`). Thiết kế phải để weight pluggable, cắm OT sau mà không dựng lại graph.

**Bất biến giữ nguyên ở sub-project này:** `OutfitRecord`, `generation.py`, `build_outfits.py`, `qdrant_index.py` (collection `outfits`) **không xoá, không sửa** — migration thuộc sub-project 3.

## 3. Architecture & module layout

Module mới trong `src/outfitmatch/kb/`:

| File | Trách nhiệm | Hành động |
|---|---|---|
| `kb/pair_scoring.py` | `pairwise_compatibility(a,b)` interface + `HeuristicPairScorer` default (pluggable → OT-labse) | **Create** |
| `kb/graph.py` | `COMPLEMENTARY_CATEGORIES`, `edge_allowed(a,b)`, `build_edges(items, scorer, k)`, dataclass `Edge` | **Create** |
| `kb/graph_store.py` | `write_edges`/`read_edges` (parquet), `load_graph` → `OutfitGraph`, `index_item_nodes` (Qdrant `items`) | **Create** |
| `scripts/data/kb/build_graph.py` | CLI: catalog → graph → parquet + Qdrant; `--incremental`/`--rebuild` | **Create** |
| `tests/kb/test_pair_scoring.py`, `tests/kb/test_graph.py`, `tests/kb/test_graph_store.py` | Test | **Create** |

Data mới: `data/custom/graph/item_edges.parquet`.

## 4. Node & Edge model (lõi)

### 4.1 Node
Node = `ItemRecord` sẵn có (đã mang `item_id/category/gender/formality/store/image_path/item_embedding`). **Không thêm schema.**

### 4.2 Edge — điều kiện tồn tại (3 hard-constraint, AND)
Cạnh vô hướng giữa `a`–`b` tồn tại khi **cả 3**:

1. **Co-wearable category** — `edge_allowed_categories(a.category, b.category)`:
   - Cùng category → **không** nối (mỗi slot 1 món).
   - `dress` loại trừ `top` và `bottom` (đầm thay cho top+bottom).
   - Còn lại nối được. Bảng `COMPLEMENTARY_CATEGORIES` (vô hướng):
     - `top`  ↔ {bottom, shoes, outerwear, bag, accessory}
     - `bottom` ↔ {top, shoes, outerwear, bag, accessory}
     - `dress` ↔ {shoes, outerwear, bag, accessory}
     - `shoes` ↔ {top, bottom, dress, outerwear, bag, accessory}
     - `outerwear` ↔ {top, bottom, dress, shoes, bag, accessory}
     - `bag` ↔ {top, bottom, dress, shoes, outerwear, accessory}
     - `accessory` ↔ {top, bottom, dress, shoes, outerwear, bag}
2. **Đồng gender** — `_combo_gender([a, b]) is not None` (unisex ghép mọi gender; men×women = không cạnh).
3. **Coherent formality** — `formality_span_ok([a.formality, b.formality])`. Nếu `a` hoặc `b` thuộc category **ngoài** `FORMALITY_RELEVANT_CATEGORIES` (bag/accessory) → bỏ qua ràng buộc formality cho cặp đó (style-neutral).

### 4.3 Edge — trọng số
`weight = pairwise_compatibility(a, b) ∈ [0,1]`, **pluggable**. Default `HeuristicPairScorer`:
- Đối xứng, deterministic.
- Tổ hợp tín hiệu rẻ: (a) gần giá (price proximity), (b) color harmony (giao/ lặp màu — chịu được colors rỗng: thiếu màu → điểm trung tính, không phạt), (c) formality closeness (cùng bậc > kề bậc). Trả [0,1].
- Interface để OT-labse pairwise thay sau:
  ```python
  class PairScorer(Protocol):
      def score_pair(self, a: ItemRecord, b: ItemRecord) -> float: ...
  ```

### 4.4 Sparsify
Mỗi node giữ **top-K neighbor mạnh nhất / partner-category** (mặc định `K=15`). Chặn nổ O(N²): edges ≤ N × (#partner-cat) × K. Cạnh lưu canonical 1 chiều (`src_id < dst_id`); load dựng adjacency 2 chiều. Vì sparsify theo từng phía, hợp 2 phía → một node có thể >K neighbor ở một partner-category (chấp nhận; vẫn bị chặn ~2K).

## 5. Storage

### 5.1 `data/custom/graph/item_edges.parquet` (canonical 1 chiều)
| cột | kiểu | nghĩa |
|---|---|---|
| `src_id` | str | `src_id < dst_id` (so sánh chuỗi) |
| `dst_id` | str | |
| `src_category` | str | tra cứu lúc traverse |
| `dst_category` | str | |
| `weight` | float | [0,1] |

### 5.2 Qdrant `items` collection (mirror `qdrant_index.py`)
- `vector = item_embedding`, `distance = COSINE`, point id = `uuid5(item_id)`, `item_id` giữ trong payload.
- Payload + KEYWORD index để filter seed node ở Tầng 3:
  `category, gender, formality, price_tier, has_vn_store, in_stock, store_id` (index); kèm `price_vnd, colors, image_path, product_url` (payload không index).
- Hàm `create_items_collection` / `index_item_nodes` đối xứng `create_outfits_collection`/`index_outfits` (tái dùng helper `_make_client`/`_batched`/`_stable_point_id` — cân nhắc tách helper dùng chung; nếu rủi ro thì copy nhỏ, ghi chú DRY).

## 6. Build pipeline & extensibility

### 6.1 `scripts/data/kb/build_graph.py` (full build)
1. `load_catalog_items(catalog, links, genders=...)` — adult-only mặc định, `--include-kid` để bật.
2. `extract_item_embeddings(missing, scorer)` — đảm bảo embedding cho weight.
3. `build_edges(items, scorer, k=15)` → list `Edge`.
4. `write_edges(edges, EDGES_PATH)` + `index_item_nodes(items, qdrant_url)`.
- Flags: `--k`, `--include-kid`, `--qdrant-url`, `--no-qdrant` (chỉ ghi parquet), `--incremental`, `--rebuild`.

### 6.2 Incremental (`--incremental`) — mục tiêu extensibility
- Đọc `item_edges.parquet` cũ + tập `item_id` đã có. `new = items` có id chưa xuất hiện.
- Chỉ tính cạnh **(new × all)** + **(new × new)**, **append** vào parquet; upsert node mới lên Qdrant. **Cạnh cũ bất biến.**
- Hệ quả chốt: top-K của **node cũ** không tái tính → item mới (vd giày nữ) chỉ chắc chắn xuất hiện ở "phía neighbor của chính nó". Lúc traverse vẫn đủ để ráp outfit (seed = top/bottom, hỏi `neighbors(seed, "shoes")` — giày mới có cạnh ngược về top/bottom vì cạnh vô hướng). Chấp nhận lệch nhẹ top-K; `--rebuild` để tính lại toàn bộ khi cần chuẩn.

### 6.3 Determinism
Sort item theo `item_id`; tie-break weight bằng `dst_id`; không dùng RNG ở build. Cùng input + cùng `k` + cùng scorer → cùng `item_edges.parquet` (bit-identical sau sort).

## 7. Error handling & edge cases
- Item thiếu embedding sau `extract_item_embeddings` → log warning, vẫn tạo node, weight dùng nhánh fallback (price/formality) — **không** loại node.
- `colors` rỗng (53% catalog: yody/canifa) → color-harmony trả điểm trung tính, không phạt; edge vẫn sinh.
- Category lạ / ngoài `ITEM_CATEGORY_SET` → `load_catalog_items` đã lọc; `edge_allowed_categories` trả False an toàn.
- Parquet cũ thiếu cột (schema cũ) → `read_edges` raise rõ ràng, gợi ý `--rebuild`.
- Qdrant không cài / offline → `--no-qdrant` cho phép build chỉ-parquet (test/CI không cần Qdrant; dùng `:memory:` như `qdrant_index` test).

## 8. Testing
`tests/kb/test_pair_scoring.py`:
- `score_pair` ∈ [0,1], đối xứng (`score(a,b)==score(b,a)`), deterministic; colors rỗng → không lỗi, điểm hợp lệ.

`tests/kb/test_graph.py`:
- Khác gender → 0 cạnh; unisex ghép được.
- Lệch formality (athletic×formal) → 0 cạnh; kề bậc (casual×smart_casual) → có cạnh.
- Same-category (top×top) = 0; loại trừ (top×dress) = 0; hợp lệ (top×bottom, *×shoes) > 0.
- Sparsify: ≤ K neighbor/partner-category/node ở phía canonical.
- Determinism: 2 lần build cùng input → cùng tập cạnh.

`tests/kb/test_graph_store.py`:
- Round-trip parquet; `load_graph` dựng adjacency 2 chiều; `neighbors()` sort weight desc; `edge_weight()` None khi không cạnh.
- Incremental: thêm node không đổi cạnh cũ; `--rebuild` == full build.
- `index_item_nodes` lên Qdrant `:memory:` → đếm point đúng, payload filter `gender`/`formality` chạy.

## 9. Interface contract cho Tầng 3 (sub-project 2 — chốt sẵn)
```python
# kb/graph_store.py
def load_graph(edges_path: Path, *, items: list[ItemRecord]) -> OutfitGraph: ...

class OutfitGraph:
    def neighbors(self, item_id: str, partner_category: str) -> list[tuple[str, float]]:
        """(neighbor_id, weight) đã sort weight desc — cho beam-expand."""
    def edge_weight(self, a_id: str, b_id: str) -> float | None:
        """None nếu không có cạnh — để kiểm clique khi ráp outfit."""
    def item(self, item_id: str) -> ItemRecord: ...
```
Traversal (sub-proj 2): filter seed node trên Qdrant `items` → từ seed `neighbors()` ráp `top+bottom` (bắt buộc) rồi optional `shoes/outerwear/bag/accessory`, kiểm **clique** bằng `edge_weight` (mọi cặp phải có cạnh) → rank theo tổng/trung bình weight → top 5. Shoeless khi `neighbors(.., "shoes")` rỗng; tự "đính" giày khi data giày tăng (incremental build).

## 10. Decomposition (3 sub-project)
1. **Graph construction + storage** ← *spec này*.
2. **Traversal retrieval (Tầng 3 mới)** — assemble outfit động từ graph; thay filter-sort trên `outfits` collection.
3. **Grading redefinition** — định nghĩa lại Recall@5 / Compat trên outfit ráp động + eval harness; gỡ materialized `OutfitRecord`/`outfits` collection.

## 11. Out of scope (sub-project này)
- Traversal/assembly algorithm & ranking (sub-proj 2).
- Định nghĩa lại grading + gỡ `outfits` collection (sub-proj 3).
- OT-labse pairwise scorer thật (cắm sau qua `PairScorer`).
- Trục `season` cho edge (tái dùng khung `edge_allowed` khi cần).
- Cứu colors/sizes cho yody/canifa (việc scraper riêng; graph chịu được colors rỗng).

## 12. Success criteria
- `build_graph.py` chạy trên catalog 5618 item → `item_edges.parquet` + Qdrant `items` collection, deterministic.
- 0 cạnh vi phạm gender/formality/category (test khoá).
- Edges thưa (≤ ~2K/node), build < ~vài phút trên catalog hiện tại.
- `--incremental` thêm node không đổi cạnh cũ; outfit shoeless có thể "đính" giày sau khi thêm giày.
- Interface §9 đủ để sub-project 2 viết traversal mà không sửa lại graph.
