# Lighthouse Development Makefile

.PHONY: help install install-dev clean test test-unit test-integration test-performance
.PHONY: lint format type-check pre-commit setup-dev start-api start-bridge
.PHONY: benchmark load-test clean-data docker-build docker-run

help:
	@echo "Lighthouse Development Commands:"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install         Install package in production mode"
	@echo "  install-dev     Install package with development dependencies"
	@echo "  setup-dev       Complete development environment setup"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test            Run all tests"
	@echo "  test-unit       Run unit tests only" 
	@echo "  test-integration Run integration tests only"
	@echo "  test-performance Run performance benchmarks"
	@echo "  test-validation  Run Phase 1 success criteria validation"
	@echo ""
	@echo "Code Quality Commands:"
	@echo "  lint            Run all linting checks"
	@echo "  format          Format code with black and isort"
	@echo "  type-check      Run mypy type checking"
	@echo "  pre-commit      Run pre-commit hooks"
	@echo ""
	@echo "Development Commands:"
	@echo "  start-api       Start Event Store API server"
	@echo "  start-bridge    Start Validation Bridge server"
	@echo "  benchmark       Run performance benchmarks"
	@echo "  load-test       Run load testing scenarios"
	@echo ""
	@echo "Utility Commands:"
	@echo "  clean           Clean up temporary files and data"
	@echo "  clean-data      Clean up development data directories"
	@echo "  docker-build    Build Docker development image"
	@echo "  docker-run      Run in Docker container"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,performance]"

setup-dev: install-dev
	pre-commit install
	mkdir -p data/events/.index data/snapshots/.metadata
	@echo "Development environment setup complete!"

test:
	pytest

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-performance:
	pytest tests/performance/ -v --benchmark-only

test-validation:
	pytest tests/validation/ -v

lint: format type-check
	@echo "All linting checks passed!"

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

pre-commit:
	pre-commit run --all-files

start-api:
	uvicorn lighthouse.event_store.api:app --host 0.0.0.0 --port 8080 --reload

start-bridge:
	python -m lighthouse.server

benchmark:
	python scripts/benchmark.py

load-test:
	python scripts/load_test.py

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .coverage .pytest_cache/ .mypy_cache/

clean-data:
	rm -rf data/events/* data/snapshots/* || true
	mkdir -p data/events/.index data/snapshots/.metadata

docker-build:
	docker build -t lighthouse-dev .

docker-run:
	docker run -it --rm -p 8080:8080 -v $(PWD):/workspace lighthouse-dev