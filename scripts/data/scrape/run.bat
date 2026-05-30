@echo off
REM Convenience wrapper — VN catalog scraper
REM Usage:
REM   scripts\data\scrape\run.bat                  → all active stores
REM   scripts\data\scrape\run.bat --store yody_vn  → single store
REM   scripts\data\scrape\run.bat --limit 30 --no-images  → smoke test
REM
REM Requires `uv` on PATH and project dependencies installed via `uv sync`.

setlocal
cd /d "%~dp0..\..\.."
uv run python -m scripts.data.scrape.run %*
endlocal
