from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    welcome = State()
    name = State()
    birth_date = State()
    city = State()


class ProfileStates(StatesGroup):
    edit_name = State()
    edit_birth_time = State()
    edit_birth_place = State()
