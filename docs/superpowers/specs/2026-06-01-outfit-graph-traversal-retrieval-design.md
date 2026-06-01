# Outfit Graph Traversal Retrieval — Design Spec (Sub-project 2)

**Status:** Approved architecture (graph-IS-KB, traversal Tầng 3). Design decisions below need a quick user review — see §3 ⚠️.
**Date:** 2026-06-01
**Depends on:** sub-project 1 (`docs/superpowers/specs/2026-06-01-outfit-graph-kb-design.md`) — `OutfitGraph.neighbors/edge_weight/item`, Qdrant `items` collection.
**Next:** plan `docs/superpowers/plans/2026-06-01-outfit-graph-traversal-retrieval.md`.

---

## 1. Goal

Hiện thực Tầng 3 **lần đầu** (hiện `pipeline.recommend_outfit` raise `NotImplementedError`, `tools.py` chỉ là tool-schema): nhận query có filter → **filter seed node trên Qdrant `items`** → **traverse graph ráp outfit động** (top+bottom bắt buộc, shoes/outerwear/bag/accessory optional) → rank theo compatibility → trả top-N. Outfit ráp ra là `OutfitRecord` (tag dẫn xuất) nên **toàn bộ downstream giữ nguyên**: `rerank_by_preference` (Tầng 4), `RecommendResult`, validation, explanation.

Vì là graph-KB: outfit **không bắt buộc có giày** (shoeless khi seed không có neighbor shoes); thêm giày sau (`build_graph --incremental`) → traverse tự đính.

## 2. Bối cảnh (đã kiểm chứng)

- `pipeline.py`: `RecommendRequest(occasion, height_cm, weight_kg, style, body_shape, skin_tone, price_max, exclude_colors, quiz_answers, image_path)` → `RecommendResult(outfits: list[OutfitRecord], body_shape, occasion, explanation_vi, latency_ms, suggested_sizes)`. `recommend_outfit` chưa implement.
- `quiz/rerank.py`: `rerank_by_preference(outfits, pref, top_k=5)` chấm trên `outfit.compatibility_score/style/occasion/color_palette/price_tier` — **cần `OutfitRecord` có các field này**.
- `OutfitRecord` (schema.py): `occasion/style/body_shapes_fit/season/color_palette/price_tier/gender/compatibility_score/...`.
- Graph node (`items` collection) payload: `category/gender/formality/price_tier/has_vn_store/in_stock/store_id/colors`. **Không có** `occasion/style/body_shape` ở mức item.
- `StoreConfig.style_tags: tuple[str,...]` (subset STYLE) + `target_gender` — suy style cho item theo store.
- Enums: `OCCASION` (office/interview/school/date/cafe_hangout/party/wedding/home_casual/travel), `FORMALITY` (athletic<casual<smart_casual<formal), `STYLE`, `BODY_SHAPE`.

## 3. ⚠️ Quyết định thiết kế cần review (occasion / style / body)

Graph node thiếu tag semantic mức item. Cách dung hoà cho MVP (flag để bạn xác nhận):

| Trục query | Cách suy ở graph MVP | Rủi ro |
|---|---|---|
| **occasion** | Map `formality → tập occasion phù hợp` (bảng `FORMALITY_OCCASIONS` mới trong vocab). Outfit "hợp" occasion X nếu formality-band của nó admit X. Giữ ablation occasion-on/off có nghĩa. | Thô (formal→office/wedding/party...); 1 formality map nhiều occasion. |
| **style** | Item style = `STORES_BY_ID[store_id].style_tags`; outfit style = hợp các item. Filter theo giao với style yêu cầu. | Style theo store, không theo từng sản phẩm. |
| **body_shape** | **DEFER** ở MVP (node không có body-fit tag). `body_shape` filter là no-op + ghi log; outfit `body_shapes_fit=[]`. | Ablation body-conditioning (grading, sub-proj 3) **chưa đo được** → cần item-tagging follow-up. |
| **exclude_colors / price_max** | Filter trực tiếp trên item colors / price. | colors rỗng 53% → exclude yếu cho yody/canifa (đã biết). |

