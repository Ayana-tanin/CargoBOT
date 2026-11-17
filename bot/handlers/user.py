from __future__ import annotations

import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove

from bot.config import Config
from bot.database.db import SqlitePool
from bot.database.queries import (
    allocate_next_client_code,
    get_user_by_code,
    get_user_by_telegram_id,
    upsert_user,
)
from bot.keyboards.user import (
    BT_INFO,
    BT_LOGIN,
    BT_REGISTER,
    BT_SHARE_PHONE,
    BT_STATUS,
    MENU_TEXTS,
    main_menu,
    phone_request_keyboard,
    welcome_menu,
)
from bot.states import RegisterStates

router = Router(name=__name__)

# Не перехватывать /upload, /start и др. — иначе команды не доходят до admin-роутера.
_not_command = F.text.func(lambda text: not (text or "").startswith("/"))

# Legacy codes: K1234, L23435423, E-23435t
_LEGACY_CLIENT_CODE_RE = re.compile(r"^[A-Za-z](?:-)?\d{1,8}[A-Za-z]?$")
# Auto codes from registration: 600-kar, 601-kar, ...
_AUTO_CLIENT_CODE_RE = re.compile(r"^\d+-kar$", re.IGNORECASE)


def _normalize_client_code(text: str) -> str:
    code = text.strip().replace(" ", "")
    if _AUTO_CLIENT_CODE_RE.fullmatch(code):
        parts = code.split("-", 1)
        return f"{parts[0]}-kar"
    return code


def _is_valid_client_code(code: str) -> bool:
    return bool(
        _LEGACY_CLIENT_CODE_RE.fullmatch(code)
        or _AUTO_CLIENT_CODE_RE.fullmatch(code)
    )


def _normalize_phone(text: str) -> str | None:
    """
    E.164: + и 8–15 цифр.
    Поддержка: +996… (КГ), +7… (РФ/КЗ), +380… и др., а также локальный формат 0700… (КГ).
    """
    raw = (text or "").strip()
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return None

    # Кыргызстан: 0700123456
    if len(digits) == 10 and digits.startswith("0"):
        digits = "996" + digits[1:]
    # Кыргызстан: 700123456 (9 цифр без кода страны)
    elif len(digits) == 9:
        digits = "996" + digits
    # Россия: 89991234567
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    # Россия / Казахстан: 9123456789
    elif len(digits) == 10:
        digits = "7" + digits

    if len(digits) < 8 or len(digits) > 15:
        return None
    if digits.startswith("0"):
        return None

    return f"+{digits}"


def _is_valid_fio(text: str) -> bool:
    cleaned = " ".join((text or "").split())
    return len(cleaned) >= 5 and " " in cleaned


def _welcome_text() -> str:
    return (
        "Привет! Я бот карго-компании.\n\n"
        "Если у вас уже есть код карго нажмите Войти \n"
        "Если нет нажмите Регистрацию."
    )


async def _send_instruction_video(message: Message, config: Config, bot: Bot) -> None:
    if config.instruction_video_file_id:
        await bot.send_video(
            chat_id=message.chat.id,
            video=config.instruction_video_file_id,
        )
        return
    if config.instruction_video_path:
        await bot.send_video(
            chat_id=message.chat.id,
            video=FSInputFile(config.instruction_video_path),
        )
        return


def _user_has_profile(user: object) -> bool:
    return bool(user["phone"] and user["full_name"])


async def _prompt_fio(message: Message, state: FSMContext) -> None:
    await state.set_state(RegisterStates.waiting_fio)
    await message.answer(
        "Телефон сохранён.\n\n"
        "Теперь напишите ФИО полностью (фамилия, имя, отчество).",
        reply_markup=ReplyKeyboardRemove(),
    )


async def _on_phone_saved(
    message: Message, state: FSMContext, phone: str
) -> None:
    await state.update_data(phone=phone)
    await _prompt_fio(message, state)


async def _start_profile_collection(
    message: Message,
    state: FSMContext,
    *,
    client_code: str,
    phone: str | None = None,
) -> None:
    await state.update_data(pending_client_code=client_code, login_after_profile=False)
    if phone:
        await state.update_data(phone=phone)
        await _prompt_fio(message, state)
        return
    await state.set_state(RegisterStates.waiting_phone)
    await message.answer(
        "Укажите контакты.\n\n"
        "Шаг 1 из 2: отправьте номер телефона кнопкой ниже или текстом "
        "(+996…, +7…, другая страна с «+»).",
        reply_markup=phone_request_keyboard(),
    )


