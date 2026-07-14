# OutfitMatch — Hướng dẫn Cài đặt & Chạy Web UI

> **Dành cho:** Co-worker clone repo từ GitHub và chạy web UI trên máy local.
> **Cập nhật:** 2026-07-14 · **Branch:** `Model` (hoặc `feat/benchmark`)

---

## 0. Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Cách kiểm tra |
|---|---|---|
| Python | **3.13** | `python --version` |
| Node.js | **≥20.9** | `node --version` |
| npm | đi kèm Node.js | `npm --version` |
| Git | bất kỳ | `git --version` |
| GPU NVIDIA (tùy chọn) | 8GB+ VRAM, CUDA 12.4+ | `nvidia-smi` |

> **GPU là optional.** Không có GPU → server vẫn chạy, nhưng stylist chat sẽ unavailable (trả HTTP 503). Recommend vẫn hoạt động qua deterministic path.

---

## 1. Clone repo

```bash
git clone https://github.com/Lendo-Stylix/fashion_match.git
cd fashion_match
```

> **Lưu ý:** Repo đã chuyển từ `vominhnhatquang/fashion_match_project` sang `Lendo-Stylix/fashion_match`.

---

## 2. Cài đặt Python backend

### 2.1 Cài `uv` (package manager)

```powershell
# Windows PowerShell (Admin)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2.2 Cài dependencies

```bash
uv sync --group dev
```

Quá trình này cài tất cả Python packages vào `.venv/`, bao gồm:
- `torch`, `transformers`, `peft`, `bitsandbytes` (model)
- `fastapi`, `uvicorn`, `sse-starlette` (server)
- `pytest`, `ruff`, `mypy` (dev tools)

> **Thời gian:** ~5-10 phút tùy tốc độ mạng.

---

## 3. Cài đặt Frontend (Next.js)

```bash
cd web
npm install
cd ..
```

> **Thời gian:** ~2-5 phút.

---

## 4. (Tùy chọn) Tải model stylist

**Chỉ cần nếu bạn có GPU NVIDIA và muốn chạy chat với stylist.**

```bash
uv run python scripts/setup_models.py --base --adapters
```

Script này tải về `D:/Models/`:
- `Qwen/Qwen3-VL-8B-Thinking` (bnb-4bit, ~6.8 GB VRAM)
- `Nhat-Quang/outfitmatch-stylist-final-qwen3vl8b-thinking-lora` (LoRA adapter)

> Nếu không có GPU, **bỏ qua bước này**. Server vẫn chạy bình thường.

---

## 5. Chạy Web UI

Mở **2 terminal** riêng biệt:

### Terminal 1 — Backend (FastAPI)

```bash
cd fashion_match
make serve
```

Output mong đợi:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
Graph KB: ✅ loaded (4694 nodes, 316559 edges)
Stylist model: ✅ loaded (có GPU) / ⚠️ unavailable (không GPU)
```

### Terminal 2 — Frontend (Next.js)

```bash
cd fashion_match
make web-dev
```

Output mong đợi:
```
▲ Next.js 16.2.10 (Turbopack)
- Local:        http://localhost:3000
```

### Truy cập

| URL | Mô tả |
|---|---|
| http://localhost:3000 | **Web UI** — trang chủ |
| http://localhost:3000/chat | Chat với AI Stylist |
| http://localhost:3000/quiz | Quiz onboarding (5 câu) |
| http://localhost:3000/results | Kết quả gợi ý outfit |
| http://localhost:8000/docs | **API docs** (Swagger UI) |
| http://localhost:8000/openapi.json | OpenAPI schema |

---

## 6. Kiểm tra hệ thống hoạt động

### 6.1 Backend test

```bash
make test-fast
```

Kết quả mong đợi: `29 passed` (hoặc ít hơn nếu không có GPU — các test mock model vẫn pass).

### 6.2 Health check API

```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "status": "ok",
  "graph_loaded": true,
  "stylist_available": true,   // false nếu không có GPU
  "gpu_available": true         // false nếu không có GPU
}
```

### 6.3 Quiz API

```bash
curl http://localhost:8000/api/quiz
```

Trả về 5 câu hỏi onboarding.

### 6.4 Recommend API (deterministic, không cần GPU)

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"occasion": "office"}'
```

### 6.5 Frontend build check

```bash
make web-build
```

Kết quả mong đợi: `✓ Compiled successfully`.

---

## 7. Các lệnh Makefile thông dụng

```bash
make serve          # Chạy backend (production)
make serve-dev      # Chạy backend (hot reload, port 8001)
make web-dev        # Chạy frontend dev server
make web-build      # Build frontend production
make test-fast      # pytest nhanh (không coverage)
make test           # pytest + coverage report
make lint           # ruff check + format check + mypy
make format         # ruff format + auto-fix
make qdrant-up      # Khởi động Qdrant (Docker) — optional
make qdrant-down    # Tắt Qdrant
```

---

## 8. Xử lý sự cố thường gặp

### "No module named 'torch'" hoặc "Cannot access accelerator device"

Nguyên nhân: `uv run` tự động cài torch CPU, ghi đè torch CUDA.

**Fix:** Dùng `.venv/Scripts/python.exe` trực tiếp (không `uv run`):
```bash
.venv/Scripts/python.exe -m uvicorn outfitmatch.server.app:app --host 0.0.0.0 --port 8000
```

### "port 8000 already in use"

```bash
# Windows: tìm process đang dùng port 8000
netstat -ano | findstr :8000
# Kill process
taskkill /PID <PID> /F
```

### "Qdrant connection refused"

Không có Qdrant → server tự động fallback sang graph scan. Không ảnh hưởng đến chức năng.

### "Model not found at D:/Models/..."

Stylist model chưa được tải. Chạy `uv run python scripts/setup_models.py --base --adapters` hoặc bỏ qua — server vẫn hoạt động.

### Next.js build lỗi TypeScript

```bash
cd web
npx tsc --noEmit    # Kiểm tra type errors
npm run build       # Build lại
```

---

## 9. Cấu trúc thư mục quan trọng

```text
fashion_match/
├── src/outfitmatch/       # Python source code
│   ├── server/            # FastAPI backend (mới)
│   ├── stylist/           # Model + service
│   ├── kb/                # Graph KB
│   ├── quiz/              # Onboarding quiz
│   └── pipeline.py        # E2E pipeline
├── web/                   # Next.js 16 frontend (mới)
│   └── src/app/           # Pages: home, chat, quiz, results
├── scripts/
│   ├── serve.py           # Backend launch script
│   └── setup_models.py    # Tải model về local
├── tests/                 # Unit + E2E tests
├── docs/                  # Tài liệu
├── data/custom/           # Catalog, graph, outfits parquet files
├── Makefile               # Convenience commands
└── pyproject.toml         # Python project config
```

---

## 10. Liên hệ

| Vai trò | Người phụ trách |
|---|---|
| Data/KB | Nhật Quang |
| Model/Stylist | Đình Lộc |
| Retrieval/API/UI | Hữu Hoàng |

Repo: https://github.com/Lendo-Stylix/fashion_match