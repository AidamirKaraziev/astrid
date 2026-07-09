"""AI-чат Astrid — свободный текст вместо кнопочных FSM-флоу.

Прототип (feature/ai-chat-astrid). Включается флагом `ai_chat_enabled`.
Точка входа — `router` в `handler.py`, регистрируется последним в bot.py.
"""

from astra.telegram.ai_chat.handler import router

__all__ = ["router"]
