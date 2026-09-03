"""
config.py — читает все секреты и настройки из .env (или переменных окружения).
Никаких токенов в коде быть не должно — только здесь они подтягиваются.
"""

import base64
import os
import tempfile

from dotenv import load_dotenv

# Подгружаем .env из текущей папки (на хостинге Render/Koyeb переменные
# окружения задаются в панели, и load_dotenv просто ничего не сделает — это ок).
load_dotenv()
print("ФАЙЛ .env НАЙДЕН:", os.path.exists(".env"))

# --- Токены и ключи ---
# Токен Telegram-бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Бесплатный ключ Google Gemini (из Google AI Studio)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ID папки Google Диска, откуда берём свежий PDF
# (берётся из URL папки: https://drive.google.com/drive/folders/<ВОТ_ЭТО_ID>)
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# --- Настройки ---
# Название группы, для которой ищем пары
GROUP_NAME = os.getenv("GROUP_NAME", "26-Д")

# Путь к credentials.json сервисного аккаунта Google (локально).
# На хостинге безопаснее не хранить файл, а передать закодированный JSON
# через переменную окружения GOOGLE_CREDENTIALS_B64 (см. README, раздел 4).
_b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
if _b64:
    # раскодируем service-account JSON во временный файл и используем его
    _raw = base64.b64decode(_b64)
    _tmp = tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False)
    _tmp.write(_raw)
    _tmp.close()
    CREDENTIALS_FILE = _tmp.name
else:
    CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Модель Gemini. gemini-2.0-flash — быстрая и бесплатная на free-тарифе.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Сколько секунд кэшировать скачанный PDF в памяти,
# чтобы не лазить в Диск при каждом нажатии кнопки (по умолчанию 1 час).
PDF_CACHE_TTL = int(os.getenv("PDF_CACHE_TTL", "3600"))


def _check_required() -> None:
    """Быстрая проверка, что самое важное задано, иначе — понятная ошибка."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not GOOGLE_DRIVE_FOLDER_ID:
        missing.append("GOOGLE_DRIVE_FOLDER_ID")
    if missing:
        raise RuntimeError(
            "Не заданы переменные окружения: "
            + ", ".join(missing)
            + ". Создайте .env (пример в .env.example) или задайте их на хостинге."
        )


_check_required()
