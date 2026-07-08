from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    welcome = State()
    gender = State()
    birth_date = State()
    birth_place_query = State()


class ProfileStates(StatesGroup):
    edit_name = State()
    edit_birth_date = State()
    edit_birth_time = State()
    edit_birth_place = State()
    edit_notification_place_query = State()


class CompatibilityStates(StatesGroup):
    choose_context = State()
    choose_pair_mode = State()
    collect_name = State()
    collect_gender = State()
    collect_birth_date = State()
    collect_birth_time = State()
    birth_place_query = State()
    confirm = State()


class NatalStates(StatesGroup):
    collect_birth_time = State()
    confirm = State()


class PeopleStates(StatesGroup):
    """Редактирование сохранённого натального профиля («Мои люди»)."""

    edit_name = State()
    edit_birth_date = State()
    edit_birth_time = State()
    edit_birth_place_query = State()
