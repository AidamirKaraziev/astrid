# =============================================================================
# Astra — образ приложения (API + worker)
#
# Targets:
#   dev     — зависимости для pytest (docker compose --profile test run test)
#   runtime — production-образ (сервисы api и worker)
#
# Порядок слоёв оптимизирован под кеш BuildKit: зависимости ставятся из
# uv.lock ДО копирования кода. Изменение src/ не инвалидирует слой с
# зависимостями — gcc и компиляция pyswisseph выполняются только при
# изменении uv.lock.
# =============================================================================

FROM python:3.12-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

# --- Слой зависимостей: только манифесты ---
# pyswisseph (зависимость kerykeion) для Python 3.12 есть только как sdist —
# нужен gcc. Слой кешируется, пока не меняется uv.lock.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && uv sync --frozen --no-dev --no-install-project \
    && apt-get purge -y gcc g++ \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# --- Код приложения ---
COPY README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic

# PDF синастрии: PT Sans должен быть в репозитории (не скачивается при сборке)
RUN test -f src/astra/reports/synastry/assets/fonts/PTSans-Regular.ttf \
    && test -f src/astra/reports/synastry/assets/fonts/PTSans-Bold.ttf \
    || (echo "ERROR: PTSans-Regular.ttf / PTSans-Bold.ttf отсутствуют в src/astra/reports/synastry/assets/fonts/" >&2; exit 1)

# Доустановка самого пакета astra (зависимости уже стоят — это секунды)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# --- Тесты и CI в контейнере ---
FROM base AS dev

COPY tests ./tests

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-extras


# --- Production ---
FROM base AS runtime

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
    || exit 1

CMD ["uvicorn", "astra.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
