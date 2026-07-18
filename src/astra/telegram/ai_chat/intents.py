"""Схемы намерений AI-чата Astrid.

Это «инструменты», которые Astrid распознаёт в свободном тексте пользователя.
LLM возвращает JSON строго по `AstridReply` — а бот уже роутит `intent`
в существующие FSM-флоу (совместимость, натал, профиль, предсказание).

Ключевая идея: LLM не хранит состояние и ничего не «делает» сам — он только
превращает болтовню в структуру (slot filling) и говорит, куда идти дальше.
Истина о состоянии живёт в нашем коде (FSM + БД), как и раньше.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Куда пользователь хочет попасть. Совпадает с реальными продуктами Astra."""

    smalltalk = "smalltalk"                 # просто разговор / вопрос про астрологию
    daily_prediction = "daily_prediction"   # 🔮 Предсказание на сегодня
    compatibility = "compatibility"         # 💕 Совместимость
    natal = "natal"                         # 🌌 Разбор натала
    tarot = "tarot"                         # 🔮 Карты Таро (меню, если расклад не ясен)
    tarot_wish = "tarot_wish"               # 🌟 Таро: загадай желание (сбудется ли + срок)
    tarot_three_cards = "tarot_three_cards"  # 🃏 Таро: три карты
    tarot_relationship = "tarot_relationship"  # 💕 Таро: расклад на отношения
    edit_profile = "edit_profile"           # ✨ Обо мне (правка данных)
    invite = "invite"                       # 🎁 Пригласить друга


class BirthData(BaseModel):
    """Данные рождения, вытащенные из свободного текста (slot filling).

    Все поля опциональны: Astrid заполняет то, что смогла понять, и сама
    спрашивает недостающее. Формат намеренно строковый (ISO) — валидацию и
    парсинг в date/time делают наши существующие utils (`parse_birth_date`).
    """

    name: str | None = Field(None, description="Имя человека, о котором речь")
    gender: str | None = Field(None, description="'male' или 'female'")
    birth_date: str | None = Field(None, description="Дата рождения в ISO: YYYY-MM-DD")
    birth_time: str | None = Field(None, description="Время рождения HH:MM, если известно")
    birth_city: str | None = Field(None, description="Город рождения, как назвал пользователь")


class AstridReply(BaseModel):
    """Единый структурированный ответ Astrid на каждую реплику пользователя."""

    reply: str = Field(description="Что Astrid говорит пользователю, живым языком")
    intent: Intent = Field(description="Распознанное намерение")
    birth_data: BirthData | None = Field(
        None, description="Собранные данные рождения, если пользователь их упоминал"
    )
    missing: list[str] = Field(
        default_factory=list,
        description="Каких полей не хватает, чтобы запустить продукт (напр. ['birth_time'])",
    )
    ready_to_route: bool = Field(
        False,
        description="True, когда данных достаточно и можно передать управление реальному флоу",
    )
