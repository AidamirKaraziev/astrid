"""Реестр продуктов раздела «Спроси Астрид».

Один вопрос = одна запись здесь + два файла (расчёт и промпт). Хендлер, сервис
и worker не знают ни про партнёров, ни про детей — они работают через реестр.

**Продукты изолированы друг от друга.** Реестр хранит только пути к модулям и
подтягивает их по требованию: если модуль продукта удалён или в нём ошибка,
падает ровно этот вопрос (человек видит «скоро»), а остальные продолжают
работать и продаваться. Поэтому здесь нет импортов конкретных продуктов —
и добавлять их сюда нельзя, это вернёт связанность.

Контракт модуля расчёта:
    METHODOLOGY_VERSION: int
    RESULT_MODEL: type[BaseModel]
    compute(chart, *, birth_date, calibration, today=None) -> RESULT_MODEL
    render_card(result) -> bytes            # необязательно

Контракт модуля промпта:
    SYSTEM_PROMPT, TEMPERATURE, MAX_TOKENS
    build_user_message(result, *, user_name, gender) -> str
    parse(raw) -> answer | None
    validate(answer, expected) -> str | None
    expected_blocks(result) -> int
    render_answer(answer, result) -> str
    card_caption(result) -> str
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from types import ModuleType
from typing import Any

from astra.core.observability import get_logger

log = get_logger(__name__)

QUESTION_FATED_COUNT = "love_fated_count"
QUESTION_CHILDREN = "love_kids"

# Первый продукт писал ответ на калибрующий вопрос в отдельную колонку —
# у строк, созданных до миграции 020, поля `context` нет.
LEGACY_CALIBRATION_PRODUCT = QUESTION_FATED_COUNT


@dataclass(frozen=True, slots=True)
class AskProductSpec:
    """Описание продукта: пути к модулям и тексты вокруг покупки."""

    key: str
    calc_module: str
    prompt_module: str
    # Калибрующий вопрос: то, что нельзя посчитать по карте
    calibration_text: str
    calibration_yes: str
    calibration_no: str
    calibration_field: str  # ключ в ask_readings.context
    invoice_title: str
    invoice_description: str
    teaser: str


@dataclass(frozen=True, slots=True)
class AskProduct:
    """Загруженный продукт: спецификация + его модули."""

    spec: AskProductSpec
    calc: ModuleType
    prompt: ModuleType

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def methodology_version(self) -> int:
        return self.calc.METHODOLOGY_VERSION

    @property
    def result_model(self) -> type:
        return self.calc.RESULT_MODEL

    @property
    def render_card(self):  # noqa: ANN201 — Callable | None
        return getattr(self.calc, "render_card", None)

    @property
    def calibration_text(self) -> str:
        return self.spec.calibration_text

    @property
    def calibration_yes(self) -> str:
        return self.spec.calibration_yes

    @property
    def calibration_no(self) -> str:
        return self.spec.calibration_no

    @property
    def calibration_field(self) -> str:
        return self.spec.calibration_field

    @property
    def invoice_title(self) -> str:
        return self.spec.invoice_title

    @property
    def invoice_description(self) -> str:
        return self.spec.invoice_description

    @property
    def teaser(self) -> str:
        return self.spec.teaser

    def compute(
        self,
        chart: Any,
        birth_date: date,
        calibration: bool,
        today: date | None = None,
    ) -> Any:
        return self.calc.compute(
            chart,
            birth_date=birth_date,
            calibration=calibration,
            today=today,
        )

    def validate_expected(self, result: Any) -> int:
        """Сколько блоков ответа ждём от модели — считает сам продукт."""
        return self.prompt.expected_blocks(result)


SPECS: dict[str, AskProductSpec] = {
    QUESTION_FATED_COUNT: AskProductSpec(
        key=QUESTION_FATED_COUNT,
        calc_module="astra.ask.fated_partners",
        prompt_module="astra.llm.prompts.ask.fated_partners",
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
    ),
    QUESTION_CHILDREN: AskProductSpec(
        key=QUESTION_CHILDREN,
        calc_module="astra.ask.children",
        prompt_module="astra.llm.prompts.ask.children",
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
    ),
}


@lru_cache(maxsize=None)
def _load(question_key: str) -> AskProduct | None:
    """Подтянуть модули продукта. None — продукт сломан или удалён."""
    spec = SPECS.get(question_key)
    if spec is None:
        return None
    try:
        calc = importlib.import_module(spec.calc_module)
        prompt = importlib.import_module(spec.prompt_module)
    except Exception as exc:
        # Соседние продукты от этого не страдают: вопрос просто показывает «скоро».
        log.error(
            "ask.product_unavailable",
            question_key=question_key,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None
    return AskProduct(spec=spec, calc=calc, prompt=prompt)


def get_product(question_key: str) -> AskProduct | None:
    return _load(question_key)


def is_ready(question_key: str) -> bool:
    """Готов ли вопрос к покупке (иначе показываем заглушку «скоро»)."""
    return get_product(question_key) is not None
