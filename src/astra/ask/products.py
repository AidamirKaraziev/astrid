"""Реестр продуктов раздела «Спроси Астрид».

Один вопрос = одна запись здесь. Хендлер, сервис и worker не знают ни про
партнёров, ни про детей — они работают через этот реестр, поэтому новый вопрос
добавляется записью, а не правкой пайплайна.

У каждого продукта своя структура ответа: она проектируется под тему вопроса,
а не копируется у соседнего продукта.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from astra.ask import children as children_calc
from astra.ask import fated_partners as partners_calc
from astra.ask import card
from astra.ask.schemas import ChildrenResult, FatedPartnersResult
from astra.astro.schemas import FullNatalChart
from astra.llm.prompts.ask import children as children_prompt
from astra.llm.prompts.ask import fated_partners as partners_prompt

QUESTION_FATED_COUNT = "love_fated_count"
QUESTION_CHILDREN = "love_kids"


@dataclass(frozen=True, slots=True)
class AskProduct:
    """Всё, что отличает один вопрос раздела от другого."""

    key: str
    # Расчёт: карта + дата рождения + ответ человека на калибрующий вопрос
    compute: Callable[[FullNatalChart, date, bool, date | None], BaseModel]
    result_model: type[BaseModel]
    methodology_version: int
    # Промпт-модуль: SYSTEM_PROMPT, build_user_message, parse, validate,
    # render_answer, card_caption
    prompt: ModuleType
    render_card: Callable[[Any], bytes] | None
    # Калибрующий вопрос перед покупкой: то, что нельзя посчитать по карте
    calibration_text: str
    calibration_yes: str
    calibration_no: str
    # Ключ, под которым ответ ложится в ask_readings.context
    calibration_field: str
    invoice_title: str
    invoice_description: str
    teaser: str
    validate_expected: Callable[[BaseModel], int]


def _compute_partners(
    chart: FullNatalChart,
    birth_date: date,
    calibration: bool,
    today: date | None,
) -> FatedPartnersResult:
    return partners_calc.compute_fated_partners(
        chart,
        birth_date=birth_date,
        in_relationship=calibration,
        today=today,
    )


def _compute_children(
    chart: FullNatalChart,
    birth_date: date,
    calibration: bool,
    today: date | None,
) -> ChildrenResult:
    return children_calc.compute_children_theme(
        chart,
        birth_date=birth_date,
        has_children=calibration,
        today=today,
    )


PRODUCTS: dict[str, AskProduct] = {
    QUESTION_FATED_COUNT: AskProduct(
        key=QUESTION_FATED_COUNT,
        compute=_compute_partners,
        result_model=FatedPartnersResult,
        methodology_version=partners_calc.METHODOLOGY_VERSION,
        prompt=partners_prompt,
        render_card=card.render_fated_partners_card,
        calibration_text=(
            "Один вопрос перед ответом — от него зависит, как читать твою карту.\n\n"
            "<b>Сейчас ты в отношениях?</b>\n\n"
            "<i>Сколько их уже было — не спрашиваю. Это я и посчитаю.</i>"
        ),
        calibration_yes="Сейчас в отношениях",
        calibration_no="Сейчас свободна/свободен",
        calibration_field="in_relationship",
        invoice_title="Сколько судьбоносных партнёров",
        invoice_description=(
            "Разбор по твоей натальной карте: сколько судьбоносных союзов показывает "
            "карта, сколько уже было и сколько впереди, какими они будут и как их узнать."
        ),
        teaser=(
            "Смотрю твой седьмой дом, его управителя и Венеру — считаю, "
            "сколько по-настоящему поворотных историй в твоей карте ✨"
        ),
        validate_expected=lambda result: result.total,
    ),
    QUESTION_CHILDREN: AskProduct(
        key=QUESTION_CHILDREN,
        compute=_compute_children,
        result_model=ChildrenResult,
        methodology_version=children_calc.METHODOLOGY_VERSION,
        prompt=children_prompt,
        render_card=card.render_children_card,
        calibration_text=(
            "Один вопрос перед ответом — от него зависит, как читать твою карту.\n\n"
            "<b>У тебя уже есть дети?</b>"
        ),
        calibration_yes="Да, есть",
        calibration_no="Пока нет",
        calibration_field="has_children",
        invoice_title="Будут ли у меня дети",
        invoice_description=(
            "Разбор по твоей натальной карте: какой у тебя сценарий темы детей, "
            "сколько показывает карта, когда открываются лучшие окна и что для "
            "тебя значит родительство."
        ),
        teaser=(
            "Смотрю твой пятый дом, Луну и Юпитер — ищу, как в твоей карте "
            "устроена тема детей и когда её лучшие окна ✨"
        ),
        validate_expected=lambda result: len(result.windows),
    ),
}


def get_product(question_key: str) -> AskProduct | None:
    return PRODUCTS.get(question_key)


def is_ready(question_key: str) -> bool:
    """Готов ли вопрос к покупке (иначе показываем заглушку «скоро»)."""
    return question_key in PRODUCTS
