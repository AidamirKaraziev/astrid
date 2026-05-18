# GeoNames — справочник населённых пунктов РФ

Бесплатные данные: https://www.geonames.org/ (лицензия CC BY 4.0).

## Установка

```bash
cd data/geonames
curl -LO https://download.geonames.org/export/dump/RU.zip
unzip RU.zip
curl -LO https://download.geonames.org/export/dump/admin1CodesASCII.txt
cd ../..
uv run alembic upgrade head
uv run python scripts/import_geonames_ru.py
```

После импорта в БД будет ~200k городов, посёлков и деревень России.

**Язык:** в UI и поиске используются **русские** названия из поля `alternatenames` GeoNames
(кириллица). Латинское имя тоже индексируется — найдётся и по «Moscow», и по «Москва».

Повторный импорт (после обновления скрипта):

```bash
uv run python scripts/import_geonames_ru.py
```
