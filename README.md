# Telegram-бот расписания колледжа

Бот берёт самый свежий PDF с расписанием из папки Google Диска, вытаскивает из
него текст через `pdfplumber` и отдаёт в бесплатный API **Google Gemini**, который
возвращает аккуратный список пар для группы на нужную дату.

Кнопки: **«На сегодня»**, **«На завтра»**.

---

## 1. Получаем бесплатный API-ключ Gemini

Gemini API (не Vertex AI) имеет бесплатный тариф — для нашего бота хватит с головой.

1. Открой **Google AI Studio**: https://aistudio.google.com/
2. Войди под своим Google-аккаунтом.
3. В меню слева (или вверху) найди **"Get API key"** → **"Create API key"**
   (прямая ссылка: https://aistudio.google.com/apikey ).
4. Скопируй сгенерированный ключ (начинается с `AIza…`).
5. Вставь его в `.env` как `GEMINI_API_KEY=...`.

> 💡 Бесплатный лимит Gemini 2.0 Flash: ~15 запросов/мин и ~1500 запросов/день.
> Для учебного расписания этого более чем достаточно. Если упрёшься в лимит —
> поменяй модель на `gemini-2.0-flash-lite` (ещё дешевле) в `GEMINI_MODEL`.

---

## 2. Google Диск (откуда берём PDF)

У тебя уже есть `credentials.json` — это сервисный аккаунт. Чтобы он видел
папку с расписанием:

1. Открой папку на Диске, нажми **Настройки доступа → Открыть доступ**.
2. В поле «пригласить людей» вставь **email сервисного аккаунта** из
   `credentials.json` (поле `client_email`, выглядит как
   `something@something.iam.gserviceaccount.com`). Дай ему роль **Читатель**.
3. Скопируй ID папки из URL (`.../folders/ВОТ_ЭТО_ID`) в `GOOGLE_DRIVE_FOLDER_ID`.

---

## 3. Локальный запуск

```bash
pip install -r requirements.txt
cp .env.example .env      # и заполни значения
python main.py
```

---

## 4. Деплой на бесплатный хостинг

### Подготовка (важно: не свети секреты)
1. Создай репозиторий на GitHub и залей туда проект.
2. **Не коммить `.env` и `credentials.json`** — они уже в `.gitignore`.
   Токены и ключ сервис-аккаунта попадают на хостинг только через переменные
   окружения.
3. Для `credentials.json` на хостинге используй переменную
   `GOOGLE_CREDENTIALS_B64` — это base64 от твоего `credentials.json`.
   Получить его локально:
   - Windows (PowerShell): `[Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))`
   - macOS/Linux: `base64 -w0 credentials.json`
   Вставь вывод в переменную окружения `GOOGLE_CREDENTIALS_B64` на хостинге.

### Render (бесплатно: Web Service + UptimeRobot)
1. render.com → New → **Web Service** → подключи репо.
2. Build Command: `pip install -r requirements.txt`
   Start Command: `python main.py`
   (в `main.py` уже есть заглушка на `$PORT`, поэтому Render не убьёт процесс
   по таймауту проверки здоровья).
3. Environment variables добавь: `BOT_TOKEN`, `GEMINI_API_KEY`,
   `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_CREDENTIALS_B64`
   (и опционально `GROUP_NAME`, `GEMINI_MODEL`).
4. Deploy. В логах должно появиться «Бот запущен».
5. Render Free засыпает после ~15 мин простоя. Чтобы бот «не спал» днём,
   заведи бесплатный мониторинг **UptimeRobot** (тип HTTP, URL любой — заглушка
   отвечает 200) с интервалом 5–25 мин.

### Koyeb (есть бесплатный worker)
1. New Service → GitHub → выбери репо. Тип **Worker**,
   Build: `pip install -r requirements.txt`, Run: `python main.py`.
2. Environment variables — те же, что для Render, включая `GOOGLE_CREDENTIALS_B64`.
3. Caveat: бесплатный worker на Koyeb засыпает после ~15 мин и **не**
   просыпается сам по сообщению в Telegram (нет входящего HTTP) — бот будет
   «мёртв» большую часть времени. Для стабильной работы нужен платный
   инстанс либо Render + UptimeRobot (см. выше).

### Fly.io (альтернатива, не спит на бесплатном лимите)
Нужен `flyctl` и минимальный `fly.toml`/`Dockerfile`. Бесплатный лимит не
засыпает, но требует чуть больше настройки — скажи, если выберешь этот путь.

> ☀️ Для учебного расписания **Render Free + UptimeRobot** — самый простой
> рабочий бесплатный вариант. Любой free-тариф ограничен по ресурсам/времени.

---

## Структура

```
.
├── main.py              # код бота
├── config.py            # чтение токенов из .env
├── test_pipeline.py     # проверка Диск→Gemini без Telegram
├── requirements.txt     # зависимости
├── Procfile             # команды запуска для хостинга
├── .env.example         # пример переменных окружения
├── .gitignore           # исключает .env и credentials.json из git
└── credentials.json     # сервисный аккаунт Google (локально; на хосте — через B64)
```
