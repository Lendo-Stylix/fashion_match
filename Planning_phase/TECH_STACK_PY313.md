# Tech Stack — OutfitMatch
## Python 3.13 Edition

> **Last updated**: May 2026  
> **Python**: 3.13.x (CPython)  
> **Package manager**: [uv](https://docs.astral.sh/uv/) (khuyến nghị) hoặc pip  
> **Env isolation**: uv venv / conda (bắt buộc cho faiss-gpu)

---

## ⚠️ Compatibility Notes trước khi cài

| Package | Tình trạng với 3.13 | Giải pháp |
|---|---|---|
| `mediapipe` | ❌ Không có wheel cp313, build from source fail do ABI break | Thay bằng `ultralytics` (YOLOv8-pose) |
| `faiss-cpu` (pip) | ⚠️ Không có cp313 wheel trên PyPI | Dùng conda hoặc thay bằng `qdrant` |
| `faiss-cpu` (conda) | ✅ v1.14.1 ok | `conda install -c pytorch -c conda-forge faiss-cpu=1.14.1` |
| `torch` | ✅ 2.12+ hỗ trợ 3.13 chính thức | `uv pip install torch` |
| `transformers` | ✅ Python 3.10+ | ok |
| `torchvision` | ✅ Python ≥3.10 | ok |
| `open_clip_torch` | ✅ | ok |
| `ultralytics` | ✅ | ok, thay thế mediapipe |
| `qdrant-client` | ✅ | ok |
| `gradio` | ✅ | ok |
| `wandb` | ✅ | ok |
| `dvc` | ✅ | ok |

---

## Setup môi trường

```bash
# Cài uv (nếu chưa có)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Tạo project với Python 3.13
uv init outfitmatch
cd outfitmatch
uv python pin 3.13

# Hoặc nếu dùng conda (bắt buộc nếu cần faiss-gpu)
conda create -n outfitmatch python=3.13
conda activate outfitmatch
```

---

## Core dependencies

### Deep Learning

```toml
# pyproject.toml
[project]
requires-python = ">=3.13"
dependencies = [
    # PyTorch ecosystem — hỗ trợ 3.13 từ 2.6+
    "torch>=2.12",
    "torchvision>=0.26",
    "torchaudio>=2.12",          # nếu cần audio (optional)

    # Transformers / HuggingFace
    "transformers>=4.52",
    "open-clip-torch>=2.26",     # CLIP + SigLIP variants
    "sentence-transformers>=3.3",
    "datasets>=3.2",
    "huggingface-hub>=0.30",
    "safetensors>=0.5",
    "accelerate>=1.4",           # multi-GPU, mixed precision

    # LoRA / PEFT cho fine-tuning
    "peft>=0.14",
]
```

```bash
# Install
uv pip install torch torchvision
uv pip install transformers open-clip-torch sentence-transformers
uv pip install datasets huggingface-hub safetensors accelerate peft
```

### Computer Vision — KHÔNG dùng mediapipe

```toml
# Body keypoints: ultralytics thay thế mediapipe
"ultralytics>=8.3",          # YOLOv8-pose, YOLOv11-pose
"opencv-python>=4.11",
"Pillow>=11.0",
"timm>=1.0",                 # vision backbones (ViT, ResNet, etc.)
"einops>=0.8",               # tensor ops dùng trong transformers
```

```bash
uv pip install ultralytics opencv-python Pillow timm einops
```

**Lý do thay mediapipe → ultralytics:**
- YOLOv8-pose/YOLOv11-pose cho 17-keypoint body detection.
- Cùng output format (keypoints 2D), accuracy tương đương hoặc tốt hơn.
- Maintained tích cực, hỗ trợ Python 3.13 đầy đủ.
- Đã có clothing detection (YOLO object detection) trong cùng lib → tiết kiệm dependency.

```python
# Dùng thế này thay mediapipe
from ultralytics import YOLO

model = YOLO("yolov8n-pose.pt")
results = model("user_photo.jpg")
keypoints = results[0].keypoints.xy  # [N, 17, 2]

# Extract shoulder, waist, hip từ keypoints chuẩn COCO-17
# 5=left_shoulder, 6=right_shoulder, 11=left_hip, 12=right_hip
```

### Vector Search / Retrieval

```bash
# Option A: Qdrant (khuyến nghị cho Python 3.13, không cần conda)
uv pip install qdrant-client>=1.12

# Option B: FAISS qua conda (nếu team đang dùng conda env)
conda install -c pytorch -c conda-forge faiss-cpu=1.14.1
# hoặc GPU
conda install -c pytorch -c nvidia -c conda-forge faiss-gpu=1.14.1

# Option C: usearch (pure-Python-friendly, nhẹ hơn)
uv pip install usearch>=2.15    # ANN search, tương thích 3.13

# Option D: Annoy (nhẹ, đủ cho prototype)
uv pip install annoy>=1.17
```

**Khuyến nghị cho dự án này:**
- Phase 1 (MVP): `usearch` hoặc `qdrant-client` + Qdrant chạy Docker — không cần conda, không headache 3.13.
- Phase 2 (production): Qdrant Cloud hoặc Milvus.

```bash
# Chạy Qdrant local qua Docker (không phụ thuộc Python version)
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage \
    qdrant/qdrant
```

### Inference API & Serving

```toml
"fastapi>=0.115",
"uvicorn[standard]>=0.32",
"pydantic>=2.10",
"httpx>=0.28",               # async HTTP client
"python-multipart>=0.0.20",  # file upload
"slowapi>=0.1",              # rate limiting
```

```bash
uv pip install "fastapi[standard]" uvicorn pydantic httpx python-multipart slowapi
```

### Demo UI (Phase 1)

```toml
"gradio>=5.9",    # Python 3.13 ok từ gradio 4+
```

```bash
uv pip install gradio
```

### Data & Preprocessing

```toml
"numpy>=2.1",             # NumPy 2.x, Python 3.13 ok
"pandas>=2.2",
"scikit-learn>=1.6",
"scipy>=1.14",
"albumentations>=2.0",    # image augmentation
"pyarrow>=18.0",          # parquet, HF datasets backend
"tqdm>=4.67",
"rich>=13.9",             # CLI output đẹp
"typer>=0.15",            # CLI tools
```

```bash
uv pip install numpy pandas scikit-learn scipy albumentations pyarrow tqdm rich typer
```

### Weak Supervision (Occasion labeling)

```toml
"google-generativeai>=0.8",   # Gemini API
"openai>=1.57",               # GPT-4o-mini backup
"anthropic>=0.42",            # Claude API (optional)
"tenacity>=9.0",              # retry logic cho API calls
"diskcache>=5.6",             # cache API responses, tiết kiệm quota
```

```bash
uv pip install google-generativeai openai tenacity diskcache
```

### Experiment Tracking & MLOps

```toml
"wandb>=0.19",          # experiment tracking
"dvc[s3]>=3.56",        # data versioning
"mlflow>=2.18",         # alternative hoặc kết hợp
```

```bash
uv pip install wandb "dvc[s3]" mlflow
```

### Tooling (dev)

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.8",          # linter + formatter (thay black + flake8 + isort)
    "mypy>=1.13",
    "pre-commit>=4.0",
    "ipykernel>=6.29",
    "jupyter>=1.1",
]
```

```bash
uv pip install --group dev pytest pytest-asyncio pytest-cov ruff mypy pre-commit ipykernel jupyter
```

---

## File cấu hình đầy đủ

### `pyproject.toml`

```toml
[project]
name = "outfitmatch"
version = "0.1.0"
description = "Body & Occasion-Aware Fashion Recommendation"
requires-python = ">=3.13"

