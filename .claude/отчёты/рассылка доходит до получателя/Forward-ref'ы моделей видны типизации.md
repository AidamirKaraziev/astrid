ветка:    worktree-agent-a81b8453ad289f305
сделал:   в users/referrals/compatibility/astro models.py добавлены блоки if TYPE_CHECKING с импортами моделей, убраны ставшие ненужными noqa F821; в users/models.py блок включает NatalReport и Place; ruff чистый, закоммичено.
не смог:  —
проверка: uv run mypy src/astra 2>&1 | grep -c "name-defined" → 1 (остался только workers/handlers.py:473); uv run pytest -q → 1419 passed с DATABASE_URL на :15444; без него 1146 passed, 273 skipped
предположение: первый прогон с живым Postgres дал 5 failed + 1 error (test_registration_funnel_e2e, ForeignKeyViolation на profiles), повторный без правок зелёный — похоже на гонку соседних дорожек за общую БД, не на изменения.
