from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.database.db import SqlitePool


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, pool: SqlitePool) -> None:
        super().__init__()
        self._pool = pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["db_pool"] = self._pool
        return await handler(event, data)
