"""Тексты этапов прогресса (голос Astrid, от первого лица)."""

from __future__ import annotations

from astra.telegram.progress.stages import CompatibilityStage, NatalStage, PredictionStage

_PREDICTION_TEXTS: dict[PredictionStage, str] = {
    PredictionStage.STARTED: (
        "Сейчас загляну в твою карту рождения — это займёт пару секунд ✨"
    ),
    PredictionStage.NATAL_DONE: (
        "Карта готова 🌙\n"
        "Сейчас посмотрю, как звёзды складываются именно сегодня."
    ),
    PredictionStage.CONTEXT_DONE: (
        "Небо на сегодня прочитала — картина сложилась 🌙\n"
        "Собираю для тебя предсказание."
    ),
}

_COMPATIBILITY_TEXTS: dict[CompatibilityStage, str] = {
    CompatibilityStage.STARTED: (
        "Начинаю разбирать вашу пару — сначала сверю карты рождения ✨"
    ),
    CompatibilityStage.SYNASTRY_DONE: (
        "Карты сошлись, общая картина видна 🌙\n"
        "Сейчас распишу это подробно."
    ),
    CompatibilityStage.LLM_DONE: (
        "Текст готов ✨\n"
        "Оформляю красивый отчёт."
    ),
}


_NATAL_TEXTS: dict[NatalStage, str] = {
    NatalStage.STARTED: (
        "Начинаю разбирать твою натальную карту — сверяю положение планет ✨"
    ),
    NatalStage.LLM_DONE: (
        "Разбор готов ✨\n"
        "Оформляю красивый отчёт с колесом карты."
    ),
}


def natal_stage_text(stage: NatalStage) -> str:
    return _NATAL_TEXTS[stage]


def prediction_stage_text(stage: PredictionStage) -> str:
    return _PREDICTION_TEXTS[stage]


def compatibility_stage_text(stage: CompatibilityStage) -> str:
    return _COMPATIBILITY_TEXTS[stage]
