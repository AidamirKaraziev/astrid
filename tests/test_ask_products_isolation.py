"""Изоляция продуктов раздела «Спроси Астрид».

Смысл этих тестов: удаление или поломка одного вопроса не должны задевать
остальные. Проверяем не намерение, а факт — ломаем импорт модуля продукта и
смотрим, что соседние продукты продолжают продаваться.

Список продуктов берётся из самого реестра: новый вопрос попадает под все
проверки автоматически, без правки этого файла.
"""

import importlib
import re
import sys
from importlib.abc import MetaPathFinder

import pytest

from astra.ask import products as registry

# Модули, которые общие для всего раздела и не должны знать ни одного продукта.
SHARED_MODULES = (
    "astra.ask.windows",
    "astra.ask.card",
    "astra.ask.naming",
    "astra.services.ask_service",
)

PRODUCT_KEYS = sorted(registry.SPECS)


def _source(module_name: str) -> str:
    module = importlib.import_module(module_name)
    with open(module.__file__ or "", encoding="utf-8") as handle:  # noqa: PTH123
        return handle.read()


def _product_modules(key: str) -> tuple[str, str]:
    spec = registry.SPECS[key]
    return spec.calc_module, spec.prompt_module


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
    text = _source("astra.ask.products")
    imports = [line for line in text.splitlines() if re.match(r"\s*(from|import)\s", line)]
    for key in PRODUCT_KEYS:
        for module_name in _product_modules(key):
            assert all(module_name not in line for line in imports), f"реестр импортирует {module_name}"


@pytest.mark.parametrize("broken_key", PRODUCT_KEYS)
def test_broken_product_does_not_take_down_the_others(broken_key: str) -> None:
    """Один продукт удалён — все остальные продолжают работать."""
    modules = _product_modules(broken_key)
    gone = _Removed(*modules)
    _forget(*modules)
    sys.meta_path.insert(0, gone)
    try:
        registry._load.cache_clear()
        assert registry.get_product(broken_key) is None
        assert registry.is_ready(broken_key) is False

        for key in PRODUCT_KEYS:
            if key == broken_key:
                continue
            alive = registry.get_product(key)
            assert alive is not None, f"{key} упал вместе с {broken_key}"
            assert alive.prompt.SYSTEM_PROMPT
            assert callable(alive.compute)
    finally:
        sys.meta_path.remove(gone)
        registry._load.cache_clear()


@pytest.mark.parametrize("broken_key", PRODUCT_KEYS)
def test_section_handler_still_imports_without_a_product(broken_key: str) -> None:
    """Раздел поднимается, даже если модуль одного продукта не грузится."""
    modules = _product_modules(broken_key)
    gone = _Removed(*modules)
    _forget(*modules)
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


@pytest.mark.parametrize("key", PRODUCT_KEYS)
def test_products_do_not_import_each_other(key: str) -> None:
    """Продукт не должен знать о соседе: общее живёт в windows/card/base."""
    others = {
        module
        for other_key in PRODUCT_KEYS
        if other_key != key
        for module in _product_modules(other_key)
    }
    for module_name in _product_modules(key):
        text = _source(module_name)
        for other in others:
            assert other not in text, f"{module_name} знает про {other}"


@pytest.mark.parametrize("module_name", SHARED_MODULES)
def test_shared_layer_knows_nothing_about_products(module_name: str) -> None:
    """Общие модули раздела не должны упоминать конкретные продукты."""
    text = _source(module_name)
    for key in PRODUCT_KEYS:
        for product_module in _product_modules(key):
            assert product_module not in text, f"{module_name} знает про {product_module}"


@pytest.mark.parametrize("key", PRODUCT_KEYS)
def test_every_product_fulfils_the_contract(key: str) -> None:
    """Контракт проверяется тестом: модуль, который импортируется, но не дописан,
    иначе упал бы уже после списания денег."""
    product = registry.get_product(key)
    assert product is not None
    assert isinstance(product.methodology_version, int)
    assert product.result_model is not None
    for attribute in (
        "SYSTEM_PROMPT",
        "TEMPERATURE",
        "MAX_TOKENS",
        "build_user_message",
        "parse",
        "validate",
        "expected_blocks",
        "render_answer",
        "card_caption",
    ):
        assert hasattr(product.prompt, attribute), f"{key}: в промпте нет {attribute}"
    assert callable(product.calc.compute)
