ветка:    worktree-agent-ac4c87a45df93af9d
сделал:   в Makefile цель lint гоняет `uv run mypy src/astra --exclude 'src/astra/(telegram|admin)/'`, строка help про lint описывает новый охват; в [tool.mypy] добавлен warn_unused_ignores = true, комментарий над ним переписан; снят мёртвый `# type: ignore[arg-type]` в compatibility/crud.py:121; коммит 8ca0e0f
не смог:  —
проверка: make lint

подробности: база проверена — шесть коммитов поверх 154e49a. ruff «All checks passed!», mypy «Success: no issues found in 252 source files». Исключение флагом --exclude в Makefile. Новых ignore_errors, disable_error_code и type: ignore нет; существующие overrides не тронуты, warn_unused_ignores на них не ругается.
предположение: при follow_imports = "silent" модули telegram и admin анализируются как импортируемые, ошибки не печатаются; отдельно не проверял.
