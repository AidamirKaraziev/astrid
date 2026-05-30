# =============================================================================
# Astra — образ приложения (API + worker)
#
# Targets:
#   dev     — зависимости для pytest (docker compose --profile test run test)
#   runtime — production-образ (сервисы api и worker)
# =============================================================================

FROM python:3.12-slim-bookworm AS base

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src


# --- Тесты и CI в контейнере ---
FROM base AS dev

COPY tests ./tests

RUN uv sync --frozen --all-extras


# --- Production ---
FROM base AS runtime

ARG UV_EXTRAS=
RUN uv sync --frozen --no-dev ${UV_EXTRAS}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
    || exit 1

CMD ["uvicorn", "astra.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
