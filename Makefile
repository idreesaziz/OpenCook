.PHONY: install test lint benchmark serve web
install:
	uv sync --extra dev
	cd web && npm ci
test:
	uv run pytest --basetemp .pytest-tmp
	cd web && npm test
lint:
	uv run ruff check .
	cd web && npm run lint
benchmark:
	uv run opencook benchmark --iterations 100 --json
serve:
	uv run opencook serve
web:
	cd web && npm run dev
