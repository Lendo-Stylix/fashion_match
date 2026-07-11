.PHONY: install test test-fast lint format demo qdrant-up qdrant-down clean bench-fashion setup-models bench-rl bench-graph

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
# Reproducible fashion-knowledge/logic regression guard (no GPU).
bench-fashion:
	uv run python -m scripts.stylist.run_fashion_benchmark --mock
# Pull 4 base models + 4 LoRA adapters to D:/Models (off C:)
setup-models:
	uv run python scripts/setup_models.py --base --adapters

bench-graph:
	uv run python -m scripts.data.kb.eval_graph --seeds 50 --output-csv docs/experiments/eval_graph_benchmark_run.csv

bench-rl:
	uv run python -m scripts.stylist.train_grpo_kaggle --dry-run --canonical
