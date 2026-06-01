# Graph KB Grading Redefinition — Design Spec (Sub-project 3)

**Status:** Approved direction ("định nghĩa lại grading"). Decisions below need a quick review — see §3 ⚠️.
**Date:** 2026-06-01
**Depends on:** sub-project 1 (graph) + sub-project 2 (traversal `assemble_outfits`, `AssemblyConfig`).
**Next:** plan `docs/superpowers/plans/2026-06-01-graph-grading-redefinition.md`.

---

## 1. Goal

Định nghĩa lại bộ đo grading cho KB-graph (thay vì materialized `outfits` collection):
1. **Recall@K** — đo trên outfit **ráp động** bằng FITB-on-graph (mask 1 item, xem traversal có recover trong top-K). Thay "Recall@5 trên outfits collection".
2. **Graph coverage report** — metric chính cho mục tiêu diversity ban đầu: **% catalog xuất hiện trong ≥1 outfit** + item-reuse + degree + coherence-violations (phải 0). Thay `OutfitBuildReport` chạy trên materialized frame.
3. Giữ nguyên **FITB accuracy + Compatibility AUC** (`metrics/outfit.py`) — chúng đo **encoder OT trên Polyvore**, độc lập biểu diễn KB.
4. Map lại 4 ablation bắt buộc sang thế giới graph.

## 2. Bối cảnh (đã kiểm chứng)

- `metrics/outfit.py`: `fitb_accuracy(preds, labels)`, `compatibility_auc(scores, labels)` — generic, dùng cho OT/Polyvore. **Không sửa.**
- `kb/evaluation.py`: `OutfitBuildReport` + `evaluate_outfit_frame` chạy trên parquet outfit materialized (cột `item_ids/categories/gender/price_tier/compatibility_score`). KB-graph không sinh frame này → cần report mới.
- Grading targets hiện tại (`CLAUDE.md` / `Kien_truc_v3.1.md` §grading): Recall@5 (baseline+5pp), FITB ≥55%, Compat AUC ≥0.85, Body-cond Precision@5 (+10pp), E2E latency, LLM-judge. 4 ablation: encoder variants / body on-off / occasion on-off / greedy vs beam.

## 3. ⚠️ Quyết định cần review

| Mục | Quyết định MVP | Ghi chú |
|---|---|---|
| **Recall@5 ground-truth** | KB-graph không có nhãn "outfit đúng/query". Dùng **FITB-on-graph self-consistency**: lấy outfit ráp được làm "good", mask 1 item (mặc định `shoes`), rank ứng viên clique theo weight, Recall@K = tỉ lệ recover top-K. | Đây là proxy nội tại, không cần dataset nhãn ngoài. Số mục tiêu cũ (baseline+5pp) **recalibrate** sau lần đo đầu. |
| **Diversity metric** | `catalog_coverage` = % item adult xuất hiện trong ≥1 outfit khi sweep seed. Đây là **đáp số trực tiếp** cho vấn đề 4% ban đầu. | Đặt target sơ bộ (vd ≥60%) sau khi đo. |
| **Body-cond Precision@5 ablation** | **BLOCKED** — node chưa có body-fit tag. Cần **item semantic tagging follow-up** (Gemini tag body_shape per node). Spec này định nghĩa harness nhưng để ablation body ở trạng thái "pending tagging". | Encoder/occasion/decoding ablation map được ngay (xem §6). |
| **Encoder ablation (OT zero-shot vs fine-tuned)** | Giữ nguyên trên Polyvore qua `metrics/outfit.py` — không thuộc KB-graph. | Không đổi. |

## 4. Architecture & module layout

| File | Trách nhiệm | Hành động |
|---|---|---|
| `src/outfitmatch/metrics/retrieval.py` | `recall_at_k(retrieved, relevant, k)` generic + `fitb_recall_at_k(graph, outfits, k, masked_category)` | **Create** |
| `src/outfitmatch/kb/graph_eval.py` | `GraphReport` + `evaluate_graph(graph, items, seed_ids, config)` (coverage/reuse/degree/coherence) + `summarize_graph_report` | **Create** |
| `scripts/data/kb/eval_graph.py` | CLI: nạp graph+catalog → in GraphReport + fitb_recall@5 + ablation occasion/decoding | **Create** |
| `Kien_truc_v3.1.md`, `CLAUDE.md`, `docs/EXPERIMENT_GUIDE.md` | Cập nhật bảng metric + ablation cho graph | Modify |
| tests tương ứng | | Create |

