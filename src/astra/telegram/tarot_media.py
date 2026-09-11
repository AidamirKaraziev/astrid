"""Отправка карт таро фото/альбомом с кэшем file_id в Redis.

Паттерн — как у приветственного видео (handlers/start.py): первая отправка
грузит файл через FSInputFile, дальше по file_id (мгновенно, без заливки).
При смене bot token file_id протухают — сбросить ключи:
    redis-cli --scan --pattern 'astra:telegram:tarot:file_id:*' | xargs redis-cli del
"""

from __future__ import annotations

from aiogram.types import FSInputFile, InputMediaPhoto, Message

from astra.core.observability import get_logger
from astra.tarot.deck import TarotCard
from astra.tarot.file_id_cache import cache_file_id, get_cached_file_id
from astra.tarot.images import image_path
from astra.telegram.effects import send_with_effect

log = get_logger(__name__)

# caption у альбома показывается, только когда он ровно у одного элемента
ALBUM_CAPTION_LIMIT = 1024


async def _get_cached_file_id(card_id: str) -> str | None:
    return await get_cached_file_id(card_id)


async def _cache_file_id(card_id: str, file_id: str) -> None:
    await cache_file_id(card_id, file_id)


def _fallback_line(card: TarotCard) -> str:
    return f"{card.emoji} <b>{card.name_ru}</b>"


async def send_card_photo(
    message: Message,
    card: TarotCard,
    caption: str,
    *,
    effect: str | None = None,
) -> None:
    """Одна карта фото; без ассета — текстом, ритуал важнее картинки."""
    path = image_path(card.id)
    if path is None:
        await message.answer(f"{_fallback_line(card)}\n\n{caption}", parse_mode="HTML")
        return
    cached_file_id = await _get_cached_file_id(card.id)
    photo = cached_file_id or FSInputFile(path)
    # caption у фото ограничен 1024 символами — длинный текст отдельным сообщением
    fits = len(caption) <= ALBUM_CAPTION_LIMIT
    sent = await send_with_effect(
        message.answer_photo,
        photo,
        effect=effect,
        caption=caption if fits else None,
        parse_mode="HTML" if fits else None,
    )
    if not fits:
        await message.answer(caption, parse_mode="HTML")
    if not cached_file_id and sent.photo:
        await _cache_file_id(card.id, sent.photo[-1].file_id)


async def send_cards_album(
    message: Message,
    cards: list[TarotCard],
    caption: str,
    *,
    effect: str | None = None,
) -> None:
    """Расклад альбомом (2–10 карт), caption на первом элементе.

    Если хотя бы одного ассета нет — весь расклад текстом (частичный альбом
    выглядит хуже, чем честный список).
    """
    paths = [image_path(card.id) for card in cards]
    if any(path is None for path in paths):
        lines = "\n".join(_fallback_line(card) for card in cards)
        await message.answer(f"{lines}\n\n{caption}", parse_mode="HTML")
        return

    media: list[InputMediaPhoto] = []
    cached_ids: list[str | None] = []
    for card, path in zip(cards, paths, strict=True):
        cached_file_id = await _get_cached_file_id(card.id)
        cached_ids.append(cached_file_id)
        media.append(
            InputMediaPhoto(
                media=cached_file_id or FSInputFile(path),
                caption=caption if not media else None,
                parse_mode="HTML" if not media else None,
            ),
        )
    sent_messages = await send_with_effect(
        message.answer_media_group,
        media,
        effect=effect,
    )
    for card, cached_file_id, sent in zip(cards, cached_ids, sent_messages, strict=False):
        if not cached_file_id and sent.photo:
            await _cache_file_id(card.id, sent.photo[-1].file_id)
