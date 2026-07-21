"""Анимация вращения колеса: лента призов прокручивается редактированием сообщения.

Настоящего колеса в Bot API нет: бот отправляет сообщение и несколько раз
редактирует его, сдвигая ленту секторов и замедляясь к финалу. Приз известен
заранее — анимация лишь доводит ленту до нужного сектора, поэтому сбой
редактирования (флуд-лимит, сеть) не влияет на выдачу выигрыша.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from aiogram.types import Message

from astra.core.observability import Event, get_logger

log = get_logger(__name__)

# Шаги ленты между кадрами и паузы после них: к финалу и то и другое замедляется.
_FRAME_STEPS: tuple[int, ...] = (3, 3, 2, 2, 1, 1)
_FRAME_DELAYS: tuple[float, ...] = (0.4, 0.45, 0.55, 0.7, 0.9, 1.1)

_POINTER = "▸ "
_PADDING = "   "
_SPINNING_HEADER = "🎡 <b>Колесо крутится…</b>"


def _window_size(total: int) -> int:
    return 3 if total >= 3 else total


def render_frame(labels: Sequence[str], offset: int, *, header: str = _SPINNING_HEADER) -> str:
    """Кадр ленты: несколько секторов, в центре — тот, что под стрелкой."""
    total = len(labels)
    window = _window_size(total)
    top = -(window // 2)
    rows = []
    for shift in range(top, top + window):
        label = labels[(offset + shift) % total]
        rows.append(f"{_POINTER}{label}" if shift == 0 else f"{_PADDING}{label}")
    return f"{header}\n\n" + "\n".join(rows)


def frame_offsets(total: int, winner_index: int) -> list[int]:
    """Смещения ленты по кадрам: последний кадр — победитель под стрелкой.

    Соседние кадры обязаны отличаться: одинаковый текст Telegram редактировать
    отказывается («message is not modified») и анимация оборвалась бы. Шаг,
    кратный длине ленты (например 3 сектора и шаг 3), сдвигаем на один.
    """
    if total < 2:
        return [0]
    offsets = [winner_index % total]
    for step in reversed(_FRAME_STEPS):
        following = offsets[0]
        candidate = (following - step) % total
        if candidate == following:
            candidate = (following - 1) % total
        offsets.insert(0, candidate)
    return offsets


def build_frames(labels: Sequence[str], winner_index: int) -> list[str]:
    if len(labels) < 2:
        # Один сектор — крутить нечего, показываем сразу финальный кадр.
        return [render_frame(labels, 0)]
    return [render_frame(labels, offset) for offset in frame_offsets(len(labels), winner_index)]


async def play_spin_animation(
    message: Message,
    labels: Sequence[str],
    winner_index: int,
) -> None:
    """Прокрутить ленту в чате. Ошибки редактирования гасим — приз уже выдан."""
    if not labels:
        return
    frames = build_frames(labels, winner_index)
    try:
        sent = await message.answer(frames[0], parse_mode="HTML")
    except Exception as exc:  # сеть/лимиты: анимация необязательна
        log.warning(Event.WHEEL_ANIMATION_FAILED, error_type=type(exc).__name__)
        return
    for frame, delay in zip(frames[1:], _FRAME_DELAYS, strict=False):
        await asyncio.sleep(delay)
        try:
            await sent.edit_text(frame, parse_mode="HTML")
        except Exception as exc:
            log.warning(Event.WHEEL_ANIMATION_FAILED, error_type=type(exc).__name__)
            return
