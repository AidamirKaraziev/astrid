ветка:    worktree-agent-af4601a72b5554e7f
сделал:   в tests/conftest.py убран setdefault для DATABASE_URL с зашитым портом 5432 (DSN берётся из окружения или .env, иначе из дефолта Settings); коммит в ветке. С DATABASE_URL на порту 15444 полный прогон даёт 1419 passed, 0 скипов. Без DATABASE_URL скипы с подсказкой «подними инфраструктуру…» остаются (1146 passed, 273 skipped). Логику live_infra и CI-падение не трогал.
не смог:  —
проверка: DATABASE_URL="postgresql+asyncpg://astra:astra@localhost:15444/astra" uv run pytest -q -rs 2>&1 | grep -c "Postgres недоступен" → 0
предположение: uv sync --all-extras менял только .venv дорожки, файлы в git не затронуты.
