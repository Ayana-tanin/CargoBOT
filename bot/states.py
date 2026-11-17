from aiogram.fsm.state import State, StatesGroup


class RegisterStates(StatesGroup):
    waiting_client_code = State()
    waiting_phone = State()
    waiting_fio = State()


class AdminUploadStates(StatesGroup):
    waiting_excel = State()

