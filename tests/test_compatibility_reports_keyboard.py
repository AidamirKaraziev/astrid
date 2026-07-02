from astra.telegram.keyboards import (
    compatibility_delete_confirm_keyboard,
    compatibility_report_card_keyboard,
    compatibility_reports_keyboard,
)


def test_compatibility_reports_keyboard_one_button_per_row() -> None:
    keyboard = compatibility_reports_keyboard(
        [("✅ Aidamir × Анж (02.07)", "00000000-0000-0000-0000-000000000001")],
    )
    assert len(keyboard.inline_keyboard[0]) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == (
        "compatibility:report:00000000-0000-0000-0000-000000000001"
    )


def test_compatibility_report_card_keyboard() -> None:
    report_id = "00000000-0000-0000-0000-000000000002"
    keyboard = compatibility_report_card_keyboard(report_id)
    assert keyboard.inline_keyboard[0][0].text == "📄 Получить PDF"
    assert keyboard.inline_keyboard[0][0].callback_data == f"compat:pdf:{report_id}"
    assert keyboard.inline_keyboard[1][0].text == "🗑 Удалить"
    assert keyboard.inline_keyboard[1][0].callback_data == f"compat:del:{report_id}"
    assert keyboard.inline_keyboard[2][0].text == "◀️ К списку"
    assert keyboard.inline_keyboard[2][0].callback_data == "compat:reports:list"


def test_compatibility_delete_confirm_keyboard() -> None:
    report_id = "00000000-0000-0000-0000-000000000002"
    keyboard = compatibility_delete_confirm_keyboard(report_id)
    row = keyboard.inline_keyboard[0]
    assert row[0].text == "✅ Удалить"
    assert row[1].text == "❌ Отмена"
    assert row[0].callback_data == f"compat:del:yes:{report_id}"
    assert row[1].callback_data == f"compat:del:no:{report_id}"
