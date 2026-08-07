"""Добор данных рождения посреди продукта.

Короткий онбординг спрашивает имя и пол, поэтому до разбора человек доходит
с пустым профилем. Дальше есть два честных варианта: закрыть дверь («добавь
данные в профиле») или спросить прямо здесь и вернуть человека туда, откуда
он пришёл. Работает только второй: отправить человека искать раздел ради
того, что бот мог спросить сам, — это потеря на ровном месте.

Как устроено:

* продукт зовёт `ensure_birth_data` перед началом сценария;
* если чего-то не хватает, начинается добор: дата, потом место;
* каждый ответ сразу пишется в профиль, а не копится в FSM: человек может
  уйти на середине, и то, что он уже назвал, спрашивать второй раз нельзя;
* когда всё собрано, продукт продолжается сам — по ключу в FSM.

Точка проверки одна на все продукты нарочно. Если каждый хендлер напишет
свою, тексты разъедутся, а какой-нибудь один проверку забудет — и человек
получит разбор, посчитанный от Москвы и полудня, не узнав об этом.

Время рождения здесь не спрашивается: без него карта считается на полдень,
знаки планет остаются верными, и каждый продукт просит его сам — со своим
объяснением про асцендент и дома. Место ведёт себя иначе: при пустом месте
координаты подставляются московские, поэтому без него разбор невозможен.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.telegram.states import BirthDataStates
from astra.users import crud as users_crud
from astra.users.birth_data import BirthField, Product, blocked_by
from astra.users.models import Profile, User

# Продукт, в который надо вернуться, когда данные собраны.
RETURN_PRODUCT_KEY = "birth_data_return_product"
# Что именно человек открывал внутри продукта: раздел «Спроси Астрид» состоит
# из десятка вопросов, и вернуть его надо к своему, а не в общий список.
RETURN_PAYLOAD_KEY = "birth_data_return_payload"

_FIELD_LABELS: dict[BirthField, str] = {
    BirthField.DATE: "дата рождения",
    BirthField.TIME: "время рождения",
    BirthField.PLACE: "место рождения",
}

_PRODUCT_LABELS: dict[Product, str] = {
    Product.NATAL_REPORT: "разбора натальной карты",
    Product.COMPATIBILITY: "разбора совместимости",
    Product.ASK_ANSWER: "ответа по твоей карте",
    Product.DAILY_PREDICTION: "ежедневного предсказания",
    Product.PROFILE_PORTRAIT: "портрета по карте",
}

_ASK_DATE = (
    "📅 Для {what} нужна дата рождения.\n\n"
    "Напиши её в формате <b>ДД.ММ.ГГГГ</b> — например <code>15.03.1990</code>"
)

def missing_data_text(product: Product, missing: tuple[BirthField, ...]) -> str:
    """Что сказать человеку, у которого не хватает данных."""
    labels = [_FIELD_LABELS[field] for field in missing]
    if len(labels) == 1:
        what = labels[0]
    else:
        what = ", ".join(labels[:-1]) + " и " + labels[-1]
    return f"✨ Для {_PRODUCT_LABELS[product]} нужна {what}."


async def ensure_birth_data(
    message: Message,
    product: Product,
    profile: Profile | None,
    *,
    state: FSMContext | None = None,
    payload: str | None = None,
) -> bool:
    """True — данных хватает, продукт продолжается.

    False — начат добор недостающего (или, если состояние недоступно,
    человеку сказано, чего не хватает), и продукт должен молча остановиться.

    `payload` — что человек открывал внутри продукта (например, ключ вопроса
    в «Спроси Астрид»), чтобы вернуть его именно туда.
    """
    if not blocked_by(product, profile):
        return True
    if state is None:
        await message.answer(missing_data_text(product, blocked_by(product, profile)))
        return False
    await start_birth_data_collection(message, state, product, profile, payload=payload)
    return False


async def start_birth_data_collection(
    message: Message,
    state: FSMContext,
    product: Product,
    profile: Profile | None,
    *,
    payload: str | None = None,
) -> None:
    await state.set_state(None)
    await state.update_data(
        **{RETURN_PRODUCT_KEY: product.value, RETURN_PAYLOAD_KEY: payload},
    )
    await _ask_next(message, state, product, profile)


async def _ask_next(
    message: Message,
    state: FSMContext,
    product: Product,
    profile: Profile | None,
) -> bool:
    """Спросить первое недостающее. False — спрашивать больше нечего.

    Спрашиваем только то, без чего продукт невозможен. Время рождения сюда
    не входит намеренно: разбор натала просит его сам, объясняя про асцендент
    и дома, и «Спроси Астрид» — тоже. Спроси мы его здесь, человек ответил бы
    на один вопрос дважды.
    """
    missing = blocked_by(product, profile)
    if not missing:
        return False

    if missing[0] is BirthField.DATE:
        await state.set_state(BirthDataStates.date)
        await message.answer(
            _ASK_DATE.format(what=_PRODUCT_LABELS[product]),
            parse_mode="HTML",
        )
        return True

    # Шаг места живёт в модуле мест: там поиск, регионы, страницы и кнопка
    # «не нашла свой город». Дублировать его здесь нельзя.
    from astra.telegram.handlers.places import start_own_birth_place_step

    await start_own_birth_place_step(message, state)
    return True


async def continue_after_birth_data(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Спросить следующее недостающее или вернуть человека в продукт."""
    data = await state.get_data()
    raw_product = data.get(RETURN_PRODUCT_KEY)
    if raw_product is None:
        await state.set_state(None)
        return

    product = Product(str(raw_product))
    if await _ask_next(message, state, product, user.profile):
        return

    await state.set_state(None)
    payload = data.get(RETURN_PAYLOAD_KEY)
    await _resume_product(
        message,
        state,
        session,
        user,
        product,
        payload=str(payload) if payload else None,
    )


async def _resume_product(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    product: Product,
    *,
    payload: str | None = None,
) -> None:
    """Продолжить прерванный сценарий с того места, где не хватило данных.

    Импорты внутри функции: продукты сами зовут гейт, и на уровне модуля это
    был бы круг.
    """
    await message.answer("Спасибо! Всё сошлось — продолжаем ✨")

    if product is Product.NATAL_REPORT:
        from astra.telegram.handlers.natal import begin_self_natal_flow

        await begin_self_natal_flow(message, state, user)
        return

    if product is Product.COMPATIBILITY:
        from astra.telegram.handlers.compatibility import start_compatibility

        await start_compatibility(message, state, session)
        return

    if product is Product.ASK_ANSWER:
        from astra.telegram.handlers.ask_astrid import resume_paid_question

        await resume_paid_question(message, state, session, user, question_key=payload)
        return

    # Портрет и ежедневное предсказание отдельного сценария не имеют: данные
    # сохранены, человек увидит их при следующем открытии раздела.


async def save_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    birth_date,  # noqa: ANN001 — date, но импорт ради подписи здесь лишний
) -> None:
    await users_crud.update_profile(session, user.profile, birth_date=birth_date)
    await session.commit()
    await continue_after_birth_data(message, state, session, user)
