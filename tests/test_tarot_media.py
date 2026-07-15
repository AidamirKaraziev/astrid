"""Тесты медиа карт: ассеты на месте, кэш file_id, fallback без картинки."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import FSInputFile

from astra.tarot.deck import DECK, card_by_id
from astra.tarot.images import TAROT_IMAGES_DIR, image_path
from astra.telegram.tarot_media import send_card_photo, send_cards_album

_STAR = card_by_id("major_17")
_QUEEN = card_by_id("cups_queen")


class TestImageAssets:
    def test_all_78_assets_exist(self):
        missing = [card.id for card in DECK if image_path(card.id) is None]
        assert missing == []

    def test_image_path_convention(self):
        path = image_path("major_17")
        assert path is not None
        assert path == TAROT_IMAGES_DIR / "major_17.jpg"

    def test_unknown_card_returns_none(self):
        assert image_path("major_99") is None


def _message_mock(photo_file_id: str = "tg_file_123") -> MagicMock:
    message = MagicMock()
    sent = MagicMock()
    sent.photo = [MagicMock(file_id=photo_file_id)]
    message.answer_photo = AsyncMock(return_value=sent)
    message.answer = AsyncMock()
    message.answer_media_group = AsyncMock(return_value=[sent, sent, sent])
    return message


class TestSendCardPhoto:
    async def test_first_send_uploads_file_and_caches(self):
        message = _message_mock()
        with (
            patch("astra.telegram.tarot_media._get_cached_file_id", AsyncMock(return_value=None)),
            patch("astra.telegram.tarot_media._cache_file_id", AsyncMock()) as cache,
        ):
            await send_card_photo(message, _STAR, "Звезда говорит")
        photo_arg = message.answer_photo.call_args.args[0]
        assert isinstance(photo_arg, FSInputFile)
        cache.assert_awaited_once_with("major_17", "tg_file_123")

    async def test_second_send_uses_cached_file_id(self):
        message = _message_mock()
        with (
            patch(
                "astra.telegram.tarot_media._get_cached_file_id",
                AsyncMock(return_value="cached_id"),
            ),
            patch("astra.telegram.tarot_media._cache_file_id", AsyncMock()) as cache,
        ):
            await send_card_photo(message, _STAR, "Звезда говорит")
        assert message.answer_photo.call_args.args[0] == "cached_id"
        cache.assert_not_awaited()

    async def test_long_caption_sent_as_separate_message(self):
        message = _message_mock()
        with (
            patch("astra.telegram.tarot_media._get_cached_file_id", AsyncMock(return_value=None)),
            patch("astra.telegram.tarot_media._cache_file_id", AsyncMock()),
        ):
            await send_card_photo(message, _STAR, "х" * 1500)
        assert message.answer_photo.call_args.kwargs["caption"] is None
        message.answer.assert_awaited_once()

    async def test_missing_asset_falls_back_to_text(self):
        message = _message_mock()
        with patch("astra.telegram.tarot_media.image_path", return_value=None):
            await send_card_photo(message, _STAR, "Звезда говорит")
        message.answer_photo.assert_not_awaited()
        text = message.answer.call_args.args[0]
        assert "Звезда" in text and "Звезда говорит" in text


class TestSendCardsAlbum:
    async def test_caption_only_on_first_item(self):
        message = _message_mock()
        cards = [_STAR, _QUEEN, card_by_id("wands_03")]
        with (
            patch("astra.telegram.tarot_media._get_cached_file_id", AsyncMock(return_value=None)),
            patch("astra.telegram.tarot_media._cache_file_id", AsyncMock()) as cache,
        ):
            await send_cards_album(message, cards, "Расклад готов")
        media = message.answer_media_group.call_args.args[0]
        assert len(media) == 3
        assert media[0].caption == "Расклад готов"
        assert media[1].caption is None and media[2].caption is None
        assert cache.await_count == 3

    async def test_missing_asset_falls_back_to_text_list(self):
        message = _message_mock()
        cards = [_STAR, _QUEEN]
        with patch("astra.telegram.tarot_media.image_path", side_effect=[None, None]):
            await send_cards_album(message, cards, "Расклад готов")
        message.answer_media_group.assert_not_awaited()
        text = message.answer.call_args.args[0]
        assert "Звезда" in text and "Королева Кубков" in text
