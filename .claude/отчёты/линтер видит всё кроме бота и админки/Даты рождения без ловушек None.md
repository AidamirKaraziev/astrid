ветка:    worktree-agent-abeec8736589bb321
сделал:   PATCH профиля с birth_time без даты рождения теперь 422 (раньше 500; тест красный без правки, зелёный с ней); mypy по astro/places/users чист. После возврата приёмкой: дорожка перебазирована на 154e49a, орбы аспектов — одна типизированная таблица, `_MAX_ORBS` выводится из неё; снят мёртвый ignore в synastry.py:132.
не смог:  —
проверка: uv run mypy src/astra/astro src/astra/places src/astra/users && DATABASE_URL="postgresql+asyncpg://astra:astra@localhost:15444/astra" uv run pytest -q tests/test_profile_without_birth_date_typing.py

подробности: mypy Success, 38 source files; pytest 3 passed; полный pytest 1445 passed; `uv run mypy src/astra/astro --warn-unused-ignores` → Success.
Баг: users/routers.py:40 wall_clock_at(None, …) → TypeError → 500; теперь 422 «Укажите дату рождения вместе со временем рождения».
Защита (не баг, gate не пропускает None): BirthDateMissingError и require_birth_date() в astro/birth_time.py — calculator.py:29, simple.py:43, synastry.py:178.
Аннотации: birth_time.py:89, natal_aspects.py:79, places/crud.py `_similarity`, geonames_import.py RawPlace.timezone, name-defined в users/models.py и astro/models.py через TYPE_CHECKING.
Коммиты: 76b438b, 9ea158e. Заглушек не добавлено.