**Đề xuất:** MVP làm occasion (formality-map) + style (store) + price + exclude_colors; **body_shape defer** kèm follow-up "item semantic tagging" (Gemini tag occasion/style/body_shape per node) — đây cũng là tiền đề cho body-ablation ở sub-project 3. Nếu bạn muốn body-conditioning ngay, ta cần chèn follow-up tagging trước.

## 4. Architecture & module layout

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/vocab.py` | `FORMALITY_OCCASIONS` map + helper `occasions_for_formality` | Modify |
| `src/outfitmatch/kb/traversal.py` | `assemble_from_seed`, `assemble_outfits`, `AssemblyConfig` — pure graph, không Qdrant | **Create** |
| `src/outfitmatch/kb/assemble_record.py` | `to_outfit_record(items, score)` — dựng `OutfitRecord` tag-dẫn-xuất (occasion/style/color_palette/price_tier/gender) | **Create** |
| `src/outfitmatch/retrieval.py` | `search_outfits(request, graph, items, qdrant_url)` Tầng 3: Qdrant seed-filter → assemble → rank → top-N | **Create** |
| `src/outfitmatch/pipeline.py` | `recommend_outfit` wire Tầng 3 + Tầng 4 (`rerank_by_preference`) + `suggest_sizes_for_outfit` | Modify |
| tests tương ứng | | Create/Modify |

**Bất biến:** `OutfitGraph` (sub-proj 1) không sửa. `qdrant_index.py` collection `outfits` không dùng ở đây.

## 5. Traversal algorithm (lõi, `kb/traversal.py`)

```
assemble_from_seed(graph, seed_id, *, config) -> AssembledOutfit | None:
  items = [seed]
  if seed.category == "top":
      bottom = best clique-neighbor of seed in "bottom"   # bắt buộc; None → bỏ seed
      items += [bottom]
  # seed "dress" → core = [dress] (đã đủ); seed "bottom" tương tự cần top
  for opt in ("shoes", "outerwear", "bag", "accessory"):
      cand = best clique-neighbor (edge tới MỌI item đang có) in opt, theo config.prob/topn
      if cand: items += [cand]
  score = mean pairwise edge_weight over all item pairs   # clique đã đảm bảo đủ cạnh
  return AssembledOutfit(items, score)
```
- **Clique đảm bảo coherence**: thêm item chỉ khi `edge_weight(item, x) is not None` với mọi x đang có → mọi cặp đồng gender + coherent formality (bất biến từ sub-proj 1).
- **Anchor = top và dress** (xác định "lõi" outfit). Bottom-seed/standalone không anchor (tránh trùng).
- **Beam nhẹ**: mỗi seed sinh tối đa `config.beam` outfit (thử top-`beam` bottom). Deterministic (neighbors đã sort weight desc; tie theo id).
- **Shoeless hợp lệ**: `shoes` là optional → outfit top+bottom không giày vẫn trả về (đúng mục tiêu extensibility).

`assemble_outfits(graph, seed_ids, config) -> list[AssembledOutfit]`: gọi cho mỗi seed, dedup theo tuple item_id, sort score desc.

## 6. Retrieval (Tầng 3, `retrieval.py`)

```
search_outfits(request, *, graph, items, qdrant_url, top_n=40) -> list[OutfitRecord]:
  1. seed_ids = qdrant_filter_items(qdrant_url, gender?, formality∈occasions_for_formality(request.occasion),
                                    price_tier/price_max, in_stock=True, has_vn_store=True,
                                    category∈{"top","dress"})     # chỉ anchor
  2. assembled = assemble_outfits(graph, seed_ids, config)
  3. post-filter: exclude_colors (loại outfit chứa item màu cấm), price_max (tổng giá), style (giao store-style)
  4. records = [to_outfit_record(a.items, a.score) for a in assembled][:top_n]
  return records
