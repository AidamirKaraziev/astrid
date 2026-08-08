"""Воронка регистрации целиком: `/start` → онбординг → профиль в базе.

Почему именно так, а не через `AsyncMock`, как остальные тесты бота:
регистрация уже ломалась в слое БД (сессия и ленивая подгрузка профиля), и
восемь сотен мок-тестов остались зелёными — мок отвечает моком, ошибке
неоткуда взяться. Здесь всё настоящее: живой Postgres, боевой `Dispatcher`
со всеми роутерами и middleware, реальный справочник городов. Ненастоящий
только транспорт Telegram (`tests/fake_telegram.py`) и очередь RabbitMQ.

Эти тесты — страховка рекламного бюджета: пока они зелёные, человек,
пришедший по объявлению, доходит от `/start` до готового профиля.
"""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from conftest import new_test_telegram_id
from fake_telegram import BotHarness, assert_said, build_bot, build_test_dispatcher

from astra.telegram.button_texts import BTN_GENDER_FEMALE, BTN_NATAL, BTN_PROFILE
from astra.telegram.handlers.natal import CB_NATAL_SUBJECT_SELF
from astra.telegram.handlers.places import NEARBY_CITY_KM
from astra.users.gender import GENDER_FEMALE

pytestmark = pytest.mark.usefixtures("purge_test_users")

BEGIN_BUTTON = "Зови меня Аида"
BIRTH_DATE_INPUT = "15.03.1990"
BIRTH_DATE = date(1990, 3, 15)
BIRTH_CITY_QUERY = "Москва"
# Выдуманное название: проверяем не «ничего не нашла», а что человек не
# оказывается в тупике — ему предлагают похожие варианты и путь вперёд.
UNKNOWN_CITY_QUERY = "Ктулхуград"


@pytest.fixture
async def enqueued_predictions():
    """RabbitMQ в CI нет: перехватываем публикацию, но путь до неё живой."""
    with patch(
        "astra.services.prediction_delivery_service.enqueue_prediction_pipeline",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
async def welcome_video_without_cache():
    """Не трогаем общий ключ Redis с file_id приветственного видео.

    Иначе тест записал бы выдуманный file_id, и живой бот стал бы слать
    сломанное видео новым людям.
    """
    with (
        patch(
            "astra.telegram.handlers.start._get_cached_welcome_video_file_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "astra.telegram.handlers.start._cache_welcome_video_file_id",
            new_callable=AsyncMock,
        ),
    ):
        yield


@pytest.fixture
async def no_geonames_download():
    """Страховка от похода в интернет за справочником городов.

    Если сеялка городов когда-нибудь перестанет работать, тест должен упасть
    с внятной ошибкой, а не висеть пять минут на скачивании RU.zip.
    """

    async def _fail(*args, **kwargs):
        msg = "тест полез качать GeoNames — значит, справочник городов пуст"
        raise AssertionError(msg)

    with patch("astra.telegram.handlers.places.ensure_places_catalog", new=_fail):
        yield


@pytest.fixture
async def bot_harness(
    db_engine,
    places_catalog,
    no_geonames_download,
    enqueued_predictions,
    welcome_video_without_cache,
) -> BotHarness:
    bot = build_bot()
    harness = await build_test_dispatcher(bot)
    try:
        yield harness
    finally:
        await bot.session.close()


async def load_user(session, telegram_id: int):
    from astra.users.models import User

    result = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(User.profile), selectinload(User.referral_code)),
    )
    return result.scalar_one_or_none()


def assert_welcome_screen(text: str) -> None:
    """Первый экран: здоровается Астрид и спрашивает, как обращаться.

    Проверяем смысл, а не вёрстку: текст приветствия правится часто, и тест,
    приколоченный к конкретному <b>, ломается на каждой правке запятой — а
    сломанный тест воронки перестают читать.
    """
    plain = re.sub(r"<[^>]+>", "", text).lower()
    assert "астрид" in plain, f"на первом экране никто не представился: {text!r}"
    assert "обращаться" in plain, f"не спросили, как обращаться: {text!r}"


def _callbacks(calls: list, prefix: str) -> list[str]:
    return [
        data for call in calls for data in call.callback_data() if data.startswith(prefix)
    ]


