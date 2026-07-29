"""Роуты панели: логин и правка каталога.

Формы отправляются обычным urlencoded-постом и отвечают редиректом (PRG):
обновление страницы после сохранения ничего не повторяет. Тело формы разбираем
сами (`_form`): starlette для `request.form()` требует python-multipart, а ради
пяти текстовых полей тянуть зависимость незачем.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from astra.admin import auth, service
from astra.admin.mockups import PROTOTYPES
from astra.admin.render import catalog_page, login_page
from astra.admin.service import AdminError
from astra.core.config import Settings, get_settings
from astra.core.observability import get_logger
from astra.db.session import get_session

log = get_logger(__name__)


def require_panel() -> Settings:
    """Панель без ADMIN_PASSWORD не существует — отвечаем 404, а не 401."""
    settings = get_settings()
    if not auth.is_enabled(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return settings


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    include_in_schema=False,
    dependencies=[Depends(require_panel)],
)

_LOGIN_URL = "/admin/login"


def _redirect(url: str, *, ok: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("ok", ok), ("err", err)) if v}
    target = f"{url}?{urlencode(params)}" if params else url
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


_MAX_FORM_BYTES = 64 * 1024


async def _form(request: Request) -> dict[str, str]:
    """Поля urlencoded-формы; при повторе ключа берём последнее значение."""
    raw = await request.body()
    if len(raw) > _MAX_FORM_BYTES:
        raise AdminError("Слишком большая форма.")
    parsed = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _int_field(form: dict[str, str], name: str, label: str) -> int:
    raw = (form.get(name) or "").strip()
    try:
        return int(raw)
    except ValueError:
        raise AdminError(f"«{label}» — целое число, а пришло «{raw}».") from None


def _guard(request: Request) -> RedirectResponse | None:
    """Редирект на логин, если сессии нет."""
    if auth.is_authenticated(request):
        return None
    return _redirect(_LOGIN_URL, err="Нужно войти.")


@router.get("/login")
async def login_form(request: Request) -> Response:
    if auth.is_authenticated(request):
        return _redirect("/admin")
    return HTMLResponse(login_page(error=request.query_params.get("err")))


@router.post("/login")
async def login(request: Request, settings: Settings = Depends(require_panel)) -> Response:
    ip = auth.client_ip(request)
    locked = auth.lockout_seconds_left(ip)
    if locked:
        log.warning("admin.login_locked", ip=ip, seconds_left=locked)
        minutes = max(1, locked // 60)
        return HTMLResponse(
            login_page(error=f"Слишком много попыток. Подождите {minutes} мин."),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        form = await _form(request)
    except AdminError as exc:
        return HTMLResponse(
            login_page(error=str(exc)),
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    if not auth.check_credentials(username, password, settings):
        auth.register_failure(ip)
        log.warning("admin.login_failed", ip=ip)
        return HTMLResponse(
            login_page(error="Неверный логин или пароль."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    auth.reset_failures(ip)
    log.info("admin.login_ok", ip=ip)
    response = _redirect("/admin")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_session(settings),
        max_age=settings.admin_session_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.admin_cookie_secure,
        path="/admin",
    )
    return response


@router.post("/logout")
async def logout() -> Response:
    response = _redirect(_LOGIN_URL, ok="Вы вышли.")
    response.delete_cookie(auth.COOKIE_NAME, path="/admin")
    return response


@router.get("")
async def catalog(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    products = await service.list_catalog(session)
    prizes = await service.list_prizes(session)
    error = request.query_params.get("err")
    return HTMLResponse(
        catalog_page(
            products,
            prizes,
            flash=error or request.query_params.get("ok"),
            flash_error=bool(error),
        ),
    )


@router.get("/{section}")
async def prototype_section(section: str, request: Request) -> Response:
    """Макеты будущих разделов: вёрстка на выдуманных данных, в базу не ходят."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    page = PROTOTYPES.get(section)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return HTMLResponse(page())


@router.post("/prices/{price_id}")
async def save_price(
    price_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        form = await _form(request)
        amount = _int_field(form, "amount", "Цена")
        discount = _int_field(form, "discount_percent", "Скидка")
        row, before = await service.update_price(
            session,
            price_id,
            amount=amount,
            discount_percent=discount,
            is_active="is_active" in form,
        )
    except AdminError as exc:
        return _redirect("/admin", err=str(exc))

    log.info(
        "admin.price_updated",
        product_code=row.product_code,
        currency=row.currency,
        amount_before=before.base_amount,
        amount_after=row.amount,
        discount_before=before.discount_percent,
        discount_after=row.discount_percent,
        is_active=row.is_active,
    )
    return _redirect("/admin", ok=f"{row.product_code}: цена обновлена.")


@router.post("/products/{product_code}/prices")
async def add_price(
    product_code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        form = await _form(request)
        row = await service.create_price(
            session,
            product_code,
            currency=str(form.get("currency") or ""),
            amount=_int_field(form, "amount", "Цена"),
            discount_percent=_int_field(form, "discount_percent", "Скидка"),
        )
    except AdminError as exc:
        return _redirect("/admin", err=str(exc))

    log.info(
        "admin.price_created",
        product_code=row.product_code,
        currency=row.currency,
        amount=row.amount,
        discount=row.discount_percent,
    )
    return _redirect("/admin", ok=f"{product_code}: добавлена цена в {row.currency}.")


@router.post("/products/{product_code}/toggle")
async def toggle_product(
    product_code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        form = await _form(request)
        is_active = str(form.get("is_active") or "0") == "1"
        await service.set_product_active(session, product_code, is_active=is_active)
    except AdminError as exc:
        return _redirect("/admin", err=str(exc))

    log.info("admin.product_toggled", product_code=product_code, is_active=is_active)
    state = "включён" if is_active else "выключен"
    return _redirect("/admin", ok=f"{product_code}: товар {state}.")


@router.post("/prizes/{prize_id}")
async def save_prize(
    prize_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        form = await _form(request)
        prize = await service.update_prize(
            session,
            prize_id,
            discount_percent=_int_field(form, "discount_percent", "Скидка"),
            weight=_int_field(form, "weight", "Вес сектора"),
            is_active="is_active" in form,
        )
    except AdminError as exc:
        return _redirect("/admin", err=str(exc))

    log.info(
        "admin.prize_updated",
        product_code=prize.product_code,
        discount=prize.discount_percent,
        weight=prize.weight,
        is_active=prize.is_active,
    )
    return _redirect("/admin", ok=f"{prize.product_code}: приз обновлён.")