dependencies = [
    # Core DL
    "torch>=2.12",
    "torchvision>=0.26",
    "transformers>=4.52",
    "open-clip-torch>=2.26",
    "sentence-transformers>=3.3",
    "datasets>=3.2",
    "huggingface-hub>=0.30",
    "safetensors>=0.5",
    "accelerate>=1.4",
    "peft>=0.14",
    # Vision
    "ultralytics>=8.3",
    "opencv-python>=4.11",
    "Pillow>=11.0",
    "timm>=1.0",
    "einops>=0.8",
    # Retrieval
    "qdrant-client>=1.12",
    "usearch>=2.15",
    # API
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.10",
    "httpx>=0.28",
    "python-multipart>=0.0.20",
    # Data
    "numpy>=2.1",
    "pandas>=2.2",
    "scikit-learn>=1.6",
    "scipy>=1.14",
    "albumentations>=2.0",
    "pyarrow>=18.0",
    "tqdm>=4.67",
    "rich>=13.9",
    "typer>=0.15",
    # Weak supervision
    "google-generativeai>=0.8",
    "openai>=1.57",
    "tenacity>=9.0",
    "diskcache>=5.6",
    # MLOps
    "wandb>=0.19",
    "dvc[s3]>=3.56",
    # UI
    "gradio>=5.9",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
    "ipykernel>=6.29",
]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.13"
strict = false
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### `.python-version`

