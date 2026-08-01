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
    validate(answer, expected, result) -> str | None
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
QUESTION_KIDS_BOND = "love_kids_bond"
QUESTION_PARTNER_TRAITS = "love_partner_traits"
QUESTION_PAIN_LOOP = "love_pain_loop"

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
    # Продукт зовёт человека по имени: имя подставляет код, не модель.
    # Тизер такого продукта пишется как продолжение обращения, со строчной.
    address_by_name: bool = False


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

    def teaser_for(self, user_name: str | None) -> str:
        """Тизер с обращением по имени — у продуктов, которые его объявили."""
        if not self.spec.address_by_name:
            return self.spec.teaser
        from astra.ask.naming import address

        return address(self.spec.teaser, user_name)

    def render_answer(self, answer: Any, result: Any, *, user_name: str | None = None) -> str:
        """Разбор в HTML. Имя уходит только тем продуктам, что его ждут.

        Возможность необязательная, как и `render_card`: соседние продукты
        рендерят ответ прежней сигнатурой и о новом аргументе не знают.
        """
        if self.spec.address_by_name:
            return self.prompt.render_answer(answer, result, user_name=user_name)
        return self.prompt.render_answer(answer, result)

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
    QUESTION_KIDS_BOND: AskProductSpec(
        key=QUESTION_KIDS_BOND,
        calc_module="astra.ask.kids_bond",
        prompt_module="astra.llm.prompts.ask.kids_bond",
        calibration_text=(
            "Один вопрос перед ответом — от него зависит, как читать твою карту.\n\n"
            "<b>У тебя уже есть дети?</b>"
        ),
        calibration_yes="Да, есть",
        calibration_no="Пока нет",
        calibration_field="has_children",
        invoice_title="Отношения с детьми",
        invoice_description=(
            "Разбор по твоей натальной карте: какой ты родитель, что ребёнок "
            "получит от тебя лучше всего, где будет напряжение, что ты "
            "повторяешь за своими родителями и каким тебя видит ребёнок."
        ),
        teaser=(
            "Смотрю твой пятый дом, Луну и Меркурий — определяю, какой ты "
            "родитель и как строится связь с ребёнком ✨"
        ),
    ),
    QUESTION_PARTNER_TRAITS: AskProductSpec(
        key=QUESTION_PARTNER_TRAITS,
        calc_module="astra.ask.partner_traits",
        prompt_module="astra.llm.prompts.ask.partner_traits",
        calibration_text=(
            "Один вопрос перед ответом — от него зависит, как читать твою карту.\n\n"
            "<b>Сейчас ты в отношениях?</b>\n\n"
            "<i>Если да — покажу, по каким чертам сверить того, кто рядом.</i>"
        ),
        calibration_yes="Сейчас в отношениях",
        calibration_no="Сейчас свободна/свободен",
        calibration_field="in_relationship",
        invoice_title="Черты судьбоносного партнёра",
        invoice_description=(
            "Разбор по твоей натальной карте: какой типаж партнёра она показывает, "
            "какой у него характер, из какой он среды и по каким чертам его узнать."
        ),
        # Пишется как продолжение обращения: «Аня, смотрю твой седьмой дом…».
        teaser=(
            "смотрю твой седьмой дом, его управителя и Венеру — собираю портрет "
            "того, кого твоя карта показывает судьбоносным ✨"
        ),
        address_by_name=True,
    ),
    QUESTION_PAIN_LOOP: AskProductSpec(
        key=QUESTION_PAIN_LOOP,
        calc_module="astra.ask.pain_loop",
        prompt_module="astra.llm.prompts.ask.pain_loop",
        calibration_text=(
            "Один вопрос перед ответом — от него зависит, как читать твою карту.\n\n"
            "<b>Чаще уходишь ты — или уходят от тебя?</b>\n\n"
            "<i>Отвечай как есть. Одни и те же аспекты карты читаются "
            "по-разному в этих двух случаях.</i>"
        ),
        calibration_yes="Чаще ухожу я",
        calibration_no="Чаще уходят от меня",
        calibration_field="leaves_first",
        invoice_title="Почему я обжигаюсь",
        invoice_description=(
            "Разбор по твоей натальной карте: какой сценарий ты повторяешь в отношениях, "
            "по каким признакам его узнать, в какой момент всё каждый раз ломается "
            "и что размыкает этот круг."
        ),
        # Пишется как продолжение обращения: «Аня, смотрю твою Венеру…».
        teaser=(
            "смотрю твою Венеру, Луну и их аспекты — ищу тот самый круг, "
            "который повторяется у тебя из истории в историю 💫"
        ),
        address_by_name=True,
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
