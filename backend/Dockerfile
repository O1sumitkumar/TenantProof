# Build context is the repo root so web/ can be served by the API.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
# PyPI lookups inside the build can fail now and then ("dns error ... Try again"); retry more
# than uv's default of 3, with a longer wait per request, instead of failing the whole build.
ENV UV_HTTP_RETRIES=10 UV_HTTP_TIMEOUT=60

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY web/ /app/web/

RUN useradd --create-home app && mkdir -p /data/storage && chown -R app:app /app /data
USER app
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