```
3.13
```

### `Makefile` (shortcuts)

```makefile
.PHONY: install dev-install test lint demo clean

install:
	uv sync

dev-install:
	uv sync --group dev
	pre-commit install

test:
	uv run pytest tests/ --cov=src --cov-report=term-missing -v

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

demo:
	uv run python src/ui/gradio_app.py

api:
	uv run uvicorn src.api.main:app --reload --port 8000

qdrant-up:
	docker compose up qdrant -d

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
```

### `docker-compose.yml` (Qdrant thay FAISS)

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      QDRANT__SERVICE__GRPC_PORT: "6334"

volumes:
  qdrant_storage:
```

---

## Phase 2 additions (tuần 11+)

Chỉ thêm khi cần, không install sớm:

```toml
# Generative / Try-On (Phase 2)
"diffusers>=0.31",          # Stable Diffusion, FLUX
"controlnet-aux>=0.0.9",    # ControlNet preprocessors (canny, depth)
"replicate>=1.0",           # Replicate API (SD, IDM-VTON)
"modal>=0.65",              # Modal serverless GPU

# Production serving
"celery[redis]>=5.4",       # async task queue
"redis>=5.2",               # broker + cache
"prometheus-client>=0.21",  # metrics
"sentry-sdk[fastapi]>=2.19",

# Auth
"python-jose[cryptography]>=3.3",
"passlib[bcrypt]>=1.7",

# DB
"sqlalchemy>=2.0",
"alembic>=1.14",
"asyncpg>=0.30",            # async postgres
```

---

## Quick install (từ scratch)

```bash
# 1. Cài uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone repo + setup
git clone <repo>
cd outfitmatch
uv sync --group dev

# 3. Start Qdrant
docker compose up qdrant -d

# 4. Chạy demo
make demo

# 5. Kiểm tra môi trường
uv run python -c "
import torch, transformers, ultralytics, qdrant_client, gradio
print(f'torch: {torch.__version__}')
print(f'transformers: {transformers.__version__}')
print(f'ultralytics: {ultralytics.__version__}')
print(f'CUDA: {torch.cuda.is_available()}')
"
```

---

## Thư viện không dùng và lý do

| Package | Lý do bỏ |
|---|---|
| `mediapipe` | Không có cp313 wheel, không maintained tốt |
| `faiss-cpu` (pip) | Không có cp313 wheel; thay bằng qdrant + usearch |
| `black`, `flake8`, `isort` | Thay bằng `ruff` (nhanh hơn 10x, gộp tất cả) |
| `flask` | Thay bằng FastAPI (async-native, Pydantic v2) |
| `tensorflow`, `keras` | Không cần, PyTorch đủ |
| `smplx`, `pytorch3d` | Phase 2+ nếu cần SMPL; Phase 1 dùng YOLO-pose |
| `streamlit` | Thay bằng Gradio (tốt hơn cho ML demo) |