async def reach_place_buttons(
    harness: BotHarness,
    telegram_id: int,
    query: str = BIRTH_CITY_QUERY,
) -> str:
    """Ввести город и дойти до кнопок мест, пройдя шаг региона, если он есть.

    Тёзок много — бот сначала спрашивает регион; на маленьком справочнике в CI
    того же города может быть один, и шаг пропускается. Тест обязан работать
    в обоих случаях, иначе он проверяет не воронку, а размер базы.
    """
    calls = await harness.send(query, telegram_id=telegram_id)

    regions = _callbacks(calls, "place:region:")
    if regions:
        assert "В каком регионе" in calls[0].text
        calls = await harness.click(regions[0], telegram_id=telegram_id)

    picks = _callbacks(calls, "place:pick:")
    assert picks, f"справочник не отдал места: {[c.text for c in calls]}"
    return picks[0]


async def register_fully(
    harness: BotHarness,
    telegram_id: int,
    *,
    start_command: str = "/start",
) -> None:
    """Весь путь новичка: старт → как обращаться → пол. Три касания."""
    await harness.send(start_command, telegram_id=telegram_id)
    await harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    await harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)


async def open_birth_place_step(
    harness: BotHarness,
    telegram_id: int,
    *,
    start_command: str = "/start",
) -> None:
    """Довести человека до вопроса «Где ты родилась?».

    Путь один на все тесты шага места: регистрация → разбор натала для себя →
    дата рождения. Дальше начинается то, что эти тесты и проверяют, — поиск,
    регионы, страницы и кнопка «не нашла свой город».
    """
    await register_fully(harness, telegram_id, start_command=start_command)
    await harness.send(BTN_NATAL, telegram_id=telegram_id)
    await harness.click(CB_NATAL_SUBJECT_SELF, telegram_id=telegram_id)
    await harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)


async def walk_to_city_list(
    harness: BotHarness,
    telegram_id: int,
    *,
    start_command: str = "/start",
) -> str:
    """Дойти до выбора места рождения и вернуть callback_data первого.

    Дверь к этому шагу теперь не в онбординге, а в продукте: человек
    открывает разбор натала, у него нет данных — и бот спрашивает сначала
    дату, потом место.
    """
    await open_birth_place_step(harness, telegram_id, start_command=start_command)
    return await reach_place_buttons(harness, telegram_id)


async def fill_birth_data(
    harness: BotHarness,
    telegram_id: int,
) -> None:
    """Профиль с полными данными рождения: через добор в разборе натала."""
    pick = await walk_to_city_list(harness, telegram_id)
    await harness.click(pick, telegram_id=telegram_id)


# --------------------------------------------------------------------------
# Главный сценарий: человек с рекламы доходит до профиля
# --------------------------------------------------------------------------


async def test_new_user_walks_from_start_to_finished_profile(
    bot_harness: BotHarness,
    db_session,
    enqueued_predictions,
) -> None:
    telegram_id = new_test_telegram_id()

    # 1. /start — приветствие, оно же вопрос об имени
    calls = await bot_harness.send("/start", telegram_id=telegram_id)
    assert "sendVideo" in [call.api_method for call in calls]
    welcome = calls[0]
    assert_welcome_screen(welcome.text)
    assert BEGIN_BUTTON in welcome.buttons(), "имя из Telegram не предложено кнопкой"

    user = await load_user(db_session, telegram_id)
    assert user is not None, "пользователь не создан на /start"
    assert user.onboarding_completed is False

    # 2. Имя — спрашиваем пол, последнее, что нужно на старте
    calls = await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    gender_prompt = assert_said(calls, "укажи свой пол")
    assert BTN_GENDER_FEMALE in gender_prompt.buttons()
    assert BTN_PROFILE in gender_prompt.text  # подсказка, где менять имя

    # 3. Пол — регистрация завершена, дальше человека никто не держит
    calls = await bot_harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)
    done = assert_said(calls, "будем знакомы")
    assert "✨ Обо мне" in done.buttons(), "после регистрации не выдали главное меню"

    # 4. В базе — профиль без астроданных: их спросят у продукта
    db_session.expire_all()
    user = await load_user(db_session, telegram_id)
    assert user is not None
    assert user.onboarding_completed is True, "флаг онбординга не выставлен"
    assert user.profile is not None, "профиль не создан"
    assert user.profile.display_name == "Аида"
    assert user.profile.gender == GENDER_FEMALE
    assert user.profile.birth_date is None, "дату рождения на старте не спрашиваем"
    assert user.profile.timezone, "без таймзоны не уйдёт рассылка"
    assert user.referral_code is not None, "реферальный код не выдан"

    # 5. Предсказание не обещаем: строить его не от чего
    enqueued_predictions.assert_not_awaited()


