ветка:    worktree-agent-a14d942d8043de3af
сделал:   is_configured стал @abstractmethod в BaseLlmProvider, TracingLlmProvider.is_configured() явно возвращает self._inner.is_configured(), добавлен tests/test_llm_provider_contract.py (5 тестов); закоммичено.
не смог:  —
проверка: uv run mypy src/astra/llm && uv run pytest -q tests/test_llm_provider_contract.py

подробности: база после reset — ef1bb9e, f29f347, df5f88f. → Success: no issues found in 44 source files; 5 passed.
Отрицательный контроль: убрал is_configured из TracingLlmProvider (grep -c = 0; первая попытка sed на macOS не применилась, grep это показал) → 3 теста красные; вернул, grep = 2, зелёные.
Тест подкласса без метода — `# type: ignore[abstract]` с кодом. В base.py удалён неиспользуемый импорт Callable.
