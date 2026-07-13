# Plan — Frontend (Next.js 16) + Backend + Qwen3-VL-8B-Thinking Model Integration

**Ngày:** 2026-07-13 · **Branch:** tạo `feature/web-app` từ `feat/benchmark`
**Canonical refs:** `Kien_truc_v3.1.md` §4 (Stylist) / §7 (Pipeline E2E) / §8 (Rubric);
`docs/ARCHITECTURE.md` §0–4; `docs/STYLIST_MODEL_ANALYSIS.md`.

> **Lưu ý wire-format:** tool-call token chuẩn được định nghĩa trong
> `src/outfitmatch/stylist/tools.py` (constants + `parse_tool_call_text`). Trong file plan
> này, thay vì viết literal token (gây parse artifact), gọi là `[T-OPEN]` / `[T-CLOSE]`
> (mở/đóng tool-call) và `[TR-OPEN]` / `[TR-CLOSE]` (mở/đóng tool-result). Đối chiếu
> `tools.py` cho giá trị chính xác.

---

## 0. TL;DR

Build **2 deliverable** trên nền pipeline v3.1-lite đã chạy:

1. **Backend Python (FastAPI)** — serve graph KB + Qwen3-VL-8B-Thinking + LoRA adapter
   `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora`. Implement
   `stylist/model.py` (hiện là `NotImplementedError` stub) + `stylist/service.py` (agent
   loop) + wire vào `pipeline.py` step 2/3/6/7 (đang stub).
2. **Frontend Next.js 16 (TypeScript, App Router, Turbopack)** — chat hội thoại + quiz
   onboarding + outfit display, consume backend qua REST + SSE streaming.

**Quyết định backend: Dùng Python (FastAPI), KHÔNG dùng Rust.** Xem §1.

---

## 1. Quyết định Rust vs Python — so sánh kỹ thuật

### 1.1 Constraint cốt lõi: adapter đã train

Adapter production là **PEFT LoRA** (`peft_type: LORA`, r=16, alpha=32, all-linear targets),
base model `unsloth/Qwen3-VL-8B-Thinking-bnb-4bit` — checkpoint **bitsandbytes 4-bit
pre-quantized**. Repo ship `adapter_config.json` + `adapter_model.safetensors` (175 MB) +
`chat_template.jinja` + `tokenizer.json` + `trainer_state.json`. Commit 16 ngày trước.

### 1.2 Rust (mistral.rs / candle) — khả thi hay không?

| Tiêu chí | mistral.rs (candle) | Đánh giá |
|---|---|---|
| Architecture `Qwen3VLForConditionalGeneration` | ✅ Supported (Qwen3-VL row) | OK |
| Load base bnb-4bit checkpoint | ❌ Không support bnb-4bit. Quantize chỉ GGUF/UQFF/GPTQ/AWQ | **Blocker** |
| Apply PEFT LoRA adapter riêng | ❌ Không apply PEFT adapter trực tiếp. Phải merge LoRA vào base rồi convert | **Blocker** |
| Output identical với Python inference | ❌ Mất exact quantization + re-quantize → hành vi fine-tune bị drift | **Rủi ro cao** |
| Re-run mỗi lần update adapter | ✅ Phải merge+convert lại mỗi lần | Friction trong loop fine-tune |

### 1.3 Python (transformers + peft + bitsandbytes)

| Tiêu chí | Python | Đánh giá |
|---|---|---|
| Load bnb-4bit base + PEFT LoRA | ✅ Native, 1 dòng `PeftModel.from_pretrained` | OK |
| Exact hành vi adapter đã train | ✅ Đúng config train | OK |
| Đã verified chạy | ✅ `scripts/stylist/run_inference_device.py` chạy OK trên RTX 5060 8GB | OK |
| Tầng 3/4 (retrieval/rerank/sizing) | ✅ Toàn bộ Python, coupled parquet/pandas graph KB | OK |
| Latency bottleneck | LLM generate 5–8s — **không phải retrieval layer**. Rust không giảm bottleneck | — |
| vLLM (serving tăng tốc) | ⚠️ Không có wheel Windows. Chỉ là path cloud tương lai, không cho dev local | Defer |