async def _login_with_code(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
    code: str,
) -> None:
    existing = await get_user_by_code(db_pool, code)
    if existing:
        if int(existing["telegram_id"]) != int(message.from_user.id):
            await message.answer(
                "Этот код уже привязан к другому аккаунту. "
                "Проверьте код или пройдите регистрацию заново."
            )
            return
        if _user_has_profile(existing):
            await state.clear()
            await message.answer(
                f"Добро пожаловать! Ваш код: <b>{code}</b>\n"
                f"ФИО: {existing['full_name']}\n"
                f"Телефон: {existing['phone']}",
                reply_markup=main_menu(),
            )
            return
        await _start_profile_collection(
            message,
            state,
            client_code=code,
            phone=existing["phone"],
        )
        return

    await _start_profile_collection(message, state, client_code=code)


async def _finish_login_profile(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
) -> None:
    data = await state.get_data()
    phone = data.get("phone")
    full_name = data.get("full_name")
    code = data.get("pending_client_code")
    if not phone or not full_name or not code:
        await state.clear()
        await message.answer(
            "Вход не завершён. Нажмите «Войти» и введите код снова.",
            reply_markup=welcome_menu(),
        )
        return

    username = message.from_user.username if message.from_user else None
    try:
        await upsert_user(
            db_pool,
            client_code=code,
            telegram_id=int(message.from_user.id),
            username=username,
            phone=phone,
            full_name=full_name,
        )
    except Exception:
        await message.answer(
            "Не удалось сохранить данные. Проверьте код или пройдите регистрацию.",
            reply_markup=welcome_menu(),
        )
        return

    await state.clear()
    await message.answer(
        f"Добро пожаловать! Ваш код: <b>{code}</b>\n\n"
        f"ФИО: {full_name}\n"
        f"Телефон: {phone}",
        reply_markup=main_menu(),
    )


async def _finish_registration(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
    config: Config,
) -> None:
    data = await state.get_data()
    phone = data.get("phone")
    full_name = data.get("full_name")
    if not phone or not full_name:
        await state.clear()
        await message.answer(
            "Регистрация прервана. Нажмите «Пройти регистрацию» и начните сначала.",
            reply_markup=welcome_menu(),
        )
        return

    client_code = await allocate_next_client_code(db_pool)
    username = message.from_user.username if message.from_user else None
    try:
        await upsert_user(
            db_pool,
            client_code=client_code,
            telegram_id=int(message.from_user.id),
            username=username,
            phone=phone,
            full_name=full_name,
        )
    except Exception:
        await message.answer(
            "Не удалось сохранить регистрацию. Попробуйте ещё раз через «Пройти регистрацию».",
            reply_markup=welcome_menu(),
        )
        return

    await state.clear()
    await message.answer(
        f"Адрес карго:\n{config.cargo_address}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        f"Ваш номер: <b>{client_code}</b>\n\n"
        f"ФИО: {full_name}\n"
        f"Телефон: {phone}\n\n"
        "Сохраните код — он понадобится при отправке груза.",
        reply_markup=main_menu(),
    )


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
) -> None:
    user = await get_user_by_telegram_id(db_pool, int(message.from_user.id))
    await state.clear()

    if user:
        if not _user_has_profile(user):
            await message.answer(
                f"{_welcome_text()}\n\n"
                f"Ваш код: <b>{user['client_code']}</b>. "
                "Укажите телефон и ФИО для завершения профиля."
            )
            await _start_profile_collection(
                message,
                state,
                client_code=user["client_code"],
                phone=user["phone"],
            )
            return
        lines = [
            _welcome_text(),
            f"Вы зарегистрированы. Ваш код: <b>{user['client_code']}</b>",
            f"ФИО: {user['full_name']}",
            f"Телефон: {user['phone']}",
            "Чтобы обновить данные — снова «Пройти регистрацию». "
            "Сменить только код: /change_code",
        ]
        await message.answer("\n\n".join(lines), reply_markup=main_menu())
        return

    await message.answer(_welcome_text(), reply_markup=welcome_menu())


def _info_text(config: Config) -> str:
    return (
        f"<b>Наш адрес:</b>\n{escape(config.cargo_address)}\n\n"
        f"<b>В нашем карго запрещены товары:</b>\n"
        f"{escape(config.prohibited_goods)}\n\n"
        f"<b>График работы:</b>\n{escape(config.work_hours)}"
    )


@router.message(F.text == BT_INFO)
async def info(message: Message, config: Config, bot: Bot) -> None:
    text = _info_text(config)
    if config.instruction_video_url:
        text += f"\n\n<b>Видео-инструкция:</b> {escape(config.instruction_video_url)}"
    await message.answer(text, reply_markup=main_menu())
    await _send_instruction_video(message, config, bot)


@router.message(F.text == BT_STATUS)
async def status_stub(message: Message, db_pool: SqlitePool) -> None:
    user = await get_user_by_telegram_id(db_pool, int(message.from_user.id))
    if not user:
        await message.answer(
            "Сначала пройдите регистрацию или войдите по коду.",
            reply_markup=welcome_menu(),
        )
        return
    await message.answer(
        "Как только товар прибудет, бот отправит уведомление.",
        reply_markup=main_menu(),
    )


