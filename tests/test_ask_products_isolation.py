"""Изоляция продуктов раздела «Спроси Астрид».

Смысл этих тестов: удаление или поломка одного вопроса не должны задевать
остальные. Проверяем не намерение, а факт — ломаем импорт модуля продукта и
смотрим, что соседний продукт продолжает продаваться.
"""

import importlib
import sys
from importlib.abc import MetaPathFinder

import pytest

from astra.ask import products as registry


class _Removed(MetaPathFinder):
    """Симулирует «модуль продукта удалили из репозитория»."""

    def __init__(self, *names: str) -> None:
        self._names = set(names)

    def find_spec(self, name, path=None, target=None):  # noqa: ANN001, ANN202
        if name in self._names:
            raise ImportError(f"модуль {name} удалён вместе с продуктом")
        return None


def _forget(*module_names: str) -> None:
    for name in module_names:
        sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _clean_cache():
    """Реестр кэширует загрузку — между тестами кэш сбрасываем."""
    registry._load.cache_clear()
    yield
    registry._load.cache_clear()


def test_products_are_not_imported_by_the_registry_itself() -> None:
    """В реестре нет импортов конкретных продуктов — только пути строками."""
    source = (importlib.import_module("astra.ask.products").__file__ or "")
    text = open(source, encoding="utf-8").read()  # noqa: SIM115, PTH123
    assert "from astra.ask.children import" not in text
    assert "from astra.ask.fated_partners import" not in text
    assert "from astra.llm.prompts.ask import" not in text


def test_broken_product_does_not_take_down_the_others() -> None:
    """Продукт «дети» удалён — партнёры продолжают работать."""
    gone = _Removed("astra.ask.children", "astra.llm.prompts.ask.children")
    _forget("astra.ask.children", "astra.llm.prompts.ask.children")
    sys.meta_path.insert(0, gone)
    try:
        registry._load.cache_clear()
        assert registry.get_product(registry.QUESTION_CHILDREN) is None
        assert registry.is_ready(registry.QUESTION_CHILDREN) is False

        alive = registry.get_product(registry.QUESTION_FATED_COUNT)
        assert alive is not None
        assert alive.prompt.SYSTEM_PROMPT
        assert callable(alive.compute)
    finally:
        sys.meta_path.remove(gone)
        registry._load.cache_clear()


def test_section_handler_still_imports_without_a_product() -> None:
    """Раздел поднимается, даже если модуль одного продукта не грузится."""
    gone = _Removed("astra.ask.children", "astra.llm.prompts.ask.children")
    _forget("astra.ask.children", "astra.llm.prompts.ask.children")
    sys.meta_path.insert(0, gone)
    try:
        registry._load.cache_clear()
        handler = importlib.reload(importlib.import_module("astra.telegram.handlers.ask_astrid"))
        assert handler.router is not None
    finally:
        sys.meta_path.remove(gone)
        registry._load.cache_clear()
        importlib.reload(importlib.import_module("astra.telegram.handlers.ask_astrid"))


def test_unknown_question_is_simply_not_ready() -> None:
    assert registry.get_product("money_income_ceiling") is None
    assert registry.is_ready("money_income_ceiling") is False


def test_products_do_not_import_each_other() -> None:
    """Продукт не должен знать о соседе: общее живёт в windows/card/base."""
    for module_name in ("astra.ask.fated_partners", "astra.ask.children"):
        module = importlib.import_module(module_name)
        text = open(module.__file__, encoding="utf-8").read()  # noqa: SIM115, PTH123
        others = {"astra.ask.fated_partners", "astra.ask.children"} - {module_name}
        for other in others:
            assert other not in text, f"{module_name} знает про {other}"


def test_shared_layer_knows_nothing_about_products() -> None:
    """Общие модули раздела не должны упоминать конкретные продукты."""
    for module_name in ("astra.ask.windows", "astra.ask.card", "astra.services.ask_service"):
        module = importlib.import_module(module_name)
        text = open(module.__file__, encoding="utf-8").read()  # noqa: SIM115, PTH123
        assert "fated_partners" not in text, module_name
        assert "astra.ask.children" not in text, module_name
