# bot_logic.py
import os
import asyncio
from functools import partial
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Попытаемся импортировать современный клиент g4f; если нет — падём обратно на старый интерфейс
try:
    from g4f.client import Client as G4FClient
    HAVE_CLIENT = True
except Exception:
    import g4f  # старый интерфейс
    G4FClient = None
    HAVE_CLIENT = False

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан в переменных окружения")

# Необязательные переменные
G4F_PROVIDER = os.getenv("G4F_PROVIDER")  # например "bing" или другой провайдер, если нужно
G4F_SYSTEM_PROMPT = os.getenv("G4F_SYSTEM_PROMPT", "Ты помощник, отвечай кратко и по делу.")

# Нормализатор ответов из разных форматов g4f
def normalize_g4f_response(resp):
    if resp is None:
        return ""
    # Если объект имеет метод result() — извлекаем
    try:
        if hasattr(resp, "result") and callable(resp.result):
            try:
                out = resp.result()
                return normalize_g4f_response(out)
            except Exception:
                pass
    except Exception:
        pass

    # Строка
    if isinstance(resp, str):
        return resp.strip()

    # Словарь с choices / text / message
    if isinstance(resp, dict):
        # OpenAI-like
        try:
            return resp["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        if "text" in resp and isinstance(resp["text"], str):
            return resp["text"].strip()
        # Соберём все строковые поля
        parts = []
        for v in resp.values():
            if isinstance(v, str):
                parts.append(v)
        if parts:
            return " ".join(parts).strip()
        return str(resp)

    # Итерируемый (поток)
    try:
        pieces = []
        for chunk in resp:
            if chunk is None:
                continue
            if isinstance(chunk, str):
                pieces.append(chunk)
                continue
            if isinstance(chunk, dict):
                # попытка найти текстовые поля
                if "text" in chunk:
                    pieces.append(str(chunk["text"]))
                elif "message" in chunk:
                    # openai style chunk
                    try:
                        pieces.append(chunk["message"]["content"])
                    except Exception:
                        pieces.append(str(chunk["message"]))
                else:
                    pieces.append(str(chunk))
            else:
                pieces.append(str(chunk))
        if pieces:
            return "".join(pieces).strip()
    except Exception:
        pass

    # fallback
    try:
        return str(resp)
    except Exception:
        return ""

# Инициализация клиента (если доступен)
g4f_client = None
if HAVE_CLIENT and G4FClient is not None:
    try:
        g4f_client = G4FClient()
    except Exception:
        g4f_client = None

# Функция, выполняющая блокирующий вызов к g4f (sync) — будет вызвана в executor
def _sync_get_answer_with_new_client(messages, provider=None):
    # используется, если есть g4f client
    kwargs = {"messages": messages}
    if provider:
        # разные реализации могут ожидать provider или model; пробуем provider
        kwargs["provider"] = provider
    resp = g4f_client.chat.completions.create(**kwargs)
    return resp

def _sync_get_answer_with_old_interface(messages, provider=None):
    import g4f as _g4f
    call_kwargs = {"messages": messages, "stream": False}
    # В старых версиях иногда ожидается model; пробуем подставить provider в model, если задан
    if provider:
        call_kwargs["model"] = provider
    resp = _g4f.ChatCompletion.create(**call_kwargs)
    return resp

# Асинхронная обёртка: вызывает подходящий sync-функционал в executor и нормализует ответ
async def get_g4f_answer(messages):
    loop = asyncio.get_running_loop()
    try:
        if g4f_client is not None:
            resp = await loop.run_in_executor(None, partial(_sync_get_answer_with_new_client, messages, G4F_PROVIDER))
            text = normalize_g4f_response(resp)
            if text:
                return text
        # фоллбек на старый интерфейс
        resp = await loop.run_in_executor(None, partial(_sync_get_answer_with_old_interface, messages, G4F_PROVIDER))
        text = normalize_g4f_response(resp)
        return text
    except Exception as e:
        return f"Ошибка при генерации ответа: {e}"

# Обработчики для Telegram
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я ИИ-бот на g4f — напиши что-нибудь.")

async def ai_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    messages = [
        {"role": "system", "content": G4F_SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]

    answer = await get_g4f_answer(messages)

    # Ограничиваем длину ответа, чтобы не превысить лимит Telegram
    MAX_LEN = 4000
    if len(answer) > MAX_LEN:
        answer = answer[:MAX_LEN - 200] + "\n\n... (ответ усечён)"

    await update.message.reply_text(answer)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai
