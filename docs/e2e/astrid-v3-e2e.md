# E2E Astrid v3 — результаты

**Дата прогона:** 2026-06-14  
**Окружение:** MacBook M4 Pro, Ollama local, `gemma4:e2b`  
**Скрипт:** `uv run python scripts/e2e_astrid_v3.py`

## Автоматический чеклист (Ollama)

| # | Сценарий | Дата | Архетип | Latency | Push | Статус |
|---|----------|------|---------|---------|------|--------|
| 1 | Aidamir, сегодня | 2026-06-14 | `avoided_truth` | 16.6s | 47 симв. | ✓ |
| 2 | Aidamir, завтра | 2026-06-15 | `listen_not_convince` | 19.9s | 47 симв. | ✓ |
| 3 | Aidamir, +2 дня | 2026-06-16 | `avoided_truth` | 16.4s | 38 симв. | ✓ |

**Итог:** 3/3 OK · **p50 latency:** 16.6s

### Проверки на каждый прогон

- [x] `validate_prediction_output` — ok
- [x] 3 блока (вопрос / прогноз / совет)
- [x] Без v2-эмодзи (`✨💡🔢🎨`)
- [x] Вопрос 15–65 симв. (push)
- [x] Имя в 1-м предложении body
- [x] Body 3–6 предложений, 15–180 слов
- [x] 1 предложение совета

### Pytest E2E

```bash
uv run pytest tests/test_astrid_v3_e2e.py -q
```

- [x] Чеклист на валидном output
- [x] Fail без имени → `missing_name`
- [x] Retry worker при `LlmGenerationError("missing_name")`

---

## Ручной чеклист TG (deadtiger) — pending

| # | Сценарий | Статус |
|---|----------|--------|
| 1 | Онбординг → «🔮 Предсказание» → v3 в чате | ☐ |
| 2 | Push iPhone: вопрос целиком | ☐ |
| 3 | Scheduler 09:00 | ☐ |
| 4 | Retry: «Почти готово ✨» → текст / ошибка | ☐ |

**Команды на deadtiger:**

```bash
# smoke (1 прогон)
uv run python scripts/smoke_astrid_v3.py

# полный E2E (3 даты + чеклист)
uv run python scripts/e2e_astrid_v3.py

# JSON-отчёт
uv run python scripts/e2e_astrid_v3.py --json
```

---

## Пороги latency (draft)

| Окружение | p50 (факт) | p95 (цель) |
|-----------|------------|------------|
| Mac M4 Pro | ~17s | — |
| deadtiger CPU | TBD | ≤ 180s |

Связано: [[2026-06-14 Astrid v3 вопрос дня gemma4 e2b]] · `spec/backlog.md` E2E-1
