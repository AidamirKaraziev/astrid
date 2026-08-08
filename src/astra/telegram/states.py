from aiogram.fsm.state import State, StatesGroup


class AiChatStates(StatesGroup):
    """Режим свободного диалога с Astrid (AI-чат)."""

    chatting = State()


class OnboardingStates(StatesGroup):
    """Знакомство: как обращаться и какого человек пола.

    Данных рождения здесь нет намеренно — их спрашивает `BirthDataStates`
    тогда, когда человек открывает продукт, которому они нужны.
    """

    welcome = State()
    gender = State()


class BirthDataStates(StatesGroup):
    """Добор данных рождения посреди продукта.

    Человек нажал «разбор натальной карты», а даты рождения у него в профиле
    нет — значит спрашиваем прямо здесь и возвращаем его ровно туда, откуда
    забрали. Продукт, в который надо вернуться, лежит в FSM.

    Отдельная группа, а не шаги онбординга: попасть сюда можно из разбора,
    совместимости и «Спроси Астрид», и состояние «человек регистрируется» с
    состоянием «человеку не хватило данных» — разные вещи.
    """

    date = State()
    place_query = State()


class ProfileStates(StatesGroup):
    """Правка своих данных в разделе «Обо мне».

    Место рождения — тоже `*_place_query`: правка идёт через поиск по
    справочнику, как и везде. Свободного текста здесь нет намеренно — от него
    в профиль попадало название без координат.
    """

    edit_name = State()
    edit_birth_date = State()
    edit_birth_time = State()
    edit_birth_place_query = State()
    edit_notification_place_query = State()


class CompatibilityStates(StatesGroup):
    choose_context = State()
    collect_name = State()
    collect_gender = State()
    collect_birth_date = State()
    collect_birth_time = State()
    birth_place_query = State()
    confirm = State()


class NatalStates(StatesGroup):
    collect_birth_time = State()
    confirm = State()
    # Ввод нового человека для разбора натала
    new_name = State()
    new_gender = State()
    new_birth_date = State()
    new_birth_time = State()
    new_birth_place_query = State()


class TarotStates(StatesGroup):
    """Платный расклад: ждём вопрос к картам (тип расклада — в FSM data)."""

    waiting_question = State()


class SupportStates(StatesGroup):
    """Служба заботы: ждём текст обращения для релея живому оператору."""

    writing = State()


class PlaceStates(StatesGroup):
    """Человек не нашёл своё место и рассказывает, какого не хватает.

    Отдельное состояние, а не `SupportStates.writing`: сюда человек попадает
    из середины другого сценария (онбординг, совместимость, «мои люди»), и
    после отправки его надо вернуть ровно туда, откуда забрали.
    """

    describing_missing = State()


class PeopleStates(StatesGroup):
    """Редактирование сохранённого натального профиля («Мои люди»)."""

    edit_name = State()
    edit_birth_date = State()
    edit_birth_time = State()
    edit_birth_place_query = State()
