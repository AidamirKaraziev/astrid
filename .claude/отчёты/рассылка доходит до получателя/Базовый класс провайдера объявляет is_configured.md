ветка:    worktree-agent-a6c0f202861b5d465
сделал:   в BaseLlmProvider добавлена аннотация is_configured: Callable[[], bool] без реализации; пять провайдеров не тронуты
не смог:  не сделал методом — оба варианта сломали бы TracingLlmProvider (он наследует базу и делегирует is_configured внутреннему провайдеру через __getattr__). Абстрактный метод не дал бы создать обёртку, метод с реализацией по умолчанию перекрыл бы делегирование. Цена аннотации: забывчивый новый провайдер не будет поймлен ни mypy, ни ABC. Чтобы ловилось, нужно сначала определить is_configured в TracingLlmProvider через self._inner — отдельная задача.
проверка: uv run mypy src/astra/services src/astra/natal_report 2>&1 | grep -c "is_configured" → 0, затем uv run pytest -q → 1419 passed
предположение: 17 ошибок типа object в llm/*_generate.py и api/gemini.py были скрыты той же заглушкой и после её снятия потребуют отдельной задачи.
