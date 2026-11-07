# Build context is the repo root so web/ can be served by the API.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY web/ /app/web/

RUN useradd --create-home app && mkdir -p /data/storage && chown -R app:app /app /data
USER app
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
