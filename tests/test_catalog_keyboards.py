from astra.telegram.button_texts import (
    BTN_ASK_ASTRID_LEGACY,
    BTN_ASK_STARS,
    BTN_BACK_MENU,
    BTN_COMPATIBILITY,
    BTN_HELP,
    BTN_INVITE,
    BTN_MONTH_FORECAST,
    BTN_NATAL,
    BTN_PREDICTION_TODAY_LEGACY,
    BTN_PROFILE,
    BTN_TAROT,
    BTN_WHEEL,
    PAID_PRODUCT_BUTTONS,
    TAROT_PRODUCT_BUTTONS,
)
from astra.telegram.keyboards import main_menu_keyboard, tarot_keyboard


def _reply_texts(keyboard) -> list[str]:
    return [btn.text for row in keyboard.keyboard for btn in row]


def test_main_menu_layout_wheel_first() -> None:
    rows = [[btn.text for btn in row] for row in main_menu_keyboard().keyboard]
    assert rows == [
        [BTN_WHEEL],
        [BTN_COMPATIBILITY, BTN_NATAL],
        [BTN_MONTH_FORECAST, BTN_TAROT],
        [BTN_PROFILE, BTN_INVITE],
        [BTN_HELP],
    ]


def test_main_menu_without_prediction_and_ai_chat() -> None:
    texts = set(_reply_texts(main_menu_keyboard()))
    assert BTN_PREDICTION_TODAY_LEGACY not in texts
    assert BTN_ASK_ASTRID_LEGACY not in texts


def test_main_menu_includes_reply_paid_products() -> None:
    texts = _reply_texts(main_menu_keyboard())
    for button in PAID_PRODUCT_BUTTONS:
        assert button in texts
    assert BTN_ASK_STARS not in texts


def test_tarot_submenu_full_width_rows() -> None:
    rows = [[btn.text for btn in row] for row in tarot_keyboard().keyboard]
    assert rows == [
        [TAROT_PRODUCT_BUTTONS[0]],
        [TAROT_PRODUCT_BUTTONS[1]],
        [TAROT_PRODUCT_BUTTONS[2]],
        [BTN_BACK_MENU],
    ]


def test_no_catalog_or_help_in_main_menu() -> None:
    texts = set(_reply_texts(main_menu_keyboard()))
    assert "💫 Каталог" not in texts
    assert "✉️ Помощь" not in texts
