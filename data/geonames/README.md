# GeoNames — справочник населённых пунктов РФ

Бесплатные данные: https://www.geonames.org/ (лицензия CC BY 4.0).

## Автозагрузка

При старте API, если таблица `places` пуста, приложение само скачивает дамп и импортирует данные.
Отключить: `GEONAMES_AUTO_IMPORT=false`.

## Ручной переимпорт

Скрипт очищает `places` и загружает заново (данные скачиваются автоматически, если их нет):

```bash
uv run alembic upgrade head
uv run python scripts/import_geonames_ru.py
```

После импорта в БД будет ~200k городов, посёлков и деревень России.

**Язык:** в UI и поиске используются **русские** названия из поля `alternatenames` GeoNames
(кириллица). Латинское имя тоже индексируется — найдётся и по «Moscow», и по «Москва».

## Ручная установка файлов (опционально)

```bash
cd data/geonames
curl -LO https://download.geonames.org/export/dump/RU.zip
unzip RU.zip
curl -LO https://download.geonames.org/export/dump/admin1CodesASCII.txt
```
