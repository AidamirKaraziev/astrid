from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    welcome = State()
    name = State()
    birth_date = State()
    birth_place_query = State()
    notification_place_query = State()


class ProfileStates(StatesGroup):
    edit_name = State()
    edit_birth_time = State()
    edit_birth_place = State()
