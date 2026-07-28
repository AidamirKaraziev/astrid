"""Тесты админ-панели: выключена без пароля, вход, правки каталога, экранирование."""

import uuid
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
