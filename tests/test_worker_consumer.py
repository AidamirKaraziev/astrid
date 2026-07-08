from types import SimpleNamespace
from unittest.mock import patch

from astra.core.observability import Event
from astra.workers.consumer import check_daily_provider_configured


def _cfg(*, enabled: bool, api_key: str) -> SimpleNamespace:
    return SimpleNamespace(deepseek_enabled=enabled, deepseek_api_key=api_key)


def test_warns_when_daily_provider_unconfigured() -> None:
    with patch("astra.workers.consumer.log") as log:
        check_daily_provider_configured(_cfg(enabled=False, api_key=""))

    log.warning.assert_called_once()
    assert log.warning.call_args.args[0] == Event.LLM_DAILY_PROVIDER_UNCONFIGURED


def test_silent_when_daily_provider_configured() -> None:
    with patch("astra.workers.consumer.log") as log:
        check_daily_provider_configured(_cfg(enabled=True, api_key="sk-x"))

    log.warning.assert_not_called()