### 1.4 Kết luận

**Backend 100% Python (FastAPI + uvicorn).** Lý do:
1. Model layer **bắt buộc** Python — Rust không load được bnb-4bit + PEFT LoRA mà không
   convert mất tính chính xác của adapter đã train.
2. Retrieval/graph layer đã Python + có **hard guards** (coherence violations = 0,
   recall@5 ≈ 0.98). Rewrite Rust = tuần re-implement + re-validate, rủi ro vỡ guard.
3. Bottleneck latency là LLM generate, không phải retrieval → Rust không giúp.
4. Team 3 sinh viên, 7 tuần, Windows + RTX 5060 8GB — chi phí Rust không xứng ROI.
5. Rust BFF/gateway mỏng chỉ thêm 1 network hop, lợi ích không đáng kể cho MVP.

**Defer (không nằm trong scope plan này):** convert adapter → GGUF + mistral.rs server
chỉ khi deploy production cloud multi-user cần throughput cao (sau khi đóng môn).

---

## 2. Verified facts (web-verify)

| Fact | Giá trị | Nguồn |
|---|---|---|
| Next.js 16 stable | App Router + React Canary (19.2+). Turbopack default. Async Request APIs (cookies/headers/params/searchParams async). `middleware`→`proxy`. React Compiler stable. Cache Components. ESLint flat config. AMP removed. `next lint` removed. | nextjs.org/docs/app/guides/upgrading/version-16 (cập nhật 2026-05-13) |
| Next.js 16 Node requirement | **Node.js ≥ 20.9** (Node 18 unsupported). TypeScript ≥ 5.1. | same |
| Node 26.5.0 | "Current" (LTS từ 2026-10-28). Thỏa mãn Next 16 req. | nodejs.org/en/blog/release/v26.5.0 |
| Mistral.rs Qwen3-VL | Support `Qwen3VLForConditionalGeneration` + `Qwen3VLMoeForConditionalGeneration`. Không support bnb-4bit / PEFT LoRA trực tiếp. | ericlbuehler.github.io/mistral.rs/reference/supported-models/ |
| Adapter HF repo | LoRA r=16 α=32, base `unsloth/Qwen3-VL-8B-Thinking-bnb-4bit`, class `Qwen3VLForConditionalGeneration`. Files: adapter_config.json, adapter_model.safetensors (175 MB), chat_template.jinja, tokenizer.json, trainer_state.json. | huggingface.co/Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora |

**Local constraints (từ memory + repo):**
- Windows + RTX 5060 8GB + CUDA 13.3: **phải cài torch+cu130 vào `.venv`, KHÔNG dùng `uv run`**
  (uv re-sync torch CPU → GPU script fail). Serve backend bằng `.venv/Scripts/python.exe -m uvicorn`.
- bnb-4bit: dùng `device_map={"": 0}` (KHÔNG `"auto"`) để skip CPU-dispatch ValueError.
- Qwen-VL processor: call `processor(text=[prompt], images=None, ...)` cho text-only prompt.
- Pipeline graph KB: 5,618 catalog items + 316,559 edges, đã load qua `pipeline._default_graph()`.

---

