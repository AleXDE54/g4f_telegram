# bot_logic.py
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ВАЖНО: вставь сюда токен или установи TELEGRAM_TOKEN в окружении
TOKEN = os.getenv("TELEGRAM_TOKEN") or "ВАШ_ТЕЛЕГРАМ_ТОКЕН_ЗДЕСЬ"

# Попытка импортировать g4f (старый интерфейс)
try:
    import g4f
except Exception as e:
    raise RuntimeError("Нужна библиотека g4f. Установи: pip install g4f") from e

if not TOKEN or TOKEN == "ВАШ_ТЕЛЕГРАМ_ТОКЕН_ЗДЕСЬ":
    raise RuntimeError("Поставь свой токен в переменную TOKEN или в TELEGRAM_TOKEN в окружении")

# Настройки
SYSTEM_PROMPT = os.getenv("G4F_SYSTEM_PROMPT", "Ты помощник, отвечай кратко и по делу.")
MAX_REPLY_LEN = 4000

def normalize_response(resp):
    """
    Приводим ответ g4f к строке.
    Поддерживаем: str, dict, iterable (поток), либо объекты — пытаемся извлечь текст.
    """
    try:
        if resp is None:
            return ""
        # Если строка — ok
        if isinstance(resp, str):
            return resp.strip()
        # Если словарь с привычными полями
        if isinstance(resp, dict):
            # openai-like
            try:
                return resp["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
            if "text" in resp and isinstance(resp["text"], str):
                return resp["text"].strip()
            # собрать текстовые значения
            parts = [str(v) for v in resp.values() if isinstance(v, (str, int, float))]
            return " ".join(parts).strip() if parts else str(resp)
        # Если итерируемый (stream)
        try:
            pieces = []
            for chunk in resp:
                if chunk is None:
                    continue
                if isinstance(chunk, str):
                    pieces.append(chunk)
                elif isinstance(chunk, dict):
                    if "text" in chunk:
                        pieces.append(str(chunk["text"]))
                    elif "message" in chunk:
                        # streaming chunk like {"message": {"content": "..."}}
                        try:
                            pieces.append(str(chunk["message"]["content"]))
                        except Exception:
                            pieces.append(str(chunk["message"]))
                    else:
                        pieces.append(str(chunk))
                else:
                    pieces.append(str(chunk))
            if pieces:
                return "".join(pieces).strip()
        except TypeError:
            # не итерируемый
            pass
        # fallback
        return str(resp)
    except Exception:
        try:
            return str(resp)
        except Exception:
            return ""

async def generate_answer(messages):
    """
    Вызов g4f в отдельном потоке (чтобы не блокировать asyncio loop).
    Используем старый интерфейс g4f.ChatCompletion.create(...) с stream=False.
    """
    loop = asyncio.get_running_loop()
    def _sync_call():
        # Не указываем model по-умолчанию — так меньше ошибок "Model not found"
        return g4f.ChatCompletion.create(messages=messages, stream=False)
    try:
        resp = await loop.run_in_executor(None, _sync_call)
        return normalize_response(resp)
    except Exception as e:
        return f"Ошибка при генерации ответа: {e}"

# Telegram handlers
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я ИИ-бот на g4f. Напиши что-нибудь.")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]
    # Получаем ответ (await)
    answer = await generate_answer(messages)
    if not answer:
        answer = "Пустой ответ от модели."
    # Ограничим длину
    if len(answer) > MAX_REPLY_LEN:
        answer = answer[:MAX_REPLY_LEN - 200] + "\n\n... (ответ усечён)"
    await update.message.reply_text(answer)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
