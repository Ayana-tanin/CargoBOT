from __future__ import annotations

import aiosqlite

from bot.database.db import SqlitePool


async def allocate_next_client_code(pool: SqlitePool) -> str:
    async with pool.acquire() as conn:
        cursor = await conn.execute(
            "SELECT value FROM app_settings WHERE key = 'next_client_number'"
        )
        row = await cursor.fetchone()
        if row is None:
            number = 600
        else:
            number = int(row[0])
        await conn.execute(
            """
            UPDATE app_settings
            SET value = ?
            WHERE key = 'next_client_number'
            """,
            (str(number + 1),),
        )
        return f"{number}-kar"


async def upsert_user(
    pool: SqlitePool,
    *,
    client_code: str,
    telegram_id: int,
    username: str | None,
    phone: str | None = None,
    full_name: str | None = None,
) -> None:
    client_code = client_code.strip()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (
                client_code, telegram_id, username, phone, full_name
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (telegram_id) DO UPDATE SET
                client_code = excluded.client_code,
                username = excluded.username,
                phone = excluded.phone,
                full_name = excluded.full_name
            """,
            (client_code, telegram_id, username, phone, full_name),
        )


async def add_user(
    pool: SqlitePool, client_code: str, telegram_id: int, username: str | None
) -> None:
    await upsert_user(
        pool,
        client_code=client_code,
        telegram_id=telegram_id,
        username=username,
    )


async def get_user_by_code(
    pool: SqlitePool, client_code: str
) -> aiosqlite.Row | None:
    client_code = client_code.strip()
    async with pool.acquire() as conn:
        cursor = await conn.execute(
            "SELECT * FROM users WHERE client_code = ?",
            (client_code,),
        )
        return await cursor.fetchone()


async def get_user_by_telegram_id(
    pool: SqlitePool, telegram_id: int
) -> aiosqlite.Row | None:
    async with pool.acquire() as conn:
        cursor = await conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        return await cursor.fetchone()


async def save_arrival(pool: SqlitePool, client_code: str) -> bool:
    """
    Returns True if inserted (i.e. first time), False if already existed.
    """
    client_code = client_code.strip()
    async with pool.acquire() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO arrivals (client_code)
            VALUES (?)
            ON CONFLICT (client_code) DO NOTHING
            RETURNING id
            """,
            (client_code,),
        )
        row = await cursor.fetchone()
        return row is not None


async def is_already_notified(pool: SqlitePool, client_code: str) -> bool:
    client_code = client_code.strip()
    async with pool.acquire() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM arrivals WHERE client_code = ?",
            (client_code,),
        )
        row = await cursor.fetchone()
        return row is not None
