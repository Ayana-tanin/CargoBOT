from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BT_SHARE_PHONE = "📱 Отправить номер телефона"

BT_REGISTER = "Пройти регистрацию"
BT_LOGIN = "Войти"
BT_INFO = "ℹ️ Информация"
BT_STATUS = "📦 Проверить статус"

MENU_TEXTS = frozenset({BT_INFO, BT_STATUS, BT_LOGIN, BT_REGISTER})


def welcome_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BT_REGISTER), KeyboardButton(text=BT_LOGIN)],
        ],
        resize_keyboard=True,
        selective=True,
    )


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BT_SHARE_PHONE, request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BT_STATUS)],
            [KeyboardButton(text=BT_INFO)],
        ],
        resize_keyboard=True,
        selective=True,
    )