## 3. Target architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ FRONTEND — Next.js 16 (web/) · TypeScript · App Router · Turbopack │
│  /  /quiz  /chat  /recommend  /outfit/[id]                        │
│  API client (typed) + SSE consumer → fetch /api/* (proxy rewrite)  │
└──────────────────────────────┬───────────────────────────────────┘
                               │  REST + SSE  (localhost:3000 → :8000)
┌──────────────────────────────┴───────────────────────────────────┐
│ BACKEND — FastAPI (src/outfitmatch/server/)                       │
│  Startup singletons (load 1 lần):                                 │
│    • OutfitGraph (parquet → 316K edges)                           │
│    • Qwen3-VL-8B-Thinking-bnb-4bit + LoRA adapter (PEFT)          │
│    • (optional) Qdrant items seed index                           │
│  Routes:                                                          │
│    POST /api/chat          (SSE streaming agent loop)             │
│    POST /api/recommend     (structured RecommendRequest→Result)   │
│    GET  /api/quiz          (onboarding 5 câu schema)             │
│    GET  /api/outfits/{id}  (outfit detail + items + store links)  │
│    GET  /api/catalog/item/{id}/image  (serve item webp)          │
│    GET  /api/health        (liveness + model load status)        │
│  Guardrails (bắt buộc trước khi trả UI):                          │
│    validate_response (chống hallucinate outfit_id)               │
│    validate_sizes (chống size không có thật)                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────┴───────────────────────────────────┐
│ EXISTING v3.1-lite core (đã chạy, KHÔNG sửa behavior)            │
│  stylist/tools.py · validation.py · retrieval.py · traversal.py  │
│  quiz/rerank.py · quiz/sizing.py · pipeline.py · kb/*            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Backend plan (FastAPI)

### 4.1 Startup singletons (`server/deps.py`)

Load **một lần** tại startup (warm), giữ trong app state, reuse cho mọi request:

```python
# pseudo
@asynccontextmanager
async def lifespan(app):
    graph = _default_graph()              # đã có, lru_cache
    model, processor = load_stylist_model(
        base="unsloth/Qwen3-VL-8B-Thinking-bnb-4bit",
        adapter="Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora",
        load_in_4bit=True,
    )
    app.state.graph = graph
    app.state.stylist = StylistService(model, processor, graph)
    yield
```

- Qdrant: **optional**. Demo có thể skip (retrieval fallback graph scan qua
  `_fallback_seed_ids`). Chỉ bật nếu `QDRANT_URL` env set + `make qdrant-up`.
- Model load theo memory: `device_map={"": 0}`, `torch_dtype="auto"` (bnb-4bit lm_head
  bf16), BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
  bnb_4bit_use_double_quant=True). VRAM peak ≈ 6.8 GB trên 8GB GPU.

### 4.2 Model integration — implement `stylist/model.py` + mới `stylist/service.py`

`stylist/model.py` (hiện stub → implement):
- `load_stylist_model(base, adapter, load_in_4bit=True) -> (model, processor)`
  mirror `run_inference_device.py`: Qwen3VLForConditionalGeneration + bnb config +
  PeftModel.from_pretrained(adapter). Trả (model, processor).
- Đọc `chat_template.jinja` từ adapter repo (processor tự load, nhưng verify).
- Đừng dùng `AutoModelForCausalLM` (sai class VL, sẽ vỡ).

`stylist/service.py` (MỚI) — `StylistService` agent loop (theo §7 step 2–7):
1. Build messages: system prompt (vai trò stylist VN + tool schema `SEARCH_OUTFITS_TOOL`
   từ `tools.py`) + history + user text + (optional image).
2. Stream generate (TextIteratorStreamer). Model "Thinking" emit khối reasoning
   (token mở/đóng thinking) trước. Frontend show collapsible "Đang suy nghĩ…".
3. Detect tool call: parse bằng `tools.parse_tool_call_text` (token chuẩn `[T-OPEN]` /
   `[T-CLOSE]`, JSON đúng schema `search_outfits`). Nếu có → execute retrieval.
4. Execute `retrieval.search_outfits(request, graph=...)` → `rerank_by_preference` (nếu
   có quiz) → `suggest_sizes_for_outfit` (nếu có height/weight).
5. Inject tool result vào history (token `[TR-OPEN]` / `[TR-CLOSE]`, JSON từ step 4).
   Generate tiếp (pass 2).
6. Final turn: Vietnamese explanation + outfit refs `OF_XXXXX`.
7. **validate_response**: extract outfit_ids, check tồn tại trong set ID retrieval vừa
   trả. Nếu hallucinate → không hiển thị, fallback "Xin lỗi, mình không tìm thấy outfit
   phù hợp".
8. **validate_sizes**: nếu model nhắc size cụ thể, check `available_sizes` /
   `sizes_in_stock`.

Trả structured payload kèm SSE stream: tokens + `outfit_cards` event (JSON) + `done` event.

### 4.3 Wire `pipeline.py` step 2/3/6/7

`pipeline.recommend_outfit()` hiện chỉ làm step 4–5 (retrieval+rerank+sizing), step
2/3/6/7 (Qwen) stub. Thêm optional `stylist: StylistService | None` param:
- Nếu `stylist` truyền vào + free-text intent / image → dùng Qwen parse.
- Nếu không → giữ path hiện tại (deterministic, testable) cho `/api/recommend` structured.
- Sinh `explanation_vi` qua stylist (hiện empty).

### 4.4 API contract (Pydantic schemas — `server/schemas.py`)

Mirror `RecommendRequest` / `RecommendResult` + chat:

```python
class ChatRequest(BaseModel):
    message: str
    image: UploadFile | None = None
    conversation_id: str | None = None
    quiz_answers: QuizAnswers | None = None
    history: list[dict] = []           # [{role, content}]

class OutfitCardDTO(BaseModel):        # cho frontend render
    outfit_id: str
    items: list[ItemCardDTO]
    occasion: list[str]
    style: list[str]
    color_palette: list[str]
    price_total_vnd: int
    price_tier: str
    suggested_size: dict[str, str]
    explanation_vi: str
    compatibility_score: float

class ChatEvent:                        # SSE event union
    type: Literal["token", "thinking", "outfit_cards", "done", "error"]
    # payload tùy type
```

- `POST /api/recommend` → `RecommendResult` (đã có schema, expose trực tiếp).
- `GET /api/quiz` → 5 câu hỏi + enum options từ `vocab.py` (`*_LABELS_VI`).
- `GET /api/outfits/{id}` → rebuild outfit từ graph. Lưu ý: outfit_id dynamic (derived
  tại retrieval qua `to_outfit_record(index=...)`). Cache kết quả retrieval theo
  `conversation_id` để resolve lại.

### 4.5 Launch script (`scripts/serve.py`)

```bash
# QUAN TRỌNG: dùng venv python có cu130 torch, KHÔNG dùng uv run
.venv/Scripts/python.exe -m uvicorn outfitmatch.server.app:app --host 0.0.0.0 --port 8000 --reload
```
Thêm `make serve` target. `.env`: `HF_HOME`, `HF_HUB_OFFLINE` nếu model local, `QDRANT_URL?`.

---

## 5. Frontend plan (Next.js 16)

### 5.1 Scaffold

```bash
npx create-next-app@latest web --typescript --app --turbopack --no-src-dir
# Node 26.5.0 thỏa mãn Next 16 (req ≥20.9). Lưu ý Node 26 là "Current" (LTS 2026-10-28).
cd web && npm i
```
`next.config.ts`: Turbopack top-level, `rewrites()` proxy `/api/* → http://localhost:8000/api/*`
(dev), `images.remotePatterns` cho item images served bởi backend.

### 5.2 Pages (App Router)

| Route | Mục đích |
|---|---|
| `/` | Landing/hero, CTA "Bắt đầu quiz" / "Chat ngay" |
| `/quiz` | Onboarding 5 câu (style/occasions/colors/budget/height-weight) → POST quiz → preference profile → redirect `/chat` hoặc `/recommend` |
| `/chat` | Stylist hội thoại: input text + image upload, SSE stream, render thinking + outfit cards + explanation_vi |
| `/recommend` | Form structured (occasion enum, style, budget slider, height/weight) → POST /api/recommend → outfit grid |
| `/outfit/[id]` | Outfit detail: items + store links + images + size pills + explanation |

### 5.3 Components

- `chat/ChatWindow`, `chat/MessageBubble`, `chat/ThinkingPanel` (collapsible), `chat/ImageUpload`,
  `chat/Streamer` (fetch + ReadableStream parse SSE).
- `outfit/OutfitCard`, `outfit/ItemCard`, `outfit/SizePill`, `outfit/StoreLink`.
- `quiz/QuizStepper`, `quiz/BudgetSlider`, `quiz/EnumPicker` (options từ `/api/quiz`).
- `ui/*` primitives (Button, Slider, Sheet...). Có thể dùng shadcn/ui (RSC-compatible,
  Tailwind) hoặc tự build. Quyết định ở sprint scaffold.

### 5.4 API client (`web/lib/api.ts`, `web/lib/types.ts`)

- `types.ts` mirror Pydantic schemas. Recommend `openapi-typescript` để auto-gen type từ
  FastAPI `/openapi.json` (đơn nguồn sự thật, tránh drift).
- `api.ts`: typed fetch wrappers (`getQuiz`, `recommend`, `getOutfit`, `getItemImage`).
- `sse.ts`: consume `POST /api/chat` SSE stream (fetch + `ReadableStream` reader, parse
  `event:` / `data:` lines, dispatch tới React state). KHÔNG dùng EventSource (không
  support POST + headers).

### 5.5 Image handling

- Item images: backend `GET /api/catalog/item/{id}/image` serve `data/custom/catalog/images/*.webp`.
- Next 16 breaking changes cần config: `images.qualities` default `[75]`,
  `minimumCacheTTL` 4h, dùng `images.remotePatterns` (KHÔNG dùng deprecated `images.domains`),
  `images.dangerouslyAllowLocalIP` nếu dev local.
- Selfie upload (chat): multipart → backend temp → Qwen-VL processor image input.

---

## 6. Directory structure (mới)

```
fashion_match_project/
  web/                              # Next.js 16 frontend (MỚI)
    package.json, next.config.ts, tsconfig.json
    app/  components/  lib/
  src/outfitmatch/
    server/                         # FastAPI backend (MỚI)
      __init__.py
      app.py                        # FastAPI app factory + lifespan
      deps.py                       # startup singletons
      schemas.py                    # API Pydantic
      routes/{chat,recommend,quiz,outfits,health,catalog}.py
    stylist/
      model.py                      # IMPLEMENT (hiện stub)
      service.py                    # MỚI: StylistService agent loop
      tools.py · validation.py      # đã có, dùng nguyên
    pipeline.py · retrieval.py · quiz/* · kb/*    # đã có
  scripts/
    serve.py                        # MỚI: uvicorn launcher
  docs/superpowers/plans/2026-07-13-frontend-backend-model-integration.md  # file này
```
Giữ `src/outfitmatch/ui/gradio_app.py` làm debug-internal tool (không phải primary demo nữa).

---

## 7. Sprint / task breakdown

Thứ tự có dependency. Mỗi task = 1 commit (`feat:` / `fix:` tiếng Việt ≤72 ký tự) + push
`origin Model` theo CLAUDE.md git workflow.

### Phase A — Backend model integration (block frontend chat)
- **A1.** Implement `stylist/model.py::load_stylist_model` (mirror `run_inference_device`).
  Test: load OK, generate 1 prompt VN, VRAM <7GB. (`tests/test_stylist_model.py`)
- **A2.** Implement `stylist/service.py::StylistService` agent loop (generate→parse tool→
  retrieval→validate→explain). Test mock model + real graph: tool call parse 100%,
  `validate_response` chặn hallucinated ID. (`tests/test_stylist_service.py`)
- **A3.** Wire `pipeline.py` step 2/3/6/7 optional stylist param; sinh `explanation_vi`.

### Phase B — FastAPI server
- **B1.** `server/app.py` + `deps.py` lifespan (load graph + model). `scripts/serve.py`.
  `make serve`. (`tests/test_server_health.py`)
- **B2.** `routes/recommend.py` + `quiz.py` + `outfits.py` + `catalog image`. Test contract.
- **B3.** `routes/chat.py` SSE streaming + StylistService. Test SSE event shapes (mock stylist).

### Phase C — Frontend scaffold + non-chat pages
- **C1.** `create-next-app` Next 16 + Tailwind + config (rewrites, images). Landing `/`.
- **C2.** `lib/types.ts` + `lib/api.ts` (auto-gen từ openapi hoặc tay). `/recommend` form + grid.
- **C3.** `/quiz` stepper (options từ `/api/quiz`). `/outfit/[id]` detail.

### Phase D — Chat UX (phụ thuộc A+B)
- **D1.** `/chat` page + `Streamer` SSE consumer + `ThinkingPanel` + `MessageBubble`.
- **D2.** Image upload (multipart) → backend → VL image input.
- **D3.** `OutfitCard` render từ `outfit_cards` SSE event + store links + size pills.

### Phase E — Polish + eval wiring
- **E1.** E2E smoke: `make serve` + `npm run dev` → chat 1 request thật → outfit cards +
  explanation_vi hiển thị đúng. Latency log.
- **E2.** Hook LLM-judge (Gemini) chấm output E2E (`EXPERIMENT_GUIDE.md`) — target mean ≥3.5/5.
- **E3.** Docs: `docs/feature.md` entry + update `SPRINT_REPORT` + `ARCHITECTURE` §0 snapshot.

---

## 8. Risks & constraints

| Rủi ro | Mitigation |
|---|---|
| 8GB VRAM OOM khi concurrent request | Demo single-request. Cấu hình `max_concurrency=1` hoặc queue. Đo VRAM peak. |
| Node 26 "Current" chưa LTS | OK cho 7-tuần MVP. Nếu lỗi weird, fallback Node 24 LTS (Active LTS). |
| "Thinking" model emit reasoning dài → latency | Stream thinking collapsible; set `max_new_tokens` hợp lý; đo first-token latency. |
| Tool-call format drift giữa train & infer | Dùng đúng `parse_tool_call_text` từ `tools.py` (canonical, đã lock ở grounded-stylist plan Phase A). |
| outfit_id dynamic (derived tại retrieval) | Cache kết quả retrieval theo `conversation_id` để `/outfit/[id]` resolve lại. |
| Windows torch CPU khi `uv run` | Serve backend LUÔN bằng `.venv/Scripts/python.exe -m uvicorn` (cu130 torch). Document rõ. |
| `next/image` breaking changes (qualities/TTL/remotePatterns) | Config `images.remotePatterns` + `qualities=[75]`. Test ảnh item hiển thị. |
| Hallucinate outfit_id / size | `validate_response` + `validate_sizes` chạy **trước** khi payload tới frontend. |

---

## 9. Definition of Done

1. `make serve` (backend) + `cd web && npm run dev` (frontend) chạy song song, E2E smoke
   xanh: chat 1 request VN thật → outfit cards + explanation_vi hiển thị đúng, latency <8s.
2. `pytest` coverage ≥70% cho `server/`, `stylist/model.py`, `stylist/service.py`. CI xanh.
3. `validate_response` + `validate_sizes` chặn hallucinated outfit_id/size (test regression).
4. Graph guards không vỡ: coherence violations = 0, recall@5 không regress (chạy
   `eval_graph` nếu đụng retrieval).
5. Public functions có docstring; entry `docs/feature.md` + `SPRINT_REPORT` cập nhật.
6. `git add -A && git commit -m "..." && git push origin Model` mỗi task.
7. (Data chỉ đổi nếu cần cache model local — không push HF dataset trừ khi data đổi.)

---

## 10. Out of scope (defer)

- Rust backend / mistral.rs serving (xem §1.4 — chỉ khi production cloud multi-user).
- vLLM serving (không có wheel Windows).
- GNN personalization (Phụ lục A, sau môn).
- Auth / user accounts (MVP cold-start quiz, không user thật).
- PWA / mobile native.
