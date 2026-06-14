# SOTA нейросети — отчёт для Astra

PDF для обсуждения с коллегой. Фокус: **бесплатные API** (не UI), качество генерации, лимиты.

## Файлы

| Файл | Описание |
|------|----------|
| `Astra-SOTA-нейросети-отчет-2026-06-13.pdf` | Полный отчёт: рейтинг, матрица качества, карточки моделей |

## Пересборка PDF

```bash
uv run --with fpdf2 python scripts/generate_sota_report_pdf.py
```

## Связанные заметки

- Vault: `astra-vault/knowledge/` (при сохранении сессии)
- Текущий LLM: `gemma4:e2b` на deadtiger через Ollama
