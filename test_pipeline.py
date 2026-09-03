"""
test_pipeline.py — быстрая проверка связки без Telegram.

Проверяет, что:
  * credentials.json видит папку на Диске и находит свежий PDF;
  * pdfplumber вытаскивает из него текст;
  * Gemini возвращает осмысленный ответ.

Запуск:
    python test_pipeline.py
(нужны заполненные BOT_TOKEN, GEMINI_API_KEY, GOOGLE_DRIVE_FOLDER_ID в .env)
"""
import asyncio
from datetime import date

import main  # подхватит config и создаст объект Bot (BOT_TOKEN обязателен)


async def _run() -> None:
    print("→ Запрашиваю расписание на сегодня через Gemini…\n")
    text = await main.ask_gemini(date.today())
    print("=== ОТВЕТ GEMINI ===")
    print(text)


if __name__ == "__main__":
    asyncio.run(_run())