async def test_natal_asks_for_missing_data_and_returns_to_the_report(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Данные спрашиваются там, где понадобились, и человек не теряет продукт."""
    telegram_id = new_test_telegram_id()
    await register_fully(bot_harness, telegram_id)

    # Разбор натала для себя — данных нет, бот спрашивает дату
    await bot_harness.send(BTN_NATAL, telegram_id=telegram_id)
    calls = await bot_harness.click(CB_NATAL_SUBJECT_SELF, telegram_id=telegram_id)
    assert_said(calls, "нужна дата рождения")

    # Дата — следом место
    calls = await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)
    assert_said(calls, "Где ты родилась")

    # Место — и человек снова в разборе, а не в главном меню
    pick = await reach_place_buttons(bot_harness, telegram_id)
    calls = await bot_harness.click(pick, telegram_id=telegram_id)
    assert_said(calls, "Разбор натальной карты")

    db_session.expire_all()
    user = await load_user(db_session, telegram_id)
    assert user.profile.birth_date == BIRTH_DATE
    assert user.profile.birth_place_id is not None


async def test_birth_data_is_asked_only_once(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Названное однажды сохраняется в профиль и больше не спрашивается."""
    telegram_id = new_test_telegram_id()
    await fill_birth_data(bot_harness, telegram_id)

    await bot_harness.send(BTN_NATAL, telegram_id=telegram_id)
    calls = await bot_harness.click(CB_NATAL_SUBJECT_SELF, telegram_id=telegram_id)

    said = " ".join(call.text or "" for call in calls)
    assert "нужна дата рождения" not in said
    assert "Где ты родилась" not in said


# --------------------------------------------------------------------------
# Реклама: deep link и повторные заходы
# --------------------------------------------------------------------------


async def test_start_from_ad_deep_link_registers_user(bot_harness: BotHarness, db_session) -> None:
    """`t.me/bot?start=<payload>` — так приходят люди с рекламы.

    Полезная нагрузка не должна ни ломать регистрацию, ни съедать шаг
    приветствия: неизвестный payload просто игнорируется.
    """
    telegram_id = new_test_telegram_id()

    calls = await bot_harness.send("/start utm_ads_2026", telegram_id=telegram_id)
    assert_welcome_screen(calls[0].text)
    assert BEGIN_BUTTON in calls[0].buttons()

    user = await load_user(db_session, telegram_id)
    assert user is not None


async def test_start_with_referral_code_registers_and_links(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Приглашение друга: `/start ref_<код>` заводит и человека, и связь.

    Связь создаётся на старте, а вознаграждается только когда приглашённый
    дошёл до конца онбординга, — проверяем обе половины.
    """
    from astra.referrals import crud as referrals_crud
    from astra.referrals.models import Referral, ReferralStatus

    inviter_id = new_test_telegram_id()
    await register_fully(bot_harness, inviter_id)

    db_session.expire_all()
    inviter = await load_user(db_session, inviter_id)
    assert inviter is not None and inviter.referral_code is not None
    code = inviter.referral_code.code

    invitee_id = new_test_telegram_id()
    bot_harness.clear()
    await bot_harness.send(f"/start ref_{code}", telegram_id=invitee_id)

    invitee = await load_user(db_session, invitee_id)
    assert invitee is not None
    inviter_uuid, invitee_uuid = inviter.id, invitee.id

    async def referral_row() -> Referral | None:
        db_session.expire_all()
        return (
            await db_session.execute(select(Referral).where(Referral.invitee_id == invitee_uuid))
        ).scalar_one_or_none()

    referral = await referral_row()
    assert referral is not None, "реферальная связь не записана на /start"
    assert referral.referrer_id == inviter_uuid
    assert referral.status == ReferralStatus.PENDING

    # Приглашённый доходит до конца — только теперь бонусы.
    await bot_harness.send(BEGIN_BUTTON, telegram_id=invitee_id)
    await bot_harness.send(BTN_GENDER_FEMALE, telegram_id=invitee_id)

    referral = await referral_row()
    assert referral is not None
    assert referral.status == ReferralStatus.REWARDED, "бонус за друга не начислен"
    assert await referrals_crud.count_referrals(db_session, inviter_uuid) == 1


async def test_repeated_start_before_onboarding_does_not_duplicate_user(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Человек жмёт /start дважды подряд — это норма, а не второй аккаунт."""
    from astra.users.models import User

    telegram_id = new_test_telegram_id()
    await bot_harness.send("/start", telegram_id=telegram_id)
    calls = await bot_harness.send("/start", telegram_id=telegram_id)

    assert_welcome_screen(calls[0].text)
    count = (
        await db_session.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalars().all()
    assert len(count) == 1


async def test_start_after_registration_shows_main_menu(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Зарегистрированного не гоняем по онбордингу заново."""
    telegram_id = new_test_telegram_id()
    await register_fully(bot_harness, telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send("/start", telegram_id=telegram_id)

    menu = assert_said(calls, "Главное меню")
    assert BTN_PROFILE in menu.buttons()
    assert not any("Добро пожаловать" in call.text for call in calls)


async def test_start_restart_arg_runs_onboarding_again(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """`/start restart` — осознанный перезапуск: онбординг открывается снова."""
    telegram_id = new_test_telegram_id()
    await register_fully(bot_harness, telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send("/start restart", telegram_id=telegram_id)
    assert_welcome_screen(calls[0].text)
    assert BEGIN_BUTTON in calls[0].buttons()


# --------------------------------------------------------------------------
# Тупики: любая ошибка ввода должна оставлять путь вперёд
# --------------------------------------------------------------------------


async def test_invalid_birth_date_reprompts_and_flow_continues(
    bot_harness: BotHarness,
    db_session,
) -> None:
    telegram_id = new_test_telegram_id()
    await register_fully(bot_harness, telegram_id)
    await bot_harness.send(BTN_NATAL, telegram_id=telegram_id)
    await bot_harness.click(CB_NATAL_SUBJECT_SELF, telegram_id=telegram_id)

    calls = await bot_harness.send("вчера", telegram_id=telegram_id)
    assert_said(calls, "Не разобрала дату")

    calls = await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)
    assert_said(calls, "Где ты родилась")


async def test_unknown_city_reprompts_and_flow_continues(
    bot_harness: BotHarness,
    db_session,
) -> None:
    telegram_id = new_test_telegram_id()
    await open_birth_place_step(bot_harness, telegram_id)

    # Выдуманное название не должно ронять шаг: человек вводит ещё раз и идёт
    # дальше. Что именно ответит бот — «ничего не нашла» или похожие города —
    # зависит от размера справочника, и это проверяется отдельно.
    calls = await bot_harness.send(UNKNOWN_CITY_QUERY, telegram_id=telegram_id)
    assert calls, "бот промолчал на непонятный запрос"

    pick = await reach_place_buttons(bot_harness, telegram_id)
    assert pick


async def test_unknown_city_offers_similar_names_instead_of_dead_end(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Опечатка приводит к похожим городам, а не к «ничего не нашла».

    Человек редко переспрашивает дважды: если на выдуманном названии он видит
    пустоту, он уходит. Поэтому нижний порог похожести и второй проход.
    """
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)

    calls = await bot_harness.send(UNKNOWN_CITY_QUERY, telegram_id=telegram_id)
    assert _callbacks(calls, "place:pick:") or _callbacks(calls, "place:region:"), (
        f"тупик на «{UNKNOWN_CITY_QUERY}»: {[c.text for c in calls]}"
    )


async def test_wrong_gender_input_reprompts_with_buttons(
    bot_harness: BotHarness,
    db_session,
) -> None:
    telegram_id = new_test_telegram_id()
    await bot_harness.send("/start", telegram_id=telegram_id)
    await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)

    calls = await bot_harness.send("не скажу", telegram_id=telegram_id)
    prompt = assert_said(calls, "Выбери пол кнопкой")
    assert BTN_GENDER_FEMALE in prompt.buttons()


# --------------------------------------------------------------------------
# Слой БД под регистрацией: то место, где всё сломалось в прошлый раз
# --------------------------------------------------------------------------


async def test_fresh_user_is_usable_right_after_create(db_session) -> None:
    """Только что созданный `User` не должен требовать похода в базу.

    `create_user` отдаёт объект без подгруженного `profile`; всё, что зовётся
    следом (серия дней, активность), обращается к нему в async-контексте —
    ленивая подгрузка там падает с `MissingGreenlet` и убивает `/start`.
    """
    from astra.services.points_service import register_daily_activity
    from astra.users import crud as users_crud
    from astra.users.local_time import local_today, user_timezone

    telegram_id = new_test_telegram_id()
    user = await users_crud.create_user(
        db_session,
        telegram_id=telegram_id,
        username="ads_lead",
        language_code="ru",
    )

    assert user.id is not None
    assert user.streak_current == 0
    assert user_timezone(user).key == "Europe/Moscow"
    assert local_today(user) is not None

    points, streak = await register_daily_activity(db_session, user)
    assert streak == 1
    assert points > 0

    await db_session.rollback()


async def test_activity_middleware_survives_user_without_profile(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Апдейт до конца онбординга проходит через ActivityMiddleware без падения.

    Профиля ещё нет, а middleware считает серию по таймзоне человека —
    именно на этом стыке `/start` и умирал.
    """
    from astra.users.models import User

    telegram_id = new_test_telegram_id()
    await bot_harness.send("/start", telegram_id=telegram_id)
    await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)

    db_session.expire_all()
    user = (
        await db_session.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one()
    assert user.streak_current >= 1, "серия не начислена новому пользователю"
    assert user.last_active_date is not None


# --------------------------------------------------------------------------
# Выбор места: два шага вместо пяти неразличимых строк
# --------------------------------------------------------------------------


async def _to_place_step(harness: BotHarness, telegram_id: int) -> None:
    await open_birth_place_step(harness, telegram_id)
    harness.clear()


async def test_place_step_explains_the_nearby_city_rule(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Подсказка должна читаться не вчитываясь — иначе человек уйдёт."""
    telegram_id = new_test_telegram_id()
    await register_fully(bot_harness, telegram_id)
    await bot_harness.send(BTN_NATAL, telegram_id=telegram_id)
    await bot_harness.click(CB_NATAL_SUBJECT_SELF, telegram_id=telegram_id)
    calls = await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)

    prompt = assert_said(calls, "Где ты родилась")
    assert "в своей области" in prompt.text
    assert "погрешность" in prompt.text
    # Числу здесь верят на слово — оно должно совпадать с тем, по которому
    # подбирается ближайший город.
    assert str(NEARBY_CITY_KM) in prompt.text


async def test_many_namesakes_ask_for_region_first(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Тёзок много — сначала регион с числом мест, а не пять одинаковых строк."""
    from astra.places import crud

    search = await crud.prepare_search(db_session, "Красное")
    if search is None or search.total <= 8:
        pytest.skip("в справочнике нет тёзок — шаг региона не нужен")

    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send("Красное", telegram_id=telegram_id)

    step = calls[0]
    assert "В каком регионе" in step.text
    assert _callbacks([step], "place:region:"), "нет кнопок регионов"
    # Счётчик рядом с регионом: человек видит, сколько там вариантов.
    assert any(" · " in button for button in step.buttons())


async def test_places_inside_region_carry_a_landmark(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Внутри региона строки различаются ближайшим городом, а не молчат."""
    from astra.places import crud

    search = await crud.prepare_search(db_session, "Красное")
    if search is None or search.total <= 8:
        pytest.skip("в справочнике нет тёзок")

    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send("Красное", telegram_id=telegram_id)
    region = _callbacks(calls, "place:region:")[0]

    calls = await bot_harness.click(region, telegram_id=telegram_id)
    picker = calls[0]
    labels = picker.buttons()[:-2]  # без навигации
    assert len(labels) >= 3
    assert len(set(labels)) == len(labels), f"строки неразличимы: {labels}"
    assert any("км" in label for label in labels), "нет ориентира"


async def test_back_from_region_returns_to_the_region_list(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Ошибся регионом — можно вернуться, а не начинать всё заново."""
    from astra.places import crud

    search = await crud.prepare_search(db_session, "Красное")
    if search is None or search.total <= 8:
        pytest.skip("в справочнике нет тёзок")

    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send("Красное", telegram_id=telegram_id)
    await bot_harness.click(_callbacks(calls, "place:region:")[0], telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.click("place:regions", telegram_id=telegram_id)
    assert "В каком регионе" in calls[0].text


async def test_more_button_shows_the_next_page(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Раньше дальше пятой строки было не пройти вовсе."""
    from astra.places import crud

    search = await crud.prepare_search(db_session, "Красное")
    if search is None or search.total <= 8:
        pytest.skip("в справочнике нет тёзок")

    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send("Красное", telegram_id=telegram_id)
    first_page = calls[0].buttons()

    more = _callbacks(calls, "place:page:")
    assert more, "нет кнопки «ещё» — часть регионов недостижима"

    calls = await bot_harness.click(more[0], telegram_id=telegram_id)
    second_page = calls[0].buttons()
    assert set(first_page) != set(second_page), "вторая страница повторяет первую"


async def test_few_matches_skip_the_region_step(
    bot_harness: BotHarness,
    db_session,
    full_catalog,
) -> None:
    """Ради двух вариантов лишний шаг только раздражает."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send("Коноково", telegram_id=telegram_id)

    assert "Выбери населённый пункт" in calls[0].text
    assert _callbacks(calls, "place:pick:")


# --------------------------------------------------------------------------
# «Не нашла свой город»: последняя страховка от тупика
# --------------------------------------------------------------------------


@pytest.fixture
async def admin_group(monkeypatch):
    """Админ-группа для карточек обращений. Отправку ловит фейковый Telegram."""
    from astra.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_admin_group_id", -1004419830379, raising=False)
    return settings.telegram_admin_group_id


async def test_missing_city_button_is_always_on_the_list(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Тупик выглядит как восемь чужих сёл, а не как пустота."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    calls = await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)

    assert "place:missing" in _callbacks(calls, "place:missing")
    assert any("Не нашла свой город" in button for button in calls[0].buttons())


async def test_missing_city_screen_calms_and_offers_two_ways(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Сначала снимаем тревогу, потом предлагаем помочь — не наоборот."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.click("place:missing", telegram_id=telegram_id)

    screen = calls[0]
    assert "70 км" in screen.text
    assert "в своей области" in screen.text
    assert "таким же точным" in screen.text
    assert "Выбрать город" in screen.buttons()
    assert any("Рассказать" in button for button in screen.buttons())


async def test_choose_city_returns_to_the_search_step(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Кнопка «Выбрать город» возвращает в тот же шаг, а не в никуда."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.click("place:retry", telegram_id=telegram_id)
    assert "Где ты родилась" in calls[0].text

    # И поиск снова работает: человек не выпал из онбординга.
    pick = await reach_place_buttons(bot_harness, telegram_id)
    assert pick


async def test_description_goes_to_operators_with_context(
    bot_harness: BotHarness,
    db_session,
    admin_group,
) -> None:
    """Карточка оператору несёт то, чего он сам не узнает: что искал человек."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send("Ктулхуград", telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)

    calls = await bot_harness.click("place:describe", telegram_id=telegram_id)
    prompt = calls[0]
    assert "одним сообщением" in prompt.text
    assert "рядом с каким городом" in prompt.text
    assert "Весёлый" in prompt.text  # пример, а не голая инструкция

    bot_harness.clear()
    story = "хутор Весёлый, Успенский район, Краснодарский край, 15 км от Армавира"
    calls = await bot_harness.send(story, telegram_id=telegram_id)

    # Карточка кладётся дважды: сначала без номера, потом с ним — оператор
    # видит последнюю.
    to_admins = [c for c in calls if str(c.payload.get("chat_id")) == str(admin_group)]
    assert to_admins, "карточка не ушла в админ-группу"
    card = to_admins[-1]
    assert "нет места в справочнике" in card.text.lower()
    assert "Обращение #" in card.text
    assert "Ктулхуград" in card.text, "оператор не увидит, что человек искал"
    assert story in card.text
    assert str(telegram_id) in card.text


async def test_after_description_person_continues_registration(
    bot_harness: BotHarness,
    db_session,
    admin_group,
) -> None:
    """Главное: человек не остаётся в тупике, а идёт дальше и получает разбор."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send("Ктулхуград", telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)
    await bot_harness.click("place:describe", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send(
        "хутор Весёлый, Успенский район, Краснодарский край, 15 км от Армавира",
        telegram_id=telegram_id,
    )
    assert any("Спасибо" in call.text for call in calls)
    assert any("Где ты родилась" in call.text for call in calls)

    pick = await reach_place_buttons(bot_harness, telegram_id)
    calls = await bot_harness.click(pick, telegram_id=telegram_id)
    assert_said(calls, "Разбор натальной карты")


async def test_too_short_description_is_reprompted(
    bot_harness: BotHarness,
    db_session,
    admin_group,
) -> None:
    """«Нет города» оператору ничего не даёт — просим подробнее."""
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)
    await bot_harness.click("place:describe", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send("нет города", telegram_id=telegram_id)
    assert "подробнее" in calls[0].text
    assert not [c for c in calls if str(c.payload.get("chat_id")) == str(admin_group)]


async def test_broken_admin_group_does_not_break_onboarding(
    bot_harness: BotHarness,
    db_session,
) -> None:
    """Админ-группа не настроена — человек всё равно идёт дальше.

    Он и так не нашёл своё село; оставить его ещё и без ответа — верный
    способ потерять совсем.
    """
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)
    await bot_harness.click("place:describe", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send(
        "село Иваново, Тверская область, 20 км от Твери",
        telegram_id=telegram_id,
    )
    assert any("Где ты родилась" in call.text for call in calls)


async def test_main_menu_does_not_appear_during_the_story(
    bot_harness: BotHarness,
    db_session,
    admin_group,
) -> None:
    """Посреди регистрации главное меню — приглашение её бросить.

    Человек рассказывает про своё село, а снизу вылезает «Колесо фортуны»:
    одно нажатие — и регистрация не закончена.
    """
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)
    await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    await bot_harness.click("place:missing", telegram_id=telegram_id)
    await bot_harness.click("place:describe", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send(
        "село Иваново, Тверская область, 20 км от Твери",
        telegram_id=telegram_id,
    )
    for call in calls:
        assert "🎡 Колесо фортуны" not in call.buttons(), (
            f"главное меню посреди онбординга: {call.text[:60]}"
        )


async def test_query_reaches_operators_even_when_nothing_was_found(
    bot_harness: BotHarness,
    db_session,
    admin_group,
) -> None:
    """Пустая выдача — самый ценный случай: именно этого места и не хватает.

    Раньше запрос сохранялся только после удачного поиска, и оператор видел
    рассказ без единственного, что мы знаем точно, — что человек набрал.
    """
    telegram_id = new_test_telegram_id()
    await _to_place_step(bot_harness, telegram_id)

    calls = await bot_harness.send("Ктулхуград", telegram_id=telegram_id)
    # Выход с экрана есть в любом случае — даже когда список пуст.
    assert _callbacks(calls, "place:missing")

    await bot_harness.click("place:missing", telegram_id=telegram_id)
    await bot_harness.click("place:describe", telegram_id=telegram_id)

    bot_harness.clear()
    calls = await bot_harness.send(
        "хутор Весёлый, Успенский район, Краснодарский край, 15 км от Армавира",
        telegram_id=telegram_id,
    )
    to_admins = [c for c in calls if str(c.payload.get("chat_id")) == str(admin_group)]
    assert to_admins
    assert "Ктулхуград" in to_admins[-1].text
