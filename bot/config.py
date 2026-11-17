from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from dotenv import dotenv_values

# Project root: .../CargoBOT (parent of the `bot` package)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    admin_ids: set[int]
    work_hours: str
    instruction_text: str
    instruction_video_url: str | None
    instruction_video_file_id: str | None
    instruction_video_path: str | None
    cargo_address: str
    prohibited_goods: str
    client_code_start: int


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    items = [p.strip() for p in raw.split(",") if p.strip()]
    result: set[int] = set()
    for it in items:
        try:
            result.add(int(it))
        except ValueError:
            continue
    return result


def load_config(env_path: str | Path | None = None) -> Config:
    if env_path is not None:
        path = Path(env_path)
    else:
        root_env = _PROJECT_ROOT / ".env"
        bot_env = _PROJECT_ROOT / "bot" / ".env"
        if root_env.is_file():
            path = root_env
        elif bot_env.is_file():
            path = bot_env
        else:
            path = root_env
    env = dotenv_values(path)

    bot_token = (env.get("BOT_TOKEN") or "").strip()
    database_url = (env.get("DATABASE_URL") or "").strip()
    admin_ids = _parse_admin_ids(env.get("ADMIN_IDS"))

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in .env")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in .env")

    work_hours = (env.get("WORK_HOURS") or "Пн–Сб 09:00–18:00").strip()
    instruction_text = (
        env.get("INSTRUCTION_TEXT") or "Пожалуйста, отправьте ваш код клиента."
    ).strip()
    instruction_video_url = (env.get("INSTRUCTION_VIDEO_URL") or "").strip() or None
    instruction_video_file_id = (
        env.get("INSTRUCTION_VIDEO_FILE_ID") or ""
    ).strip() or None
    instruction_video_path = (env.get("INSTRUCTION_VIDEO_PATH") or "").strip() or None
    cargo_address = (
        env.get("CARGO_ADDRESS") or "Бишкек, ул Месароша ...."
    ).strip()
    prohibited_goods = (
        env.get("PROHIBITED_GOODS")
        or (
            "оружие и боеприпасы; наркотические и психотропные вещества; "
            "взрывчатые и легковоспламеняющиеся материалы; "
            "скоропортящиеся продукты "
        )
    ).strip().replace("\\n", "\n")
    raw_start = (env.get("CLIENT_CODE_START") or "600").strip()
    try:
        client_code_start = int(raw_start)
    except ValueError:
        client_code_start = 600

    return Config(
        bot_token=bot_token,
        database_url=database_url,
        admin_ids=admin_ids,
        work_hours=work_hours,
        instruction_text=instruction_text,
        instruction_video_url=instruction_video_url,
        instruction_video_file_id=instruction_video_file_id,
        instruction_video_path=instruction_video_path,
        cargo_address=cargo_address,
        prohibited_goods=prohibited_goods,
        client_code_start=client_code_start,
    )

