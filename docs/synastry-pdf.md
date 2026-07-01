# PDF-отчёты синастрии

Mobile-first PDF для чтения с телефона: космический дизайн, flow-layout, CTA на Telegram-бота.

## Структура модуля

```
src/astra/reports/synastry/
├── __init__.py      # generate_synastry_pdf(), публичные типы
├── types.py         # SynastryReportData и вложенные dataclass
├── theme.py         # цвета, размеры, звёздное поле, легенда аспектов
├── fonts.py         # Cormorant Garamond (bundled TTF, кириллица)
├── assets/fonts/    # CormorantGaramond Regular + Bold, OFL, едут в wheel
├── bot_link.py      # resolve_telegram_bot_url()
├── sample_data.py   # демо: Айдамир × Анжела
├── builder.py       # SynastryPdfBuilder — отрисовка страниц
```

Шрифт: **Cormorant Garamond** в `src/astra/reports/synastry/assets/fonts/` — bundled OFL, работает на macOS, Linux, CI и Docker без системных зависимостей. Тонкий сериф под тёмный космический фон и золотые акценты.

## Зависимости

```bash
uv sync --extra pdf
```

`reportlab` — optional extra `pdf` в `pyproject.toml`.

## Быстрый старт

```bash
uv run --extra pdf python scripts/generate_synastry_pdf.py
```

Выход по умолчанию: `docs/output/synastry_aidamir_angela.pdf`.

Свой путь и бот:

```bash
uv run --extra pdf python scripts/generate_synastry_pdf.py \
  -o docs/output/my_synastry.pdf \
  --bot-username astrology_aid_dev_bot
```

## Программный API

```python
from pathlib import Path

from astra.reports.synastry import (
    SynastryReportData,
    build_sample_report,
    generate_synastry_pdf,
)

report = build_sample_report()  # или свой SynastryReportData
generate_synastry_pdf(Path("docs/output/synastry.pdf"), report)
```

### Модель данных

| Поле | Описание |
|------|----------|
| `person_a`, `person_b` | Имя, подзаголовок (дата/город), акцентный цвет, планеты |
| `tldr` | Краткий итог на 2–3 предложения |
| `natal_insight` | Инсайт после натальных карт |
| `metrics` | Прогресс-бары (0–1): притяжение, контакт и т.д. |
| `strong_aspects` | Главные аспекты (орб &lt; 2°) |
| `working_aspects` | Рабочие аспекты (орб 2–6°) |
| `zone_blocks` | Итог по зонам: что работает / рост / опора |
| `conclusion_quote`, `conclusion_tip` | Финальный блок «Вывод» |
| `cta_text` | Текст кнопки Telegram (по умолчанию «Забери еще одно предсказание») |

CTA-ссылка: `https://t.me/{TELEGRAM_BOT_USERNAME}` из `.env` или `astra.core.config`.

## Страницы PDF

1. Обложка — аватарки пары, «Синастрия»
2. Краткий итог + метрики
3. Натальные данные обоих + инсайт
4. Легенда аспектов + главные аспекты (flow, несколько страниц при необходимости)
5. Рабочие аспекты
6. Итог по зонам
7. Вывод — золотое свечение + кнопка в бота

Размер страницы: **390×844** (портрет телефона).

## Тесты

```bash
uv run --extra pdf pytest tests/test_synastry_pdf.py -v
```

## Дальше

- Подключить расчёт синастрии из Kerykeion → маппер в `SynastryReportData`
- LLM-тексты аспектов через `astra.llm`
- Корневой `synastry_pdf.py` — тонкая обёртка для обратной совместимости
