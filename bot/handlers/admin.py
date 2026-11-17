from __future__ import annotations

import logging
import os
import tempfile

from aiogram import Bot
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import Config
from bot.database.db import SqlitePool
from bot.services.excel_parser import ExcelParseError, parse_client_codes_from_xlsx
from bot.services.notifier import notify_arrivals
from bot.states import AdminUploadStates

router = Router(name=__name__)
logger = logging.getLogger(__name__)


def _is_admin(message: Message, config: Config) -> bool:
    if not message.from_user:
        return False
    return int(message.from_user.id) in config.admin_ids


def _require_admin(message: Message, config: Config) -> bool:
    """Проверка админа (временно отключена — загрузка для всех)."""
    # if not _is_admin(message, config):
    #     await message.answer("Эта команда доступна только администратору.")
    #     return False
    return True


async def _process_excel_upload(
    message: Message,
    state: FSMContext,
    config: Config,
    db_pool: SqlitePool,
    bot: Bot,
) -> None:
    doc = message.document
    if not doc:
        await message.answer("Не вижу файл. Пришлите .xlsx документ.")
        return

    if not (doc.file_name or "").lower().endswith(".xlsx"):
        await message.answer("Нужен файл формата .xlsx")
        return

    user_id = message.from_user.id if message.from_user else "unknown"
    logger.info("User %s uploaded file %s", user_id, doc.file_name)

    tmp_dir = tempfile.mkdtemp(prefix="cargobot_")
    tmp_path = os.path.join(tmp_dir, doc.file_name or "upload.xlsx")

    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, destination=tmp_path)
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to download excel: %s", e)
        await message.answer("Не удалось скачать файл из Telegram. Попробуйте ещё раз.")
        return

    try:
        result = parse_client_codes_from_xlsx(tmp_path)
    except ExcelParseError as e:
        await message.answer(f"Ошибка Excel: {e}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected excel parse error: %s", e)
        await message.answer("Не удалось обработать Excel (непредвиденная ошибка).")
        return

    total_codes = len(result.arrivals)
    await message.answer(
        f"Файл принят. Строк просмотрено: {result.total_rows_seen}. "
        f"Уникальных кодов клиентов: {total_codes}. Начинаю уведомления..."
    )

    sent = await notify_arrivals(
        bot=bot,
        pool=db_pool,
        arrivals=result.arrivals,
        cargo_address=config.cargo_address,
    )

    logger.info(
        "Excel processed: rows=%s unique_codes=%s notified=%s",
        result.total_rows_seen,
        total_codes,
        sent,
    )

    await message.answer(
        f"Готово. Уведомлений отправлено: {sent} из {total_codes} кодов."
    )
    await state.clear()


@router.message(Command("upload"))
async def upload_cmd(message: Message, state: FSMContext, config: Config) -> None:
    if not _require_admin(message, config):
        return
    await state.clear()
    await state.set_state(AdminUploadStates.waiting_excel)
    await message.answer("Пришлите Excel файл (.xlsx).")


@router.message(AdminUploadStates.waiting_excel, F.document)
async def handle_excel_upload(
    message: Message,
    state: FSMContext,
    config: Config,
    db_pool: SqlitePool,
    bot: Bot,
) -> None:
    if not _require_admin(message, config):
        return
    await _process_excel_upload(message, state, config, db_pool, bot)


@router.message(F.document)
async def handle_excel_direct(
    message: Message,
    state: FSMContext,
    config: Config,
    db_pool: SqlitePool,
    bot: Bot,
) -> None:
    """Excel без /upload — для всех пользователей (проверка админа отключена)."""
    if not _require_admin(message, config):
        return
    doc = message.document
    if not doc or not (doc.file_name or "").lower().endswith(".xlsx"):
        return
    await _process_excel_upload(message, state, config, db_pool, bot)
