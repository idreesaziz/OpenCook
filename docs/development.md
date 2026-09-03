# Development

Python 3.11+ and Node 20+ are supported. `uv.lock` and `web/package-lock.json` pin environments. Run backend tests with `uv run pytest`; lint/type-check with `uv run ruff check .` and `uv run mypy`. Run frontend checks from `web`.

No telemetry or analytics exist. Reaction search is local. By default, result naming sends exact Standard InChIKeys (not connection tables) to PubChem PUG REST and caches responses in `data/cache`. Set `OPENCOOK_NAME_PROVIDER=disabled` for fully offline/private operation. Other network access occurs only for explicit dataset downloads or dependency installation.
