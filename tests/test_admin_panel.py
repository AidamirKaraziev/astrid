"""Тесты админ-панели: выключена без пароля, вход, правки каталога, экранирование."""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from astra.admin import auth, render
from astra.admin.service import AdminError, PriceView, PrizeView, ProductView, update_price, update_prize
from astra.core.config import Settings, get_settings
from astra.db.session import get_session

_ROUTERS = "astra.admin.routers"
_PASSWORD = "звёзды-и-скидки"


def _settings(**overrides) -> Settings:
    base = {
        "admin_username": "astrid",
        "admin_password": _PASSWORD,
        "admin_session_secret": "test-secret",
    }
    return Settings(**{**base, **overrides})


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    auth._failures.clear()
    yield
    get_settings.cache_clear()
    auth._failures.clear()


async def _client(settings: Settings, session=None) -> AsyncClient:
    from astra.main import create_app

    get_settings.cache_clear()
    with patch("astra.core.config.Settings", return_value=settings):
        app = create_app(with_lifespan=False)

    async def _session_override():
        yield session or MagicMock()

    app.dependency_overrides[get_session] = _session_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _price(**overrides) -> PriceView:
    data = {
        "id": uuid.uuid4(),
        "currency": "XTR",
        "amount": 100,
        "discount_percent": 0,
        "is_active": True,
    }
    return PriceView(**{**data, **overrides})


def _product(**overrides) -> ProductView:
    data = {
        "code": "tarot_wish",
        "kind": "tarot_reading",
        "title": "Расклад на желание",
        "is_active": True,
        "prices": (_price(),),
    }
    return ProductView(**{**data, **overrides})


class TestPanelDisabled:
    async def test_no_password_hides_panel(self):
        async with await _client(_settings(admin_password="")) as client:
            assert (await client.get("/admin")).status_code == 404
            assert (await client.get("/admin/login")).status_code == 404
            assert (await client.post("/admin/login", data={})).status_code == 404

    def test_is_enabled_ignores_whitespace(self):
        assert not auth.is_enabled(_settings(admin_password="   "))
        assert auth.is_enabled(_settings())


