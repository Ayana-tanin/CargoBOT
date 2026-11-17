# CargoBOT — уведомления о прибытии товара (Telegram)

Telegram-бот для карго-компании на **Python + aiogram 3.x + PostgreSQL**.

## Роли
- **Админ**
  - Загружает Excel-файл с кодами клиентов командой `/upload`
- **Пользователь**
  - Регистрируется по **коду клиента**
  - Получает уведомление, когда товар прибыл (по коду клиента)

## Как работает уведомление (ключевая логика)
1. Админ загружает `.xlsx`.
2. Бот парсит **колонку B** на **первом листе** и собирает **уникальные** `client_code` внутри файла.
3. Для каждого `client_code` бот:
   - ищет пользователя в таблице `users`
   - проверяет факт уведомления через `arrivals` (защита от дублей)
   - если уведомления ещё не было — отправляет пользователю сообщение и сохраняет факт в `arrivals`

## UX и команды
- Кнопки:
  - **📦 Проверить статус** — заглушка
  - **ℹ️ Информация** — описание + видео-инструкция (если настроено)
- Команды:
  - `/start` — регистрация (если пользователь ещё не в БД)
  - `/change_code` — обновить `client_code`
  - `/upload` — загрузить Excel (только админ)

## FSM (обязательная часть)
- `RegisterStates.waiting_client_code`
  - ввод кода клиента
- `AdminUploadStates.waiting_excel`
  - ожидание Excel файла от админа

## Формат кода клиента
Поддерживаются примеры:
- `K1234`
- `L23435423`
- `E-23435t`

Правило в текущей реализации:
- 1 латинская буква
- опционально `-`
- 1..8 цифр
- опционально 1 латинская буква в конце

Пробелы в коде убираются автоматически.

## Видео-инструкция (отправка файлом / через file_id)
В `/start` и **ℹ️ Информация** бот отправляет видео, если настроено:
- `INSTRUCTION_VIDEO_FILE_ID` — Telegram `file_id` (предпочтительно)
- или `INSTRUCTION_VIDEO_PATH` — локальный путь к mp4 на машине, где запущен бот

Если настроено `INSTRUCTION_VIDEO_FILE_ID`, бот использует `bot.send_video(..., video=file_id)`.

## Excel формат
- Формат файла: `.xlsx`
- Лист: берём **первый**
- Колонка: **B**
- Пустые значения игнорируются
- Дубликаты удаляются внутри файла
- Для больших файлов используется `openpyxl` в режиме `read_only=True`

## Антиспам (ограничение скорости)
При отправке уведомлений используется небольшая задержка:
- параметр `delay_seconds` в `bot/services/notifier.py` (по умолчанию `0.05` сек между сообщениями)

## PostgreSQL схема
Создаётся автоматически при старте бота (см. `bot/database/db.py`).

Таблица `users`:
- `id` BIGSERIAL PRIMARY KEY
- `client_code` TEXT UNIQUE NOT NULL
- `telegram_id` BIGINT UNIQUE NOT NULL
- `username` TEXT

Таблица `arrivals`:
- `id` BIGSERIAL PRIMARY KEY
- `client_code` TEXT NOT NULL
- `notified_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()
- `UNIQUE(client_code)` — защита от повторных уведомлений

> Примечание: в текущей реализации `telegram_id` тоже UNIQUE. Если нужно иначе — скажите, поправим.

## Реализованные функции (как в `idea.md`)
Они находятся в `bot/database/queries.py`:
- `add_user(pool, client_code, telegram_id, username)`
- `get_user_by_code(pool, client_code)`
- `save_arrival(pool, client_code)` — вставка в `arrivals` с защитой от дублей
- `is_already_notified(pool, client_code)` — проверка факта уведомления (в текущем коде фактически используется `save_arrival`, который сам делает `ON CONFLICT DO NOTHING`)

## Структура проекта
```text
bot/
 ├── main.py
 ├── config.py
 ├── states.py
 ├── handlers/
 │    ├── user.py
 │    └── admin.py
 ├── keyboards/
 │    └── user.py
 ├── middlewares/
 │    ├── db.py
 │    └── config.py
 ├── database/
 │    ├── db.py
 │    ├── models.py (заготовка)
 │    └── queries.py
 └── services/
      ├── excel_parser.py
      └── notifier.py
```

## Настройки (.env)
Скопируйте `.env.example` и заполните:
- `BOT_TOKEN`
- `DATABASE_URL`
- `ADMIN_IDS` (ID через запятую, пример: `123,456`)

Видео (опционально):
- `INSTRUCTION_VIDEO_FILE_ID` (лучший вариант)
- `INSTRUCTION_VIDEO_PATH` (локальный путь к mp4)

Опционально:
- `WORK_HOURS`
- `INSTRUCTION_TEXT`

## Быстрый старт (запуск)
1) Установите зависимости:
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

2) Создайте БД PostgreSQL:
```sql
CREATE DATABASE cargobot;
```

3) Запуск:
```bash
python -m bot.main
```

## Логирование
Основной лог пишет `stdout` в формате:
- `timestamp | LEVEL | module | message`

## Что нужно уточнить у вас (если хотите довести до идеала)
- Точный формат `client_code`, если он отличается от указанного правила.
- Видео: как вы хотите хранить инструкцию (через `file_id` или файл на сервере).

