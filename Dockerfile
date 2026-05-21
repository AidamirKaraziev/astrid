# Сборка без apt: kerykeion опционален (extra astro). Полный натал — см. Dockerfile.astro
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

ARG UV_EXTRAS=
RUN uv sync --frozen --no-dev ${UV_EXTRAS}

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "astra.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
