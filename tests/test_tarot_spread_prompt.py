"""Тесты спек раскладов и промпта: структура, нормализация, валидация."""

from astra.llm.prompts.tarot_spread import (
    TAROT_SPREAD_SYSTEM_PROMPT,
    build_spread_user_message,
    clean_spread_output,
    normalize_spread_blocks,
    validate_spread_output,
)
from astra.tarot.deck import card_by_id
from astra.tarot.spreads import SPREADS, SpreadType

_YES_NO = SPREADS[SpreadType.YES_NO]
_THREE = SPREADS[SpreadType.THREE_CARDS]
_REL = SPREADS[SpreadType.RELATIONSHIP]

_BLOCK = "Карта в этой позиции говорит о движении и выборе стороны без спешки сегодня."
_SUMMARY_YES = "Да, но сначала закрой начатое — карта просит одного конкретного шага."
_SUMMARY = "Итог складывается в пользу разговора — начни его сегодня сама."


class TestSpecs:
    def test_spread_shapes(self):
        assert _YES_NO.card_count == 1 and _YES_NO.question_required
        assert _THREE.card_count == 3 and not _THREE.question_required
        assert _REL.card_count == 5 and _REL.question_required

    def test_position_keys_unique(self):
        for spec in SPREADS.values():
            keys = [p.key for p in spec.positions]
            assert len(keys) == len(set(keys)), spec.type


class TestBuildMessage:
    def test_contains_cards_positions_and_question(self):
        cards = [card_by_id("major_07"), card_by_id("cups_02"), card_by_id("wands_10")]
        message = build_spread_user_message(_THREE, "Что с моей работой?", cards)
        assert "Что с моей работой?" in message
        assert "Колесница" in message and "Двойка Кубков" in message
        assert "Прошлое" in message and "Будущее" in message
        assert '"число_блоков_в_ответе": 4' in message

    def test_no_question_fallback(self):
        message = build_spread_user_message(_THREE, None, [card_by_id("major_00")] * 3)
        assert "вопрос не задан" in message

    def test_client_name_and_gender_included(self):
        cards = [card_by_id("major_07")]
        message = build_spread_user_message(
            _YES_NO, "Начинать ли бизнес?", cards,
            user_name="Аня", gender="женщина",
        )
        assert '"клиент"' in message
        assert "Аня" in message
        assert "женщина" in message

    def test_client_block_omitted_when_no_profile(self):
        message = build_spread_user_message(_YES_NO, "Вопрос?", [card_by_id("major_07")])
        assert "клиент" not in message


class TestPersona:
    def test_prompt_uses_cyrillic_name(self):
        assert "Астрид" in TAROT_SPREAD_SYSTEM_PROMPT
        assert "Astrid" in TAROT_SPREAD_SYSTEM_PROMPT  # только в запрете «никогда Astrid»
        assert "род" in TAROT_SPREAD_SYSTEM_PROMPT.lower()


class TestNormalize:
    def test_extra_blocks_merged_into_summary(self):
        text = "\n\n".join([_BLOCK, _BLOCK, _BLOCK, _SUMMARY, "И ещё хвост."])
        normalized = normalize_spread_blocks(_THREE, text)
        blocks = normalized.split("\n\n")
        assert len(blocks) == 4
        assert blocks[-1].endswith("И ещё хвост.")

    def test_expected_count_untouched(self):
        text = "\n\n".join([_BLOCK, _SUMMARY_YES])
        assert normalize_spread_blocks(_YES_NO, text) == text


