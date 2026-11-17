from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

# Как в config.py: каталог CargoBOT (родитель пакета bot).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_sqlite_path(database_url: str) -> Path:
    database_url = database_url.strip()
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        raw = database_url[len(prefix) :]
        p = Path(raw)
        return p if p.is_absolute() else _PROJECT_ROOT / p
    if "://" not in database_url and database_url.lower().endswith(".db"):
        p = Path(database_url)
        return p if p.is_absolute() else _PROJECT_ROOT / p
    raise RuntimeError(
        "DATABASE_URL must be sqlite:///path/to.db "
        f"(relative paths are under project root) or a .db file path, got: {database_url!r}"
    )


class SqlitePool:
    """Один файл SQLite; каждое acquire — отдельное соединение (WAL)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @asynccontextmanager
    async def acquire(self):
        conn = await aiosqlite.connect(self._path)
        conn.row_factory = aiosqlite.Row
        try:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            yield conn
            await conn.commit()
        finally:
            await conn.close()

    async def close(self) -> None:
        return None


async def create_pool(database_url: str) -> SqlitePool:
    path = _resolve_sqlite_path(database_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqlitePool(path)


async def _migrate_users(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in await cursor.fetchall()}
    if "phone" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "full_name" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")


async def init_db(pool: SqlitePool, client_code_start: int = 600) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_code TEXT NOT NULL UNIQUE,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                phone TEXT,
                full_name TEXT
            );
            """
        )
        await _migrate_users(conn)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        await conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES ('next_client_number', ?)
            ON CONFLICT (key) DO NOTHING
            """,
            (str(client_code_start),),
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS arrivals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_code TEXT NOT NULL UNIQUE,
                notified_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )


async def clear_database(pool: SqlitePool, *, client_code_start: int = 600) -> None:
    """Очистить users, arrivals и сбросить счётчик кодов."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users")
        await conn.execute("DELETE FROM arrivals")
        await conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES ('next_client_number', ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (str(client_code_start),),
        )
