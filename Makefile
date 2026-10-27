export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: install backend frontend build start test

install:
	cd backend && uv venv --allow-existing && uv pip install -e ".[dev]"
	npm install --prefix frontend

# Dev: API on :8500 (auto reload), UI on :5180 with proxy to the API
backend:
	cd backend && .venv/bin/uvicorn smartpost.main:app --host 0.0.0.0 --port 8500 --reload --timeout-graceful-shutdown 3

frontend:
	npm run dev --prefix frontend

build:
	npm run build --prefix frontend

# Daily use: build the UI once, then one server on :8500 serves everything (also for the iPhone)
start: build
	cd backend && .venv/bin/python -m smartpost

test:
	cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests
