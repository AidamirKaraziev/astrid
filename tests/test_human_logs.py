"""Человекочитаемый вывод логов: порядок полей, сокращения, цвет только в TTY."""

from astra.core.observability.human import HumanRenderer


def _render(**event) -> str:
    base = {
        "event": "payment.completed",
        "level": "info",
        "timestamp": "2026-07-29T08:46:42.178806Z",
        "service": "api",
        "logger": "astra.payments.service",
    }
    return HumanRenderer(colors=False)(None, None, {**base, **event})


class TestLine:
    def test_time_shown_in_local_zone(self):
        """08:46 UTC — это 11:46 по Москве; логи сверяют с жалобами людей."""
        assert _render().startswith("11:46:42")

    def test_event_key_kept_as_is(self):
        assert "payment.completed" in _render()

    def test_level_is_readable_word(self):
        assert " info " in _render()
        assert " ERROR " in _render(level="error")
        assert " warn " in _render(level="warning")


class TestFields:
    def test_important_fields_go_first(self):
        line = _render(duration_ms=120, product_code="tarot_wish", user_id="7", amount=150)
        assert line.index("user_id=") < line.index("product_code=") < line.index("amount=")
        assert line.index("amount=") < line.index("duration_ms=")

    def test_unknown_fields_sorted_after(self):
        line = _render(zulu=1, alpha=2)
        assert line.index("alpha=") < line.index("zulu=")

    def test_service_and_logger_dropped(self):
        line = _render()
        assert "service=" not in line
        assert "logger=" not in line

    def test_correlation_id_goes_last(self):
        line = _render(correlation_id="http-26c17a", user_id="7")
        assert line.index("user_id=") < line.index("correlation_id=")


class TestShortening:
    def test_uuid_cut_to_eight(self):
        line = _render(user_id="0e37f0f4-9a1c-4d2a-9d2b-11aa22bb33cc")
        assert "user_id=0e37f0f4" in line
        assert "11aa22bb33cc" not in line

    def test_long_text_trimmed(self):
        line = _render(reason="ы" * 200)
        assert "…" in line
        assert len(line) < 200

    def test_newlines_do_not_break_the_line(self):
        assert "\n" not in _render(reason="первая\nвторая")

    def test_short_values_untouched(self):
        assert "reason=timeout" in _render(reason="timeout")


class TestColors:
    def test_no_escapes_without_tty(self):
        """В docker compose logs цвет превратился бы в мусор."""
        assert "\033" not in _render(level="error")

    def test_escapes_present_when_asked(self):
        line = HumanRenderer(colors=True)(
            None, None, {"event": "boom", "level": "error", "timestamp": "2026-07-29T08:00:00Z"},
        )
        assert "\033[31m" in line


class TestExceptions:
    def test_traceback_appended(self):
        line = _render(level="error", exception="Traceback (most recent call last):\n  ZeroDivisionError")
        assert "ZeroDivisionError" in line
        assert line.count("\n") >= 1
