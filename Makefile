.PHONY: help install dev test lint format typecheck migrate run docker-up docker-down backup clean

PYTHON ?= python
VENV := .venv
BIN := $(VENV)/Scripts

ifeq ($(OS),Windows_NT)
	ACTIVATE := $(VENV)/Scripts/activate
else
	BIN := $(VENV)/bin
	ACTIVATE := $(VENV)/bin/activate
endif

help:
	@echo "trader — Makefile targets"
	@echo "  install    Run the interactive installer"
	@echo "  dev        Install dev dependencies"
	@echo "  test       Run unit tests"
	@echo "  test-all   Run all tests including integration + contract"
	@echo "  lint       Run ruff"
	@echo "  format     Auto-format with ruff"
	@echo "  typecheck  Run mypy"
	@echo "  migrate    Run alembic migrations"
	@echo "  run        Start the trader (python run.py)"
	@echo "  docker-up  Bring up optional Redis + Postgres via docker-compose"
	@echo "  docker-down Stop docker services"
	@echo "  backup     Nightly backup script"
	@echo "  clean      Remove caches and build artifacts"

install:
	$(PYTHON) install.py

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(BIN)/pytest tests/unit -v

test-all:
	$(BIN)/pytest tests -v

lint:
	$(BIN)/ruff check src tests

format:
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

typecheck:
	$(BIN)/mypy src

migrate:
	$(BIN)/alembic upgrade head

run:
	$(BIN)/python run.py

docker-up:
	docker compose up -d

docker-down:
	docker compose down

backup:
	$(BIN)/python scripts/backup.py

clean:
	@rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
