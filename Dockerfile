FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY opencook opencook
COPY data/fixtures data/fixtures
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uv", "run", "opencook", "serve", "--host", "0.0.0.0", "--port", "8000"]
