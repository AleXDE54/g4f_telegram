import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import g4f  # библиотека для ИИ

# Берем токен из переменной окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Команда /start
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я простой ИИ-бот на g4f!")

# Обработка текстовых сообщений
async def ai_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    try:
        # Получаем ответ от g4f
        answer = g4f.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}],
            stream=False
        )
    except Exception as e:
        answer = f"Ошибка при генерации ответа: {e}"
    
    await update.message.reply_text(answer)

# Создаем приложение бота
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))

# Запуск бота
app.run_polling()