class TestValidate:
    def test_valid_yes_no(self):
        assert validate_spread_output(_YES_NO, f"{_BLOCK}\n\n{_SUMMARY_YES}") is None

    def test_yes_no_without_verdict(self):
        text = f"{_BLOCK}\n\n{_SUMMARY}"
        assert validate_spread_output(_YES_NO, text) == "missing_verdict"

    def test_verdict_with_quotes_accepted(self):
        text = f"{_BLOCK}\n\n«Да, но не раньше пятницы — карта просит паузы и тишины.»"
        assert validate_spread_output(_YES_NO, text) is None

    def test_wrong_block_count(self):
        assert validate_spread_output(_THREE, f"{_BLOCK}\n\n{_SUMMARY}") == "invalid_structure"

    def test_short_position_block(self):
        text = "\n\n".join(["Коротко.", _BLOCK, _BLOCK, _SUMMARY])
        assert validate_spread_output(_THREE, text) == "position_block_too_short"

    def test_short_summary(self):
        text = "\n\n".join([_BLOCK, _BLOCK, _BLOCK, "Всё."])
        assert validate_spread_output(_THREE, text) == "summary_too_short"

    def test_valid_relationship(self):
        text = "\n\n".join([_BLOCK] * 5 + [_SUMMARY])
        assert validate_spread_output(_REL, text) is None


# Реалистичные ответы модели (как их присылает DeepSeek) — проверяем ВЕСЬ путь
# clean → normalize → validate, а не только валидатор на чистых строках.
_THREE_REAL = (
    "Тройка Жезлов в прошлом говорит о моменте, когда ты уже отправила корабли "
    "в путь и решилась расширяться, пусть и с тревогой в груди.\n\n"
    "Справедливость в настоящем показывает точку честного расчёта: сейчас всё "
    "взвешивается ровно, и ты получаешь то, что посеяла раньше.\n\n"
    "Королева Кубков в будущем обещает тепло и эмоциональную зрелость, если ты "
    "позволишь себе довериться собственным чувствам.\n\n"
    "Итог: расклад складывается в твою пользу — продолжай начатое и дай себе "
    "неделю на спокойное решение без спешки."
)

_REL_REAL = "\n\n".join(
    [
        "Ты вносишь в эти отношения искренний интерес и готовность вкладываться, "
        "но иногда ждёшь подтверждения слишком быстро.",
        "Он приходит осторожнее: ему нужно время, чтобы поверить, что здесь "
        "безопасно открыться по-настоящему.",
        "Между вами живая связь, в которой больше тепла, чем вы оба готовы "
        "признать вслух прямо сейчас.",
        "Мешает страх сделать первый шаг — каждый ждёт, что начнёт другой, "
        "и пауза затягивается.",
        "Если хотя бы один заговорит честно, отношения двинутся к сближению, "
        "а не к медленному угасанию.",
        "Итог: связь жива и хочет расти — не жди идеального момента, скажи о "
        "своих чувствах на этой неделе.",
    ],
)


class TestFullPipeline:
    """clean → normalize → validate на реальных форматах вывода."""

    def _run(self, spec, raw: str) -> str | None:
        return validate_spread_output(spec, normalize_spread_blocks(spec, clean_spread_output(raw)))

    def test_three_cards_real_output_passes(self):
        assert self._run(_THREE, _THREE_REAL) is None

    def test_relationship_real_output_passes(self):
        assert self._run(_REL, _REL_REAL) is None

    def test_code_fence_wrapper_stripped(self):
        wrapped = f"```\n{_THREE_REAL}\n```"
        assert self._run(_THREE, wrapped) is None

    def test_outer_quotes_stripped(self):
        assert self._run(_THREE, f"«{_THREE_REAL}»") is None

    def test_position_label_lines_merged(self):
        # модель подписала блоки заголовками отдельной строкой
        labelled = (
            "Прошлое:\nТройка Жезлов говорит о решимости расширяться, принятой "
            "ранее с тревогой, но всё же принятой тобой честно.\n\n"
            "Настоящее:\nСправедливость показывает честный расчёт — сейчас всё "
            "взвешивается ровно и по заслугам твоим.\n\n"
            "Будущее:\nКоролева Кубков обещает тепло, если доверишься чувствам "
            "своим и не будешь торопить события вокруг.\n\n"
            "Итог:\nРасклад в твою пользу — продолжай начатое и дай себе неделю "
            "на спокойное взвешенное решение."
        )
        assert self._run(_THREE, labelled) is None

    def test_clean_does_not_touch_plain_blocks(self):
        assert clean_spread_output(_THREE_REAL) == _THREE_REAL
