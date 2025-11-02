# bot_logic.py
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Попытаемся импортировать современный клиент g4f, но если его нет — используем старый интерфейс
try:
    from g4f.client import Client as G4FClient
    HAVE_CLIENT = True
except Exception:
    import g4f
    G4FClient = None
    HAVE_CLIENT = False

# Токен берём из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан в переменных окружения")

# Доп. параметры g4f можно задавать через переменные окружения:
# G4F_PROVIDER  - имя провайдера/источника (если поддерживается)
# G4F_SYSTEM_PROMPT - системный промпт для контекста
G4F_PROVIDER = os.getenv("G4F_PROVIDER")
G4F_SYSTEM_PROMPT = os.getenv("G4F_SYSTEM_PROMPT", "Ты помощник, отвечай коротко и по делу.")

# Вспомогательная функция: приводим ответ g4f к строке
def normalize_g4f_response(resp):
    """
    Попытка извлечь текст из различных форматов,
    которые может вернуть g4f (str, dict, iterable).
    """
    # строка — возвращаем как есть
    if isinstance(resp, str):
        return resp.strip()
    # словарь — пробуем стандартные поля
    if isinstance(resp, dict):
        # OpenAI-style
        try:
            return resp["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        # простое поле text
        if "text" in resp and isinstance(resp["text"], str):
            return resp["text"].strip()
        # join всех значений
        try:
            return " ".join(str(v) for v in resp.values()).strip()
        except Exception:
            return str(resp)
    # итерируемый (поток)
    try:
        parts = []
        for chunk in resp:
            # иногда chunk — dict, иногда str
            if isinstance(chunk, dict):
                # possible streaming chunk shape
                text = chunk.get("choices") or chunk.get("text") or chunk.get("message") or chunk.get("delta")
                if isinstance(text, (list, tuple)):
                    # try to extract
                    try:
                        parts.append(text[0].get("text",""))
                    except Exception:
                        parts.append(str(text))
                else:
                    parts.append(str(text))
            else:
                parts.append(str(chunk))
        joined = "".join(parts).strip()
        if joined:
            return joined
    except Exception:
        pass
    # fallback
    return str(resp)

# Создаём клиента g4f (если есть)
g4f_client = None
if HAVE_CLIENT and G4FClient is not None:
    try:
        g4f_client = G4FClient()
    except Exception:
        g4f_client = None

# Команда /start
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я ИИ-бот на g4f — напиши что-нибудь.")

# Основной обработчик сообщений
async def ai_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    # Соберём сообщения в формате chat-completions
    messages = [
        {"role": "system", "content": G4F_SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]

    try:
        # 1) Если есть новый клиент — используем его
        if g4f_client is not None:
            # В client API: client.chat.completions.create(...)
            # Не все провайдеры требуют model; если поддерживается — можно передать model arg
            kwargs = {"messages": messages}
            if G4F_PROVIDER:
                kwargs["provider"] = G4F_PROVIDER
            resp = g4f_client.chat.completions.create(**kwargs)
            answer = normalize_g4f_response(resp)

        # 2) Фоллбек: старый интерфейс g4f.ChatCompletion.create
        else:
            # Импортируем внутри блока, если надо (в некоторых окружениях import ранний проваливался)
            import g4f
            # не указываем модель, чтобы избежать "Model not found"
            # можно указать provider через env переменную, если библиотека поддерживает
            call_kwargs = {"messages": messages, "stream": False}
            if G4F_PROVIDER:
                call_kwargs["model"] = G4F_PROVIDER  # иногда библиотека ожидает model для выбора источника
            resp = g4f.ChatCompletion.create(**call_kwargs)
            answer = normalize_g4f_response(resp)

    except Exception as e:
        # Отлавливаем ошибку и отправляем пользователю понятное сообщение
        answer = f"Ошибка при генерации ответа: {e}"

    # Ограничим длину ответа (Telegram имеет лимит, и длинные ответы лучше резать)
    MAX_LEN = 4000
    if len(answer) > MAX_LEN:
        answer = answer[:MAX_LEN-200] + "\n\n... (ответ усечён)"

    await update.message.reply_text(answer)

# Создаём приложение и регистрируем обработчики
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))
    # Запускаем polling (подходит для Pydroid)
    app.run_polling()

# Если файл запускается напрямую (например через exec), стартуем
if __name__ == "__main__":
    main()
