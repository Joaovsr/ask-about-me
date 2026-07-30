PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

-include .env
export

AAM_DATABASE_URL ?= postgresql+psycopg://ask_about_me:ask_about_me@localhost:5432/ask_about_me
AAM_TEST_DATABASE_URL ?= postgresql+psycopg://ask_about_me:ask_about_me@localhost:5433/ask_about_me_test

.PHONY: setup lock db-up db-down db-reset migrate seed-dev reindex-openai inspect-retrieval evaluate-retrieval dev test lint typecheck format check

setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r requirements.lock
	$(BIN)/pip install --no-build-isolation --no-deps -e .

lock:
	$(BIN)/pip-compile pyproject.toml --allow-unsafe --extra dev --strip-extras --output-file requirements.lock

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose --profile test down

db-reset:
	docker compose --profile test down -v

migrate: db-up
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/alembic upgrade head

seed-dev: migrate
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/python -m ask_about_me.seed

reindex-openai: migrate
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/python -m ask_about_me.reindex

inspect-retrieval:
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/python -m ask_about_me.inspect_retrieval "$(QUESTION)" $(ARGS)

evaluate-retrieval:
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/python -m ask_about_me.retrieval_evaluation $(ARGS)

dev: migrate
	AAM_DATABASE_URL="$(AAM_DATABASE_URL)" $(BIN)/uvicorn ask_about_me.app:app --reload

test:
	AAM_TEST_DATABASE_URL="$(AAM_TEST_DATABASE_URL)" bash scripts/test.sh

lint:
	$(BIN)/ruff check .

typecheck:
	$(BIN)/mypy

format:
	$(BIN)/ruff format .

check: lint typecheck test
