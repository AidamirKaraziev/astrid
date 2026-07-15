"""Тесты роутинга таро-интентов из AI-чата Astrid в FSM раскладов."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.telegram.ai_chat.handler import _flow_dispatch, ai_chat_turn
from astra.telegram.ai_chat.intents import AstridReply, Intent
from astra.telegram.ai_chat.prompt import build_system_prompt
from astra.telegram.states import TarotStates

_TAROT_INTENTS = (Intent.tarot_yes_no, Intent.tarot_three_cards, Intent.tarot_relationship)


class TestIntents:
    def test_tarot_intents_roundtrip(self):
        for intent in _TAROT_INTENTS:
            reply = AstridReply.model_validate(
                {"reply": "Сейчас разложу", "intent": intent.value, "ready_to_route": True},
            )
            assert reply.intent is intent

    def test_prompt_documents_tarot_intents(self):
        prompt = build_system_prompt()
        for intent in _TAROT_INTENTS:
            assert intent.value in prompt

    def test_flow_dispatch_covers_tarot_intents(self):
        dispatch = _flow_dispatch()
        for intent in _TAROT_INTENTS:
            assert intent in dispatch


class TestRouting:
    async def test_relationship_text_routes_to_waiting_question(self):
        message = MagicMock()
        message.text = "сделай расклад на отношения с Сашей"
        message.from_user = MagicMock(id=100500)
        message.answer = AsyncMock()
        message.chat.do = AsyncMock()
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})
        session = AsyncMock()

        user = MagicMock()
        user.id = uuid4()
        user.onboarding_completed = True
        user.profile = MagicMock(display_name="Аня", timezone="Europe/Moscow")

        astrid_reply = AstridReply(
            reply="Разложу карты на вас двоих ✨",
            intent=Intent.tarot_relationship,
            ready_to_route=True,
        )
        with (
            patch(
                "astra.telegram.ai_chat.handler.run_astrid",
                AsyncMock(return_value=astrid_reply),
            ),
            patch(
                "astra.telegram.ai_chat.handler.users_crud.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "astra.telegram.handlers.tarot_spreads.users_crud.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "astra.telegram.handlers.tarot_spreads.check_daily_limit",
                AsyncMock(return_value=True),
            ),
        ):
            await ai_chat_turn(message, state, session)

        state.set_state.assert_awaited_once_with(TarotStates.waiting_question)
        state.update_data.assert_awaited_with(tarot_spread_type="relationship")
