from astra.telegram.button_texts import (
    BTN_WHEEL,
    BTN_BACK_MENU,
    BTN_COMPATIBILITY,
    BTN_PREDICTION_TODAY_LEGACY,
    BTN_TAROT,
    BTN_TAROT_THREE,
)
from astra.telegram.keyboard_policy import (
    KeyboardZone,
    is_fsm_keyboard_suppressed,
    reply_keyboard_for_zone,
    reply_keyboard_to_api_payload,
    resolve_keyboard_zone,
)
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.states import BirthDataStates, OnboardingStates, ProfileStates


def test_main_menu_buttons_resolve_to_main_zone() -> None:
    zone = resolve_keyboard_zone(
        incoming_text=BTN_PREDICTION_TODAY_LEGACY,
        fsm_state=None,
    )
    assert zone is KeyboardZone.MAIN


def test_tarot_navigation_returns_main_menu() -> None:
    """Раздел таро живёт в inline-экране: своей reply-клавиатуры у него больше нет.

    Нажатие закэшированной кнопки расклада тоже возвращает главное меню — так
    устаревшая клавиатура лечится сама, без похода в «Назад».
    """
    assert resolve_keyboard_zone(incoming_text=BTN_TAROT, fsm_state=None) is KeyboardZone.MAIN
    assert resolve_keyboard_zone(incoming_text=BTN_BACK_MENU, fsm_state=None) is KeyboardZone.MAIN
    assert resolve_keyboard_zone(incoming_text=BTN_TAROT_THREE, fsm_state=None) is KeyboardZone.MAIN


def test_paid_stub_keeps_main_zone() -> None:
    zone = resolve_keyboard_zone(incoming_text=BTN_COMPATIBILITY, fsm_state=None)
    assert zone is KeyboardZone.MAIN


def test_free_text_refreshes_main_menu() -> None:
    zone = resolve_keyboard_zone(incoming_text="привет", fsm_state=None)
    assert zone is KeyboardZone.MAIN


def test_onboarding_fsm_suppresses_keyboard() -> None:
    assert is_fsm_keyboard_suppressed(OnboardingStates.welcome.state)
    assert is_fsm_keyboard_suppressed(OnboardingStates.gender.state)
    # Добор данных посреди продукта — то же правило: главное меню под рукой
    # уводит человека из сценария одним касанием.
    assert is_fsm_keyboard_suppressed(BirthDataStates.date.state)
    zone = resolve_keyboard_zone(
        incoming_text=BTN_PREDICTION_TODAY_LEGACY,
        fsm_state=BirthDataStates.date.state,
    )
    assert zone is None


def test_place_search_fsm_suppresses_keyboard() -> None:
    zone = resolve_keyboard_zone(
        incoming_text="Казань",
        fsm_state=ProfileStates.edit_notification_place_query.state,
    )
    assert zone is None


def test_profile_name_edit_refreshes_main_menu() -> None:
    zone = resolve_keyboard_zone(
        incoming_text="Марина",
        fsm_state=ProfileStates.edit_name.state,
    )
    assert zone is KeyboardZone.MAIN


def test_skip_auto_keyboard_flag() -> None:
    zone = resolve_keyboard_zone(
        incoming_text=BTN_PREDICTION_TODAY_LEGACY,
        fsm_state=None,
        skip_auto_keyboard=True,
    )
    assert zone is None


def test_reply_keyboard_api_payload_has_resize() -> None:
    payload = reply_keyboard_to_api_payload(main_menu_keyboard())
    assert payload["resize_keyboard"] is True
    assert BTN_WHEEL in payload["keyboard"][0][0]["text"]
    assert BTN_COMPATIBILITY in payload["keyboard"][2][0]["text"]


def test_reply_keyboard_for_zone_main() -> None:
    keyboard = reply_keyboard_for_zone(KeyboardZone.MAIN)
    assert keyboard is not None
    assert keyboard.keyboard[0][0].text == BTN_WHEEL

