.PHONY: install model-env test lint benchmark serve web
install:
	uv sync --extra dev
	cd web && npm ci
model-env:
	uv venv .model-venv --python 3.11
	uv pip install --python .model-venv/Scripts/python.exe retrochimera==1.2.0 pytorch-lightning==2.2.2 "torchmetrics<0.11" "scipy<1.12" pandas
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
