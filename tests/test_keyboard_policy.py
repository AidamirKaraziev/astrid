from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_BACK_MENU,
    BTN_COMPATIBILITY,
    BTN_PREDICTION_TODAY,
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
from astra.telegram.keyboards import main_menu_keyboard, tarot_keyboard
from astra.telegram.states import OnboardingStates, ProfileStates


def test_main_menu_buttons_resolve_to_main_zone() -> None:
    zone = resolve_keyboard_zone(
        incoming_text=BTN_PREDICTION_TODAY,
        fsm_state=None,
    )
    assert zone is KeyboardZone.MAIN


def test_tarot_navigation_zones() -> None:
    assert resolve_keyboard_zone(incoming_text=BTN_TAROT, fsm_state=None) is KeyboardZone.TAROT
    assert resolve_keyboard_zone(incoming_text=BTN_BACK_MENU, fsm_state=None) is KeyboardZone.MAIN
    assert resolve_keyboard_zone(incoming_text=BTN_TAROT_THREE, fsm_state=None) is KeyboardZone.TAROT


def test_paid_stub_keeps_main_zone() -> None:
    zone = resolve_keyboard_zone(incoming_text=BTN_COMPATIBILITY, fsm_state=None)
    assert zone is KeyboardZone.MAIN


def test_free_text_refreshes_main_menu() -> None:
    zone = resolve_keyboard_zone(incoming_text="привет", fsm_state=None)
    assert zone is KeyboardZone.MAIN


def test_onboarding_fsm_suppresses_keyboard() -> None:
    assert is_fsm_keyboard_suppressed(OnboardingStates.gender.state)
    assert is_fsm_keyboard_suppressed(OnboardingStates.birth_date.state)
    zone = resolve_keyboard_zone(
        incoming_text=BTN_PREDICTION_TODAY,
        fsm_state=OnboardingStates.birth_date.state,
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
        incoming_text=BTN_PREDICTION_TODAY,
        fsm_state=None,
        skip_auto_keyboard=True,
    )
    assert zone is None


def test_reply_keyboard_api_payload_has_resize() -> None:
    payload = reply_keyboard_to_api_payload(main_menu_keyboard())
    assert payload["resize_keyboard"] is True
    assert BTN_ASK_ASTRID in payload["keyboard"][0][0]["text"]
    assert BTN_PREDICTION_TODAY in payload["keyboard"][1][0]["text"]
    assert BTN_COMPATIBILITY in payload["keyboard"][2][0]["text"]


def test_reply_keyboard_for_zone_main() -> None:
    keyboard = reply_keyboard_for_zone(KeyboardZone.MAIN)
    assert keyboard is not None
    assert keyboard.keyboard[0][0].text == BTN_ASK_ASTRID


def test_reply_keyboard_for_zone_tarot() -> None:
    keyboard = reply_keyboard_for_zone(KeyboardZone.TAROT)
    assert keyboard == tarot_keyboard()
