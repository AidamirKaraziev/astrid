ветка:    worktree-agent-a836c97df677f42d0
сделал:   в natal_report_service.py:266 report.user_id заменён на report.owner_user_id; в тесте сборки PDF вместо MagicMock стоит настоящий NatalReport (не в БД), тест проверяет, что файл PDF создан (>10 КБ), статус стал READY и pdf_path заполнен; мок report в этом тесте убран.
не смог:  —
проверка: uv run pytest -q tests/test_natal_pipeline.py → 9 passed, 5 warnings in 37.80s
предположение: с возвращённым report.user_id этот тест падает (1 failed, 8 passed), то есть теперь баг он ловит. Проверка запускалась после `uv sync --extra dev`: в свежем окружении pytest не было, pyproject не менял. Для нетронутого теста с referral пришлось патчить astra.referrals.crud.get_or_create_referral_code, сессия остаётся AsyncMock.