```
- Qdrant filter dùng payload KEYWORD index của `items` collection (sub-proj 1).
- `qdrant_filter_items` tách riêng, **injectable** (test truyền danh sách seed trực tiếp, không cần Qdrant).
- Trả `OutfitRecord` → `rerank_by_preference` + pipeline không đổi.

## 7. `to_outfit_record` — tag dẫn xuất (`kb/assemble_record.py`)

Dựng `OutfitRecord` từ items + score, tái dùng logic giá/gender đã có ý tưởng ở `generation._make_outfit`:
- `gender = _combo_gender(items)`; `price_total_vnd = Σ price`; `price_tier` theo bậc outfit (tái dùng `generation._price_tier`).
- `occasion = occasions_for_formality(max formality band của core items)`.
- `style = sorted(∪ store.style_tags các item)`.
- `color_palette = sorted(∪ item.colors)`.
- `body_shapes_fit = []` (defer, §3).
- `season = []` (defer).
- `compatibility_score = score`; `gen_method = "graph_traversal"`; `schema_version="3.1"`.

→ `OutfitRecord` hợp lệ, `rerank_by_preference` chấm được trên style/occasion/color/price_tier.

## 8. Pipeline wire (`pipeline.recommend_outfit`)
```
recommend_outfit(request):
  graph/items nạp 1 lần (module-level cache hoặc DI)
  records = search_outfits(request, graph=..., items=..., qdrant_url=...)
  if request.quiz_answers: pref = quiz_to_profile(...); records = rerank_by_preference(records, pref, top_k=5)
  else: records = records[:5]
  sizes = suggest_sizes_for_outfit(records[0].items, request.height_cm, request.weight_kg) if records else {}
  return RecommendResult(outfits=records, body_shape=request.body_shape or "", occasion=request.occasion,
                         latency_ms=..., suggested_sizes=sizes)
```
(Explanation Tầng 2 / Qwen vẫn để trống — Sprint 6-7, ngoài phạm vi.)

## 9. Error handling & edge cases
- Graph rỗng / seed rỗng → trả `[]` (pipeline trả `RecommendResult` outfits rỗng, không raise).
- Seed top không có bottom-neighbor clique → bỏ seed (không tạo outfit lỗi).
- `occasion` không hợp formality nào → seed-filter rỗng → `[]` (caller nới filter).
- Qdrant offline → `qdrant_filter_items` injectable; có nhánh fallback "tất cả top/dress in-stock" cho test/CI.

## 10. Testing (tóm tắt)
- `traversal`: seed top → outfit có bottom; clique chặn item không-cạnh; shoeless khi không có shoes-neighbor; dedup; deterministic; beam ≤ config.
- `assemble_record`: `OutfitRecord` hợp lệ; occasion/style/color_palette dẫn xuất đúng; gender = combo gender.
- `retrieval`: seed-filter injectable → assemble → exclude_colors/price_max/style post-filter; trả `OutfitRecord` rerank được.
- `pipeline`: `recommend_outfit` trả top-5, áp quiz rerank, suggested_sizes; rỗng-an-toàn.
- `vocab`: `occasions_for_formality` đúng map, luôn ⊆ OCCASION.

## 11. Out of scope
- **Item semantic tagging** (Gemini tag occasion/style/body_shape per node) — tiền đề cho body-conditioning & style mịn. **Follow-up riêng** (cần cho body-ablation sub-proj 3).
- OT-labse pairwise scorer thật (cắm qua `PairScorer`, sub-proj 1).
- Qwen Tầng 2 explanation/validation, Gradio UI.
- season conditioning.

## 12. Success criteria
- `recommend_outfit` trả 1-5 `OutfitRecord` ráp-động trên catalog thật, latency in-memory < ~1s (Qdrant filter + traverse).
- 0 outfit vi phạm gender/formality (clique đảm bảo).
- Outfit shoeless xuất hiện khi gender/formality-band thiếu giày; sau `--incremental` thêm giày → cùng query có outfit có giày.
- `rerank_by_preference` + `suggested_sizes` chạy không sửa (tương thích `OutfitRecord`).