class TestLogin:
    async def test_login_page_renders(self):
        async with await _client(_settings()) as client:
            response = await client.get("/admin/login")
        assert response.status_code == 200
        assert "Панель управления каталогом" in response.text

    async def test_wrong_password_rejected(self):
        async with await _client(_settings()) as client:
            response = await client.post(
                "/admin/login",
                data={"username": "astrid", "password": "неверный"},
            )
        assert response.status_code == 401
        assert auth.COOKIE_NAME not in response.cookies

    async def test_correct_password_sets_cookie(self):
        async with await _client(_settings()) as client:
            response = await client.post(
                "/admin/login",
                data={"username": "astrid", "password": _PASSWORD},
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"
        assert auth.verify_session(response.cookies[auth.COOKIE_NAME], _settings())

    async def test_cookie_from_login_opens_catalog(self):
        """Кука доезжает обратно: без padding её не приходится брать в кавычки."""
        with (
            patch(f"{_ROUTERS}.service.list_catalog", AsyncMock(return_value=[])),
            patch(f"{_ROUTERS}.service.list_prizes", AsyncMock(return_value=[])),
        ):
            async with await _client(_settings()) as client:
                await client.post(
                    "/admin/login",
                    data={"username": "astrid", "password": _PASSWORD},
                )
                catalog = await client.get("/admin")
        assert catalog.status_code == 200
        assert "Astra ✨ каталог" in catalog.text

    async def test_lockout_after_repeated_failures(self):
        async with await _client(_settings()) as client:
            for _ in range(10):
                await client.post("/admin/login", data={"username": "astrid", "password": "нет"})
            blocked = await client.post(
                "/admin/login",
                data={"username": "astrid", "password": _PASSWORD},
            )
        assert blocked.status_code == 429

    async def test_anonymous_catalog_redirects_to_login(self):
        async with await _client(_settings()) as client:
            response = await client.get("/admin")
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")


class TestSession:
    def test_foreign_signature_rejected(self):
        token = auth.issue_session(_settings())
        body, _, signature = token.partition(".")
        assert not auth.verify_session(f"{body}.{signature[:-2]}xx", _settings())
        assert not auth.verify_session(token, _settings(admin_session_secret="другой"))

    def test_expired_session_rejected(self):
        assert not auth.verify_session(
            auth.issue_session(_settings(admin_session_hours=-1)),
            _settings(admin_session_hours=-1),
        )

    def test_garbage_cookie_rejected(self):
        for token in (None, "", "нет-точки", "!!!.!!!"):
            assert not auth.verify_session(token, _settings())


class TestCatalogPage:
    async def test_shows_products_and_prizes(self):
        settings = _settings()
        prize = PrizeView(
            id=uuid.uuid4(),
            product_code="tarot_wish",
            product_title="Расклад на желание",
            discount_percent=100,
            weight=5,
            is_active=True,
        )
        with (
            patch(f"{_ROUTERS}.service.list_catalog", AsyncMock(return_value=[_product()])),
            patch(f"{_ROUTERS}.service.list_prizes", AsyncMock(return_value=[prize])),
        ):
            async with await _client(settings) as client:
                client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
                response = await client.get("/admin")

        assert response.status_code == 200
        assert "Расклад на желание" in response.text
        assert "tarot_wish" in response.text
        assert "Призы колеса" in response.text

    async def test_price_update_redirects_with_message(self):
        settings = _settings()
        row = MagicMock(product_code="tarot_wish", currency="XTR", amount=120, discount_percent=10)
        row.is_active = True
        before = MagicMock(base_amount=100, discount_percent=0)
        with patch(
            f"{_ROUTERS}.service.update_price",
            AsyncMock(return_value=(row, before)),
        ) as update:
            async with await _client(settings) as client:
                client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
                response = await client.post(
                    f"/admin/prices/{uuid.uuid4()}",
                    data={"amount": "120", "discount_percent": "10", "is_active": "1"},
                )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin?ok=")
        assert update.await_args.kwargs == {
            "amount": 120,
            "discount_percent": 10,
            "is_active": True,
        }

    async def test_unchecked_toggle_disables_price(self):
        settings = _settings()
        row = MagicMock(product_code="tarot_wish", currency="XTR", amount=100, discount_percent=0)
        with patch(
            f"{_ROUTERS}.service.update_price",
            AsyncMock(return_value=(row, MagicMock(base_amount=100, discount_percent=0))),
        ) as update:
            async with await _client(settings) as client:
                client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
                await client.post(
                    f"/admin/prices/{uuid.uuid4()}",
                    data={"amount": "100", "discount_percent": "0"},
                )
        assert update.await_args.kwargs["is_active"] is False

    async def test_bad_number_shows_error_not_500(self):
        settings = _settings()
        async with await _client(settings) as client:
            client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
            response = await client.post(
                f"/admin/prices/{uuid.uuid4()}",
                data={"amount": "сто", "discount_percent": "0"},
            )
        assert response.status_code == 303
        assert "err=" in response.headers["location"]

    async def test_anonymous_post_does_not_touch_catalog(self):
        with patch(f"{_ROUTERS}.service.update_price", AsyncMock()) as update:
            async with await _client(_settings()) as client:
                response = await client.post(
                    f"/admin/prices/{uuid.uuid4()}",
                    data={"amount": "1", "discount_percent": "0"},
                )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")
        update.assert_not_awaited()


class TestSections:
    async def test_prototypes_render_with_nav(self):
        settings = _settings()
        async with await _client(settings) as client:
            client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
            for slug in ("people", "payments", "support", "broadcasts"):
                response = await client.get(f"/admin/{slug}")
                assert response.status_code == 200, slug
                # каркас на месте: меню и честная пометка «это макет»
                assert 'nav class="side"' in response.text, slug
                assert 'class="proto"' in response.text, slug

    async def test_metrics_page_is_live_not_prototype(self):
        """Метрики уехали из макетов: страница считает по базе."""
        from astra.admin.mockups import PROTOTYPES

        assert "metrics" not in PROTOTYPES

        settings = _settings()
        dashboard = MagicMock(
            days=7,
            money=MagicMock(revenue=4830, payments=41, buyers=30, refunds=0,
                            refunded_amount=0, discount_given=120, average_check=118),
            previous=MagicMock(revenue=4100, payments=35),
            revenue_days=[(date(2026, 7, 29), 1270)],
            funnel=[SimpleNamespace(name="Запустили бота", people=10, share=lambda total: 100.0)],
            products=[SimpleNamespace(action="day_card", title="Карта дня", uses=14,
                                      users=6, paid_uses=0, free_uses=14)],
            audience=MagicMock(dau=5, wau=9, mau=12, stickiness=41.7, retention={1: 50.0, 7: 20.0, 30: 0.0}),
            streaks=[("1", 5), ("30+", 1)],
            wheel=MagicMock(spins=4, spins_free=4, spins_paid=0, wins_total=4,
                            wins_activated=1, wins_expired=2, activation_share=25.0,
                            revenue_from_prizes=150, prize_rows=(("tarot_wish −100%", 2, 50.0, 33.3),)),
            referrals=MagicMock(invited=1, organic=6, invited_conversion=100.0, organic_conversion=16.7),
            repeat=MagicMock(paying_users=3, repeat_users=1, repeat_share=33.3, revenue_per_buyer=160),
            signups=2,
            failed=(1, 16),
            days_to_purchase=2.5,
        )
        timeline = SimpleNamespace(
            grain="day",
            buckets=[SimpleNamespace(start=date(2026, 7, 29), label="29.07", current=True)],
            people=[5],
            products=[14],
            calls=[31],
            money=[1270],
        )
        spend = SimpleNamespace(
            calls=31, failed=1, prompt_tokens=90000, completion_tokens=42000,
            cost_usd=0.42, unknown_tokens=2, tokens=132000,
        )
        with (
            patch(f"{_ROUTERS}.metrics_queries.collect", AsyncMock(return_value=dashboard)),
            patch(f"{_ROUTERS}.timeline_queries.collect", AsyncMock(return_value=timeline)),
            patch(f"{_ROUTERS}.timeline_queries.llm_spend", AsyncMock(return_value=spend)),
            patch(
                f"{_ROUTERS}.timeline_queries.spend_by_product",
                AsyncMock(return_value=[("tarot_reading", 24, 0.31)]),
            ),
        ):
            async with await _client(settings) as client:
                client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
                response = await client.get("/admin/metrics?grain=day")

        assert response.status_code == 200
        assert 'class="proto"' not in response.text  # бейджа макета нет
        assert "Карта дня" in response.text
        assert "липкость 41.7%" in response.text
        assert "вызовов модели" in response.text  # вторая линия на графике генераций
        assert "$0.31" in response.text  # расход на модели по продуктам

    async def test_unknown_section_is_404(self):
        settings = _settings()
        async with await _client(settings) as client:
            client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
            assert (await client.get("/admin/налоги")).status_code == 404

    async def test_sections_need_login(self):
        async with await _client(_settings()) as client:
            response = await client.get("/admin/metrics")
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")

    async def test_login_route_wins_over_section(self):
        """`/admin/login` не должен уехать в обработчик разделов."""
        async with await _client(_settings()) as client:
            response = await client.get("/admin/login")
        assert response.status_code == 200
        assert "Панель управления каталогом" in response.text


class TestStandaloneApp:
    """Панель должна уметь работать отдельным сервисом без остального API."""

    async def test_serves_panel_without_api_routes(self):
        from astra.admin.app import create_admin_app

        get_settings.cache_clear()
        with patch("astra.core.config.Settings", return_value=_settings()):
            app = create_admin_app(with_lifespan=False)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/admin/login")).status_code == 200
            # маршруты бота и API в отдельный сервис не едут
            assert (await client.post("/v1/telegram/webhook")).status_code == 404

    def test_does_not_import_telegram(self):
        """Панель не тянет aiogram: в своём процессе бота не будет."""
        import astra.admin.app
        import astra.admin.mockups
        import astra.admin.render
        import astra.admin.routers
        import astra.admin.service

        modules = (
            astra.admin.app,
            astra.admin.routers,
            astra.admin.service,
            astra.admin.render,
            astra.admin.mockups,
        )
        import ast

        for module in modules:
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported += [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            forbidden = [name for name in imported if "aiogram" in name or "astra.telegram" in name]
            assert not forbidden, f"{module.__name__}: {forbidden}"


class TestValidation:
    async def test_zero_price_rejected(self):
        with pytest.raises(AdminError):
            await update_price(AsyncMock(), uuid.uuid4(), amount=0, discount_percent=0, is_active=True)

    async def test_discount_above_hundred_rejected(self):
        with pytest.raises(AdminError):
            await update_price(AsyncMock(), uuid.uuid4(), amount=10, discount_percent=101, is_active=True)

    async def test_free_price_allowed(self):
        session = AsyncMock()
        session.get = AsyncMock(
            return_value=MagicMock(currency="XTR", amount=100, discount_percent=0),
        )
        row, _ = await update_price(
            session, uuid.uuid4(), amount=100, discount_percent=100, is_active=True,
        )
        assert row.discount_percent == 100

    async def test_missing_row_is_admin_error(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        with pytest.raises(AdminError):
            await update_price(session, uuid.uuid4(), amount=10, discount_percent=0, is_active=True)

    async def test_prize_weight_must_be_positive(self):
        with pytest.raises(AdminError):
            await update_prize(AsyncMock(), uuid.uuid4(), discount_percent=50, weight=0, is_active=True)

    async def test_prize_zero_discount_rejected(self):
        with pytest.raises(AdminError):
            await update_prize(AsyncMock(), uuid.uuid4(), discount_percent=0, weight=1, is_active=True)


class TestRender:
    def test_title_is_escaped(self):
        html = render.catalog_page([_product(title="<script>alert(1)</script>")], [])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_flash_from_query_is_escaped(self):
        html = render.catalog_page([], [], flash="<img src=x onerror=alert(1)>", flash_error=True)
        assert "<img src=x" not in html

    def test_discount_shows_old_and_new_price(self):
        html = render.catalog_page([_product(prices=(_price(amount=100, discount_percent=30),))], [])
        assert "<s>100 ⭐</s>70 ⭐" in html

    def test_free_price_labelled(self):
        html = render.catalog_page([_product(prices=(_price(discount_percent=100),))], [])
        assert "бесплатно" in html

    def test_product_without_price_warns(self):
        html = render.catalog_page([_product(prices=())], [])
        assert "Цены в каталоге нет" in html

    def test_inactive_prize_shows_no_chance(self):
        prize = PrizeView(
            id=uuid.uuid4(),
            product_code="tarot_year",
            product_title="Расклад на год",
            discount_percent=20,
            weight=12,
            is_active=False,
        )
        html = render.catalog_page([], [prize])
        assert "не в колесе" in html
        assert "шанс" not in html

    def test_prize_chance_is_share_of_weight(self):
        prize = PrizeView(
            id=uuid.uuid4(),
            product_code="tarot_wish",
            product_title="Расклад",
            discount_percent=50,
            weight=25,
            is_active=True,
        )
        assert prize.chance_percent(100) == 25.0
        assert prize.chance_percent(0) == 0.0


class TestLlmPrices:
    """Цены моделей правятся из панели: они меняются чаще, чем выходят релизы."""

    def _price(self, **overrides):
        from decimal import Decimal

        from astra.admin.service import LlmPriceView

        data = {
            "model": "deepseek-v4-flash",
            "input_per_million": Decimal("0.28"),
            "output_per_million": Decimal("0.42"),
            "note": "актуально на 2026-07-29",
            "in_use": True,
        }
        return LlmPriceView(**{**data, **overrides})

    def test_sample_cost_shown_next_to_price(self):
        from astra.admin.render_settings import settings_page

        html = settings_page([self._price()])
        assert "deepseek-v4-flash" in html
        assert "разбор ≈ $0.0015" in html  # 3000 входных + 1500 выходных

    def test_model_without_price_is_flagged(self):
        from decimal import Decimal

        from astra.admin.render_settings import settings_page

        html = settings_page(
            [self._price(model="qwen:free", input_per_million=Decimal(0), output_per_million=Decimal(0))],
        )
        assert "Без цены работают модели" in html
        assert "qwen:free" in html

    async def test_save_updates_price_and_drops_cache(self):
        settings = _settings()
        row = MagicMock(model="deepseek-v4-flash")
        row.input_per_million = "0.30"
        row.output_per_million = "0.50"
        with patch(f"{_ROUTERS}.service.save_llm_price", AsyncMock(return_value=row)) as save:
            async with await _client(settings) as client:
                client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
                response = await client.post(
                    "/admin/llm-prices/deepseek-v4-flash",
                    data={"input": "0.30", "output": "0.50", "note": "новый прайс"},
                )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/settings?ok=")
        assert save.await_args.kwargs["input_raw"] == "0.30"

    async def test_bad_number_shows_error(self):
        settings = _settings()
        async with await _client(settings) as client:
            client.cookies.set(auth.COOKIE_NAME, auth.issue_session(settings))
            response = await client.post(
                "/admin/llm-prices/some-model",
                data={"input": "дорого", "output": "0.5"},
            )
        assert response.status_code == 303
        assert "err=" in response.headers["location"]

    async def test_anonymous_cannot_change_prices(self):
        with patch(f"{_ROUTERS}.service.save_llm_price", AsyncMock()) as save:
            async with await _client(_settings()) as client:
                response = await client.post(
                    "/admin/llm-prices/x", data={"input": "1", "output": "1"},
                )
        assert response.headers["location"].startswith("/admin/login")
        save.assert_not_awaited()
