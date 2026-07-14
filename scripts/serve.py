"""Launch FastAPI server for OutfitMatch.

Usage (from project root):
    .venv/Scripts/python.exe scripts/serve.py
    .venv/Scripts/python.exe scripts/serve.py --reload --port 8001

NOTE: ALWAYS use .venv/Scripts/python.exe directly, NOT uv run.
uv run re-syncs torch to CPU-only, breaking GPU model loading.
"""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Start OutfitMatch FastAPI server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    # Ensure HF caches off C: drive
    models_base = os.environ.get("OUTFITMATCH_MODELS_BASE", "D:/Models")
    os.environ.setdefault("HF_HOME", f"{models_base}/hf_home")
    os.environ.setdefault("HF_HUB_CACHE", f"{models_base}/hf_hub")

    import uvicorn

    uvicorn.run(
        "outfitmatch.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
