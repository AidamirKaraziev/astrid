from astra.telegram.bot_menu import BOT_COMMANDS_RU
from astra.telegram.button_texts import BTN_ASK_STARS, CB_PRODUCT_ASK_STARS
from astra.telegram.keyboards import prediction_followup_keyboard


def test_bot_commands_cover_main_actions() -> None:
    commands = {cmd.command for cmd in BOT_COMMANDS_RU}
    assert commands == {"start", "help"}
    descriptions = {cmd.command: cmd.description for cmd in BOT_COMMANDS_RU}
    assert descriptions["start"] == "🏠 Главное меню"
    assert descriptions["help"] == "💌 Написать Astrid"


def test_help_keyboard_links_to_support() -> None:
    from astra.telegram.keyboards import help_keyboard

    button = help_keyboard("AstridSupport").inline_keyboard[0][0]
    assert button.text == "💌 Написать Astrid"
    assert button.url == "https://t.me/AstridSupport"
    assert button.style == "primary"


def test_prediction_followup_has_tarot_and_ask_stars_cta() -> None:
    from astra.telegram.keyboards import BTN_TAROT_DAILY, CB_TAROT_DAILY

    keyboard = prediction_followup_keyboard()
    tarot = keyboard.inline_keyboard[0][0]
    assert tarot.text == BTN_TAROT_DAILY
    assert tarot.callback_data == CB_TAROT_DAILY
    assert tarot.style == "primary"
    ask = keyboard.inline_keyboard[1][0]
    assert ask.text == BTN_ASK_STARS
    assert ask.callback_data == CB_PRODUCT_ASK_STARS


def test_prediction_followup_serializes_for_api() -> None:
    from astra.telegram.keyboards import CB_TAROT_DAILY

    payload = prediction_followup_keyboard().model_dump(mode="json", exclude_none=True)
    button = payload["inline_keyboard"][0][0]
    assert button["style"] == "primary"
    assert button["callback_data"] == CB_TAROT_DAILY
    assert payload["inline_keyboard"][1][0]["callback_data"] == CB_PRODUCT_ASK_STARS