**Bất biến:** `metrics/outfit.py` (FITB/Compat AUC), `evaluation.py` (OutfitBuildReport — giữ cho materialized legacy cho tới khi gỡ ở §7) không sửa logic.

## 5. Metrics

### 5.1 `recall_at_k` (generic)
`recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float` = |top-k ∩ relevant| / |relevant|. Dùng lại cho mọi định nghĩa retrieval.

### 5.2 `fitb_recall_at_k` (graph-native)
```
fitb_recall_at_k(graph, outfits, *, k=5, masked_category="shoes") -> float:
  eligible = outfits có ≥1 item thuộc masked_category và ≥2 item khác
  for each: context = items \ {masked}; true_id = masked.item_id
     candidates = item kết nối clique với MỌI context item, ở masked_category
     rank candidates theo mean edge_weight tới context, desc
     hit nếu true_id ∈ top-k
  return hits / len(eligible)
```
→ Recall@K nội tại, đo chất lượng ranking của graph khi "điền chỗ trống".

### 5.3 `GraphReport` (diversity + integrity)
```
n_nodes, n_edges
degree_min / degree_median / degree_max
coherence_violations  # edges vi phạm gender/formality — MUST be 0 (regression guard)
catalog_coverage      # % item xuất hiện trong ≥1 assembled outfit (diversity)
distinct_items_used, n_assembled
item_reuse_p95        # 95th pct số outfit tái dùng 1 item (đối lập với cảnh 1 giày/72 outfit cũ)
```

## 6. Ablation mapping (4 bắt buộc → graph)

| Ablation gốc | Cách đo trong graph |
|---|---|
| (1) encoder OT zero-shot vs fine-tuned | **Không đổi** — Polyvore + `metrics/outfit.py`. |
| (2) body conditioning on/off | **BLOCKED** — cần item body-tag (follow-up). Harness `recall_at_k` sẵn sàng. |
| (3) occasion conditioning on/off | Seed-filter **có** vs **không** `formalities_for_occasion` → so coverage/precision của outfit hợp occasion. |
| (4) greedy vs beam decoding | `AssemblyConfig(beam=1)` vs `beam=3` → so diversity/score. |

## 7. Migration (gỡ materialized — cuối sub-project 3)
Sau khi graph-eval xanh và được duyệt:
- Đánh dấu **deprecated** (không xoá vội): `generate_outfits.py`, `build_outfits.py`, `generation.py`, `scoring.py`, `qdrant_index.py` (collection `outfits`), `evaluation.py`. Ghi chú trỏ sang graph path.
- Xoá thật ở một dọn dẹp riêng sau khi pipeline graph chạy E2E ổn định (tránh xoá nhầm khi graph chưa kiểm chứng). **Không** gỡ trong cùng task tạo eval.

## 8. Error handling
- Graph rỗng → report toàn 0, `catalog_coverage=0.0`, không raise.
- Không outfit nào có `masked_category` → `fitb_recall_at_k` trả 0.0 (eligible rỗng) + log.
- `coherence_violations > 0` → eval CLI exit code ≠ 0 (regression: graph build sai).

## 9. Testing
- `recall_at_k`: case cơ bản (hit/miss/empty relevant).
- `fitb_recall_at_k`: outfit mask shoes → true shoe rank top-1 khi là neighbor mạnh nhất; miss khi bị đẩy ngoài k.
- `evaluate_graph`: coverage đếm đúng; coherence_violations=0 trên graph hợp lệ, >0 khi chèn edge xấu thủ công; reuse_p95 hợp lý.
- `eval_graph` CLI: exit 0 trên graph thật; exit≠0 khi coherence_violations>0.

## 10. Out of scope
- **Item semantic tagging** (mở khoá body-ablation) — follow-up.
- Xoá thật code materialized (§7 chỉ deprecate).
- LLM-as-judge harness (Gemini) — Sprint 9, riêng.

## 11. Success criteria
- `eval_graph` in: GraphReport (coverage, coherence=0, reuse), fitb_recall@5, ablation occasion(on/off) + decoding(beam 1 vs 3).
- `catalog_coverage` đo được và **cao hơn rõ rệt** mức 4% của materialized cũ (đặt target chính thức sau lần đo).
- `coherence_violations == 0` (khoá regression cho sub-project 1+2).
- Docs grading (`Kien_truc`/`CLAUDE.md`/`EXPERIMENT_GUIDE`) phản ánh định nghĩa mới + ablation map + body-ablation pending.