@router.message(F.text == BT_LOGIN)
async def login_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(login_after_profile=True, pending_client_code=None)
    await state.set_state(RegisterStates.waiting_phone)
    await message.answer(
        "Вход.\n\n"
        "Шаг 1 из 3: отправьте номер телефона кнопкой ниже или текстом "
        "(+996…, +7…, с кодом страны).",
        reply_markup=phone_request_keyboard(),
    )


@router.message(F.text == BT_REGISTER)
async def register_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(pending_client_code=None, login_after_profile=False)
    await state.set_state(RegisterStates.waiting_phone)
    await message.answer(
        "Регистрация.\n\nШаг 1 из 2: отправьте номер телефона "
        "кнопкой ниже или текстом (+996…, +7…, с кодом страны).",
        reply_markup=phone_request_keyboard(),
    )


@router.message(RegisterStates.waiting_phone, F.contact)
async def register_phone_contact(
    message: Message, state: FSMContext
) -> None:
    if not message.contact or not message.contact.phone_number:
        await message.answer("Не удалось прочитать номер. Попробуйте ещё раз.")
        return
    phone = _normalize_phone(message.contact.phone_number)
    if not phone:
        await message.answer("Некорректный номер. Отправьте телефон ещё раз.")
        return
    await _on_phone_saved(message, state, phone)


@router.message(RegisterStates.waiting_phone, F.text, _not_command)
async def register_phone_text(message: Message, state: FSMContext) -> None:
    if (message.text or "") in MENU_TEXTS:
        return
    if (message.text or "") == BT_SHARE_PHONE:
        await message.answer("Нажмите кнопку «Отправить номер телефона» или введите номер текстом.")
        return
    phone = _normalize_phone(message.text or "")
    if not phone:
        await message.answer(
            "Не удалось распознать номер. Примеры: +996700123456, 0700123456, "
            "+79991234567, +380501234567"
        )
        return
    await _on_phone_saved(message, state, phone)


@router.message(RegisterStates.waiting_fio, F.text, _not_command)
async def register_fio(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
    config: Config,
) -> None:
    if (message.text or "") in MENU_TEXTS:
        return
    fio = " ".join((message.text or "").split())
    if not _is_valid_fio(fio):
        await message.answer(
            "Укажите ФИО полностью: фамилия, имя и отчество через пробел."
        )
        return
    await state.update_data(full_name=fio)
    data = await state.get_data()
    if data.get("login_after_profile") and not data.get("pending_client_code"):
        await state.set_state(RegisterStates.waiting_client_code)
        await message.answer(
            "Шаг 3 из 3: введите ваш код клиента (например, 600-kar)."
        )
        return
    if data.get("pending_client_code"):
        await _finish_login_profile(message, state, db_pool)
        return
    await _finish_registration(message, state, db_pool, config)


@router.message(StateFilter(None), F.text, _not_command)
async def login_by_code_direct(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
) -> None:
    text = message.text or ""
    if text in MENU_TEXTS:
        return

    code = _normalize_client_code(text)
    if not _is_valid_client_code(code):
        return

    await _login_with_code(message, state, db_pool, code)


@router.message(Command("change_code"))
async def change_code(message: Message, state: FSMContext) -> None:
    await message.answer("Отправьте новый код клиента.")
    await state.set_state(RegisterStates.waiting_client_code)


@router.message(RegisterStates.waiting_client_code, F.text, _not_command)
async def register_client_code(
    message: Message,
    state: FSMContext,
    db_pool: SqlitePool,
) -> None:
    code = _normalize_client_code(message.text or "")
    if not _is_valid_client_code(code):
        await message.answer(
            "Код выглядит некорректно. Пример: 600-kar или K1234"
        )
        return

    data = await state.get_data()
    if data.get("login_after_profile"):
        phone = data.get("phone")
        full_name = data.get("full_name")
        if not phone or not full_name:
            await message.answer(
                "Сначала укажите телефон и ФИО. Нажмите «Войти» и пройдите шаги 1–2."
            )
            return
        existing = await get_user_by_code(db_pool, code)
        if existing and int(existing["telegram_id"]) != int(message.from_user.id):
            await message.answer(
                "Этот код уже привязан к другому аккаунту. "
                "Проверьте код или пройдите регистрацию."
            )
            return
        username = message.from_user.username if message.from_user else None
        try:
            await upsert_user(
                db_pool,
                client_code=code,
                telegram_id=int(message.from_user.id),
                username=username,
                phone=phone,
                full_name=full_name,
            )
        except Exception:
            await message.answer(
                "Не удалось войти. Проверьте код или пройдите регистрацию.",
                reply_markup=welcome_menu(),
            )
            return
        await state.clear()
        await message.answer(
            f"Добро пожаловать! Ваш код: <b>{code}</b>\n\n"
            f"ФИО: {full_name}\n"
            f"Телефон: {phone}",
            reply_markup=main_menu(),
        )
        return

    await _login_with_code(message, state, db_pool, code)
