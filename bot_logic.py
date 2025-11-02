import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

try:
    import g4f
except Exception as e:
    raise RuntimeError("Нужна библиотека g4f. Установи: pip install g4f") from e

TOKEN = os.getenv("TELEGRAM_TOKEN") or "ВАШ_ТОКЕН"
MODEL = os.getenv("G4F_MODEL") or "gpt4free"  # <- укажи поддерживаемую модель

SYSTEM_PROMPT = os.getenv("G4F_SYSTEM_PROMPT", "Ты помощник, отвечай кратко и по делу.")
MAX_REPLY_LEN = 4000

def normalize_response(resp):
    try:
        if isinstance(resp, str):
            return resp.strip()
        if isinstance(resp, dict):
            if "text" in resp:
                return resp["text"].strip()
            return str(resp)
        try:
            return "".join([str(x) for x in resp])
        except Exception:
            return str(resp)
    except Exception:
        return str(resp)

async def generate_answer(messages):
    loop = asyncio.get_running_loop()
    def _sync_call():
        return g4f.ChatCompletion.create(model=MODEL, messages=messages, stream=False)
    try:
        resp = await loop.run_in_executor(None, _sync_call)
        return normalize_response(resp)
    except Exception as e:
        return f"Ошибка при генерации ответа: {e}"

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я ИИ-бот на g4f. Напиши что-нибудь.")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]
    answer = await generate_answer(messages)
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
