from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot

from bot.database.db import SqlitePool
from bot.database.queries import get_user_by_code, save_arrival
from bot.services.excel_parser import ClientArrivalData

logger = logging.getLogger(__name__)


def format_arrival_message(
    *,
    full_name: str | None,
    client_code: str,
    cargo_address: str,
    arrival: ClientArrivalData,
) -> str:
    name = escape(full_name.strip()) if full_name and full_name.strip() else "клиент"
    code = escape(client_code)
    address = escape(cargo_address)
    goods_count = arrival.declared_goods_count or arrival.rows_count

    lines = [
        f"Дорогой {name}, ваш код: <b>{code}</b>.",
        "",
        "Ваши товары прибыли по адресу:",
        address,
        "",
        f"Количество товаров: <b>{goods_count}</b>",
        "",
        "Прибывшие товары:",
    ]

    if arrival.products:
        for idx, product in enumerate(arrival.products, start=1):
            lines.append(f"{idx}. {escape(product)}")
    else:
        lines.append("— список в колонке C не указан")

    return "\n".join(lines)


async def notify_arrivals(
    *,
    bot: Bot,
    pool: SqlitePool,
    arrivals: list[ClientArrivalData],
    cargo_address: str,
    delay_seconds: float = 0.05,
) -> int:
    """
    Для каждого client_code из Excel:
      - найти пользователя в БД
      - если ещё не уведомляли — отправить персональное сообщение
    """
    sent = 0
    by_code = {item.client_code: item for item in arrivals}

    for code, arrival in by_code.items():
        user = await get_user_by_code(pool, code)
        if not user:
            continue

        inserted = await save_arrival(pool, code)
        if not inserted:
            continue

        text = format_arrival_message(
            full_name=user["full_name"],
            client_code=code,
            cargo_address=cargo_address,
            arrival=arrival,
        )

        try:
            await bot.send_message(chat_id=int(user["telegram_id"]), text=text)
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to notify client_code=%s: %s", code, e)

        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return sent
