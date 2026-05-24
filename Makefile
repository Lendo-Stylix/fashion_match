.PHONY: install test test-fast lint format demo qdrant-up qdrant-down clean

install:
	uv sync --group dev
	pre-commit install

test:
	uv run pytest tests -v --cov=src/outfitmatch --cov-report=term-missing

test-fast:
	uv run pytest tests -v -x --no-cov

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

qdrant-up:
	docker compose up qdrant -d

qdrant-down:
	docker compose down

demo: qdrant-up
	uv run python src/outfitmatch/ui/gradio_app.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
