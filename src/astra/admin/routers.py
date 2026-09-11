"""Роуты панели: логин и правка каталога.

Формы отправляются обычным urlencoded-постом и отвечают редиректом (PRG):
обновление страницы после сохранения ничего не повторяет. Тело формы разбираем
сами (`_form`): starlette для `request.form()` требует python-multipart, а ради
пяти текстовых полей тянуть зависимость незачем.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.admin import auth, service
from astra.admin import metrics as metrics_queries
from astra.admin.mockups import PROTOTYPES
from astra.admin import queue as admin_queue
from astra.admin import timeline as timeline_queries
from astra.admin.render_metrics import metrics_page
from astra.admin.timeline import Grain
from astra.admin import ledger
from astra.admin import stars as stars_queries
from astra.admin.render_ledger import ledger_page
from astra.admin.render_stars import stars_page
from astra.admin.render_queue import queue_page
from astra.admin.render_broadcast import broadcast_page
from astra.admin.render_settings import settings_page
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


@router.get("/metrics")
async def metrics(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Живые метрики: деньги, воронка, продукты, аудитория, колесо, рефералы."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        grain = Grain(request.query_params.get("grain", Grain.DAY))
    except ValueError:
        grain = Grain.DAY

    # Таблицы под графиками считаем за то же окно, что показывают столбики.
    days = {Grain.DAY: 30, Grain.WEEK: 84, Grain.MONTH: 365}[grain]
    since = datetime.now(UTC) - timedelta(days=days)

    dashboard = await metrics_queries.collect(session, days)
    line = await timeline_queries.collect(session, grain)
    spend = await timeline_queries.llm_spend(session, since)
    spend_rows = await timeline_queries.spend_by_product(session, since)
    return HTMLResponse(metrics_page(dashboard, line, spend, spend_rows))


@router.get("/queue")
async def queue(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Упавшие, зависшие и неприкаянные заказы — с кнопками починки."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    problems = await admin_queue.list_problems(session)
    error = request.query_params.get("err")
    return HTMLResponse(
        queue_page(
            problems,
            admin_queue.summarize(problems),
            flash=error or request.query_params.get("ok"),
            flash_error=bool(error),
        ),
    )


@router.post("/queue/{target}/{entity_id}/{action}")
async def queue_action(
    target: str,
    entity_id: uuid.UUID,
    action: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Повторить генерацию или вернуть звёзды. Обе операции необратимы по-своему."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        kind = admin_queue.Target(target)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None

    try:
        if action == "retry":
            message = await admin_queue.retry(session, kind, entity_id)
        elif action == "refund":
            message = await admin_queue.refund(session, kind, entity_id)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except AdminError as exc:
        return _redirect("/admin/queue", err=str(exc))

    return _redirect("/admin/queue", ok=message)


@router.get("/settings")
async def settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Цены моделей: по ним считается себестоимость каждого вызова."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    prices = await service.list_llm_prices(session)
    error = request.query_params.get("err")
    return HTMLResponse(
        settings_page(
            prices,
            flash=error or request.query_params.get("ok"),
            flash_error=bool(error),
        ),
    )


@router.post("/llm-prices")
@router.post("/llm-prices/{model}")
async def save_llm_price(
    request: Request,
    model: str = "",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Завести модель или поправить её цену."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    try:
        form = await _form(request)
        row = await service.save_llm_price(
            session,
            model or form.get("model", ""),
            input_raw=form.get("input", ""),
            output_raw=form.get("output", ""),
            note=form.get("note"),
        )
    except AdminError as exc:
        return _redirect("/admin/settings", err=str(exc))

    log.info(
        "admin.llm_price_saved",
        model=row.model,
        input_per_million=str(row.input_per_million),
        output_per_million=str(row.output_per_million),
    )
    return _redirect("/admin/settings", ok=f"{row.model}: цена сохранена.")


@router.get("/stars")
async def stars(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Настоящий баланс Telegram против обязательств внутреннего кошелька."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    return HTMLResponse(stars_page(await stars_queries.collect(session)))


@router.get("/payments")
async def payments(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Лента событий: оплаты, выдачи, возвраты, черновики, аварии, колесо."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    params = request.query_params

    def _set(name: str) -> set[str]:
        raw = params.get(name, "")
        return {piece for piece in raw.split(",") if piece}

    try:
        page = int(params.get("page", 1))
    except ValueError:
        page = 1

    period = params.get("period", "today")
    filters = ledger.Filters(
        period=period if period in ledger.PERIODS else "today",
        kinds=_set("kinds"),
        products=_set("products"),
        query=params.get("q", "").strip(),
        page=page,
    )

    events, totals, total = await ledger.collect(session, filters)
    titles = await ledger.product_titles(session)
    products = sorted(titles.items(), key=lambda item: item[1])
    return HTMLResponse(ledger_page(events, totals, filters, products))


# --- рассылки -----------------------------------------------------------------


async def _current_draft(session: AsyncSession):
    """Черновик рассылки один: панелью пользуется один человек."""
    from astra.broadcasts.models import Broadcast, BroadcastStatus

    row = await session.execute(
        select(Broadcast)
        .where(Broadcast.status == BroadcastStatus.DRAFT)
        .order_by(Broadcast.created_at.desc())
        .limit(1),
    )
    draft = row.scalar_one_or_none()
    if draft is None:
        draft = Broadcast(source_text="", final_text="", criteria={})
        session.add(draft)
        await session.flush()
    return draft


def _criteria_from(form: dict[str, str], raw: dict[str, list[str]]):
    from astra.broadcasts.audience import Criteria

    def number(name: str) -> int | None:
        value = (form.get(name) or "").strip()
        return int(value) if value.isdigit() else None

    return Criteria(
        zodiac=set(raw.get("zodiac", [])),
        used_products=set(raw.get("used_products", [])),
        active_within_days=number("active_within_days"),
        sleeping_since_days=number("sleeping_since_days"),
        joined_within_days=number("joined_within_days"),
        money=form.get("money", ""),
        abandoned_draft="abandoned_draft" in form,
        unclaimed_prize="unclaimed_prize" in form,
        exclude_paid="exclude_paid" in form,
        exclude_active_within_days=number("exclude_active_within_days"),
    )


async def _broadcast_screen(session: AsyncSession, flash=None, flash_error=False) -> Response:
    from astra.broadcasts import audience as audience_module
    from astra.broadcasts import service as broadcast_service
    from astra.broadcasts.audience import Criteria
    from astra.broadcasts.editor import check

    draft = await _current_draft(session)
    criteria = Criteria(**{k: set(v) if isinstance(v, list) else v for k, v in draft.criteria.items()})
    size = draft.audience_size or None
    if criteria.is_empty() and not draft.direct_recipients:
        size = None

    titles = await ledger.product_titles(session)
    return HTMLResponse(
        broadcast_page(
            criteria=criteria,
            products=sorted(titles.items(), key=lambda item: item[1]),
            audience_size=size,
            source_text=draft.source_text,
            final_text=draft.final_text,
            warnings=check(draft.final_text) if draft.final_text else (),
            buttons=draft.buttons,
            personalize=draft.personalize,
            use_ai=draft.used_ai,
            history=await broadcast_service.history(session),
            flash=flash,
            flash_error=flash_error,
        ),
    )


@router.get("/broadcasts")
async def broadcasts(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect
    error = request.query_params.get("err")
    return await _broadcast_screen(
        session,
        flash=error or request.query_params.get("ok"),
        flash_error=bool(error),
    )


@router.post("/broadcasts/count")
async def broadcasts_count(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Посчитать охват до отправки: вслепую рассылку не запускают."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    from astra.broadcasts import audience as audience_module

    raw = parse_qs((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)
    form = {key: values[-1] for key, values in raw.items()}
    criteria = _criteria_from(form, raw)

    draft = await _current_draft(session)
    direct = [
        int(piece.strip())
        for piece in (form.get("direct") or "").split(",")
        if piece.strip().isdigit()
    ]
    draft.direct_recipients = direct
    draft.criteria = {
        key: sorted(value) if isinstance(value, set) else value
        for key, value in criteria.__dict__.items()
        if value
    }
    draft.audience_size = (
        len(direct) if direct else await audience_module.count(session, criteria)
    )
    return _redirect("/admin/broadcasts", ok=f"Под фильтры попадает {draft.audience_size} чел.")


@router.post("/broadcasts/compose")
async def broadcasts_compose(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Собрать сообщение: с редактором или без, но всегда с проверкой разметки."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    from astra.broadcasts.editor import check, improve

    form = await _form(request)
    text = (form.get("text") or "").strip()
    if not text:
        return _redirect("/admin/broadcasts", err="Пустой текст — нечего отправлять.")

    draft = await _current_draft(session)
    draft.source_text = text
    draft.personalize = "personalize" in form
    draft.used_ai = "use_ai" in form

    if draft.used_ai:
        result = await improve(text, personalize=draft.personalize)
        draft.final_text = result.text
        message = "Текст переписан — посмотри предпросмотр."
    else:
        draft.final_text = text
        message = "Текст сохранён без редактора."

    problems = check(draft.final_text)
    return _redirect(
        "/admin/broadcasts",
        ok=None if problems else message,
        err="; ".join(problems) if problems else None,
    )


@router.post("/broadcasts/button")
async def broadcasts_button(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    form = await _form(request)
    draft = await _current_draft(session)
    button = {
        "section": form.get("section", ""),
        "url": form.get("url", ""),
        "title": form.get("title", ""),
    }
    if not button["section"] and not button["url"]:
        return _redirect("/admin/broadcasts", err="Выбери раздел или укажи ссылку.")

    draft.buttons = [*draft.buttons, button]
    return _redirect("/admin/broadcasts", ok="Кнопка добавлена.")


@router.post("/broadcasts/test")
async def broadcasts_test(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Пробное сообщение себе: предпросмотр в браузере не покажет живой Telegram."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    settings = get_settings()
    chat_id = settings.admin_test_chat_id or settings.telegram_admin_group_id
    if not chat_id:
        return _redirect("/admin/broadcasts", err="Некуда слать: задай ADMIN_TEST_CHAT_ID.")

    draft = await _current_draft(session)
    if not draft.final_text:
        return _redirect("/admin/broadcasts", err="Сначала собери сообщение.")

    from astra.broadcasts.keyboards import broadcast_keyboard
    from astra.workers.telegram_send import send_telegram_html

    try:
        await send_telegram_html(
            chat_id,
            draft.final_text,
            reply_markup=broadcast_keyboard(draft.buttons),
            keyboard_zone=None,
        )
    except Exception as exc:  # noqa: BLE001 — причину показываем на экране
        return _redirect("/admin/broadcasts", err=f"Telegram не принял: {type(exc).__name__}")

    return _redirect("/admin/broadcasts", ok="Отправил тебе — посмотри в Telegram.")


@router.post("/broadcasts/send")
async def broadcasts_send(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Запустить рассылку: фиксируем получателей и отдаём воркеру."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    from astra.broadcasts import service as broadcast_service
    from astra.messaging.publisher import publish_broadcast_send

    draft = await _current_draft(session)
    if not draft.final_text:
        return _redirect("/admin/broadcasts", err="Сначала собери сообщение.")

    size = await broadcast_service.prepare(session, draft)
    if not size:
        return _redirect("/admin/broadcasts", err="Под фильтры не попал никто.")

    await session.commit()  # воркер должен увидеть строки получателей
    await publish_broadcast_send(draft.id)
    log.info("admin.broadcast_started", broadcast_id=draft.id, audience=size)
    return _redirect("/admin/broadcasts", ok=f"Рассылка пошла: {size} получателей.")


@router.get("/broadcasts/{broadcast_id}/retry")
async def broadcasts_retry(
    broadcast_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Повторить недошедшим — заблокировавших не трогаем, им не дойдёт."""
    redirect = _guard(request)
    if redirect is not None:
        return redirect

    from astra.broadcasts import service as broadcast_service
    from astra.broadcasts.models import Broadcast, BroadcastStatus
    from astra.messaging.publisher import publish_broadcast_send

    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    count = await broadcast_service.reset_failed(session, broadcast_id)
    if not count:
        return _redirect("/admin/broadcasts", err="Недошедших нет.")

    broadcast.status = BroadcastStatus.SENDING
    await session.commit()
    await publish_broadcast_send(broadcast_id)
    return _redirect("/admin/broadcasts", ok=f"Повторяю для {count} чел.")


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
