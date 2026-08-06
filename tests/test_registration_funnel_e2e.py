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

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from conftest import new_test_telegram_id
from fake_telegram import BotHarness, assert_said, build_bot, build_test_dispatcher

from astra.telegram.button_texts import BTN_GENDER_FEMALE, BTN_PROFILE
from astra.users.gender import GENDER_FEMALE

pytestmark = pytest.mark.usefixtures("purge_test_users")

BEGIN_BUTTON = "Привет, Астрид 🫶🏻"
BIRTH_DATE_INPUT = "15.03.1990"
BIRTH_DATE = date(1990, 3, 15)
BIRTH_CITY_QUERY = "Москва"
# Заведомо не существующий населённый пункт: важно, чтобы не находился даже
# по нечёткому поиску pg_trgm, иначе тест проверял бы не то.
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


async def walk_to_city_list(
    harness: BotHarness,
    telegram_id: int,
    *,
    start_command: str = "/start",
) -> str:
    """Пройти онбординг до списка городов и вернуть callback_data первого."""
    await harness.send(start_command, telegram_id=telegram_id)
    await harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    await harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)
    await harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)
    calls = await harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)

    picks = [
        data
        for call in calls
        for data in call.callback_data()
        if data.startswith("place:pick:")
    ]
    assert picks, f"справочник городов не отдал варианты: {[c.text for c in calls]}"
    return picks[0]


async def register_fully(
    harness: BotHarness,
    telegram_id: int,
    *,
    start_command: str = "/start",
) -> None:
    """Весь путь новичка от команды старта до готового профиля."""
    pick = await walk_to_city_list(harness, telegram_id, start_command=start_command)
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

    # 1. /start — приветствие с кнопкой начала
    calls = await bot_harness.send("/start", telegram_id=telegram_id)
    assert "sendVideo" in [call.api_method for call in calls]
    welcome = calls[0]
    assert "Добро пожаловать в Astra" in welcome.text
    assert BEGIN_BUTTON in welcome.buttons()

    user = await load_user(db_session, telegram_id)
    assert user is not None, "пользователь не создан на /start"
    assert user.onboarding_completed is False

    # 2. «Привет, Астрид» — спрашиваем пол
    calls = await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    gender_prompt = assert_said(calls, "Укажи свой пол")
    assert BTN_GENDER_FEMALE in gender_prompt.buttons()
    assert BTN_PROFILE in gender_prompt.text  # подсказка, где менять имя

    # 3. Пол — спрашиваем дату рождения
    calls = await bot_harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)
    assert_said(calls, "дату рождения")

    # 4. Дата — спрашиваем место рождения
    calls = await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)
    assert_said(calls, "Где ты родилась")

    # 5. Город — список из справочника
    calls = await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    picker = assert_said(calls, "Выбери населённый пункт")
    picks = [data for data in picker.callback_data() if data.startswith("place:pick:")]
    assert picks, "справочник городов пуст — онбординг обрывается на выборе города"

    # 6. Выбор города — регистрация завершена
    calls = await bot_harness.click(picks[0], telegram_id=telegram_id)
    done = assert_said(calls, "Регистрация завершена")
    assert "✨ Обо мне" in done.buttons(), "после регистрации не выдали главное меню"

    # 7. В базе — полноценный профиль
    db_session.expire_all()
    user = await load_user(db_session, telegram_id)
    assert user is not None
    assert user.onboarding_completed is True, "флаг онбординга не выставлен"
    assert user.profile is not None, "профиль не создан"
    assert user.profile.display_name == "Аида"
    assert user.profile.gender == GENDER_FEMALE
    assert user.profile.birth_date == BIRTH_DATE
    assert user.profile.birth_place_id is not None
    assert user.profile.timezone, "без таймзоны не уйдёт ежедневная рассылка"
    assert user.referral_code is not None, "реферальный код не выдан"

    # 8. Первое предсказание поставлено в очередь
    enqueued_predictions.assert_awaited_once()
    assert enqueued_predictions.await_args.args[1] == user.id


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
    assert "Добро пожаловать в Astra" in calls[0].text
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
    await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=invitee_id)
    calls = await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=invitee_id)
    pick = next(
        data
        for call in calls
        for data in call.callback_data()
        if data.startswith("place:pick:")
    )
    await bot_harness.click(pick, telegram_id=invitee_id)

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

    assert "Добро пожаловать в Astra" in calls[0].text
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
    assert "Добро пожаловать в Astra" in calls[0].text
    assert BEGIN_BUTTON in calls[0].buttons()


# --------------------------------------------------------------------------
# Тупики: любая ошибка ввода должна оставлять путь вперёд
# --------------------------------------------------------------------------


async def test_invalid_birth_date_reprompts_and_flow_continues(
    bot_harness: BotHarness,
    db_session,
) -> None:
    telegram_id = new_test_telegram_id()
    await bot_harness.send("/start", telegram_id=telegram_id)
    await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    await bot_harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)

    calls = await bot_harness.send("вчера", telegram_id=telegram_id)
    assert_said(calls, "Не могу разобрать дату")

    calls = await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)
    assert_said(calls, "Где ты родилась")


async def test_unknown_city_reprompts_and_flow_continues(
    bot_harness: BotHarness,
    db_session,
) -> None:
    telegram_id = new_test_telegram_id()
    await bot_harness.send("/start", telegram_id=telegram_id)
    await bot_harness.send(BEGIN_BUTTON, telegram_id=telegram_id)
    await bot_harness.send(BTN_GENDER_FEMALE, telegram_id=telegram_id)
    await bot_harness.send(BIRTH_DATE_INPUT, telegram_id=telegram_id)

    calls = await bot_harness.send(UNKNOWN_CITY_QUERY, telegram_id=telegram_id)
    assert_said(calls, "Ничего не нашла")

    calls = await bot_harness.send(BIRTH_CITY_QUERY, telegram_id=telegram_id)
    assert_said(calls, "Выбери населённый пункт")


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
