"""
main.py — Telegram-бот расписания колледжа.

Логика:
  1. Берём самый свежий PDF из папки Google Диска (через service-аккаунт).
  2. pdfplumber вытаскивает из PDF весь текст.
  3. Текст + промпт отправляются в бесплатный API Gemini.
  4. Ответ Gemini (готовый красивый список пар) выводится пользователю.

Кнопки: «На сегодня», «На завтра».
"""
import asyncio
import io
import logging
import os
import time
from datetime import date, timedelta

import pdfplumber
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BotCommand, KeyboardButton, Message, ReplyKeyboardMarkup
from google import genai
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("schedule_bot")

# ---------------------------------------------------------------------------
# Инициализация клиентов
# ---------------------------------------------------------------------------
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# --- Google Drive (service account) ---
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_drive_service = None

# --- Gemini ---
_genai_client = None

# Простейший in-memory кэш скачанного PDF, чтобы не дёргать Диск каждый раз.
_pdf_cache = {"data": None, "ts": 0.0}

# Русские названия месяцев для красивой даты в промпте.
_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


# ---------------------------------------------------------------------------
# Google Drive: берём самый свежий PDF
# ---------------------------------------------------------------------------
def _get_drive_service():
    """Лениво создаём клиент Диска (один раз на процесс)."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    creds = service_account.Credentials.from_service_account_file(
        config.CREDENTIALS_FILE, scopes=_DRIVE_SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def _download_latest_pdf() -> bytes:
    """Синхронно: ищем самый свежий PDF в папке и скачиваем его содержимое."""
    service = _get_drive_service()
    query = (
        f"'{config.GOOGLE_DRIVE_FOLDER_ID}' in parents and "
        "mimeType = 'application/pdf' and trashed = false"
    )
    results = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            orderBy="createdTime desc",
            pageSize=1,
            fields="files(id, name, createdTime)",
        )
        .execute()
    )
    files = results.get("files", [])
    if not files:
        raise RuntimeError(
            "В папке Google Диска не найдено ни одного PDF. "
            "Проверьте GOOGLE_DRIVE_FOLDER_ID и доступ сервисного аккаунта к папке."
        )

    file_id = files[0]["id"]
    logger.info("Берём PDF: %s (%s)", files[0].get("name"), files[0].get("createdTime"))

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


async def get_latest_pdf_bytes() -> bytes:
    """Возвращает содержимое самого свежего PDF (с учётом кэша)."""
    now = time.time()
    if _pdf_cache["data"] is not None and (now - _pdf_cache["ts"]) < config.PDF_CACHE_TTL:
        return _pdf_cache["data"]

    data = await asyncio.to_thread(_download_latest_pdf)
    _pdf_cache["data"] = data
    _pdf_cache["ts"] = now
    return data


# ---------------------------------------------------------------------------
# pdfplumber: вытаскиваем текст из PDF
# ---------------------------------------------------------------------------
def _extract_text(data: bytes) -> str:
    parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


async def extract_text_from_pdf(data: bytes) -> str:
    return await asyncio.to_thread(_extract_text, data)


# ---------------------------------------------------------------------------
# Gemini: просим расписание для группы на конкретную дату
# ---------------------------------------------------------------------------
def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _genai_client


def _format_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month]} {d.year}"


def _build_prompt(target_date: date) -> str:
    date_str = _format_date(target_date)
    return (
        f"Из предоставленного текста/скрина расписания найди пары для группы "
        f"'{config.GROUP_NAME}' на дату {date_str}. "
        f"Верни только список пар в красивом формате для телеграма "
        f"(с эмодзи, с указанием времени, предмета, кабинета и преподавателя, "
        f"если они есть). "
        f"Если пар нет, напиши ровно: 'Пар нет'."
    )


async def ask_gemini(target_date: date) -> str:
    """Полный конвейер: Диск -> PDF -> текст -> Gemini -> ответ."""
    pdf_bytes = await get_latest_pdf_bytes()
    schedule_text = await extract_text_from_pdf(pdf_bytes)

    if not schedule_text.strip():
        return (
            "⚠️ Не удалось извлечь текст из PDF. "
            "Возможно, это отсканированный документ без слоя текста "
            "(pdfplumber не умеет распознавать текст с картинок)."
        )

    prompt = _build_prompt(target_date)
    client = _get_genai_client()

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=config.GEMINI_MODEL,
        contents=[prompt, schedule_text],
    )
    return (response.text or "Пар нет").strip()


# ---------------------------------------------------------------------------
# Клавиатура и обработчики
# ---------------------------------------------------------------------------
def get_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="На сегодня"), KeyboardButton(text="На завтра")],
        ],
        resize_keyboard=True,
    )


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"👋 Привет! Я бот расписания для группы <b>{config.GROUP_NAME}</b>.\n\n"
        "Выбери день, на который нужно расписание:",
        reply_markup=get_keyboard(),
    )


async def _answer_schedule(message: Message, target: date) -> None:
    await message.answer("⏳ Ищу расписание, подожди немного…")
    try:
        result = await ask_gemini(target)
    except Exception as exc:  # ловим всё, чтобы бот не падал
        logger.exception("Ошибка при получении расписания")
        result = f"❌ Произошла ошибка: {exc}"
    await message.answer(result, reply_markup=get_keyboard())


@dp.message(F.text == "На сегодня")
async def on_today(message: Message) -> None:
    await _answer_schedule(message, date.today())


@dp.message(F.text == "На завтра")
async def on_tomorrow(message: Message) -> None:
    await _answer_schedule(message, date.today() + timedelta(days=1))


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
async def main() -> None:
    # --- Для хостинга как Web Service: поднимаем заглушку на $PORT,
    # чтобы платформа не убила процесс по таймауту проверки здоровья.
    # На worker-хостингах (например, Koyeb worker) переменная PORT обычно
    # не задана — тогда заглушка не поднимается и бот работает как обычный
    # worker (в этом случае в Procfile используется строка `worker:`).
    port = os.getenv("PORT")
    if port:
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class _HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                return

        def _serve():
            HTTPServer(("0.0.0.0", int(port)), _HealthHandler).serve_forever()

        threading.Thread(target=_serve, daemon=True).start()
        logger.info("Health-check заглушка поднята на порту %s", port)

    # Чтобы при перезапуске на хостинге не было конфликта вебхука:
    await bot.delete_webhook(drop_pending_updates=True)

    # Меню команд (покажется кнопкой-меню в Telegram):
    await bot.set_my_commands([BotCommand(command="start", description="Запустить бота")])

    logger.info("Бот запущен. Ожидаю сообщений…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
