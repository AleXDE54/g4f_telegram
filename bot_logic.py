import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import json
import os
from g4f.client import Client

# Настройка логирования ошибок в файл
logging.basicConfig(
    filename='bot_errors.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)
logger = logging.getLogger(__name__)

# Глобальная переменная для режима onetime
ONETIME_MODE = False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ответ на команду /start."""
    await update.message.reply_text("g4f_telegram AIbot. Running latest version. Enter your question...")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка истории пользователя."""
    user_id = update.effective_user.id
    if ONETIME_MODE:
        context.user_data['history'] = []
    else:
        filename = f'history_{user_id}.json'
        if os.path.exists(filename):
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    await update.message.reply_text("История переписки очищена.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать краткую сводку последних сообщений."""
    user_id = update.effective_user.id
    if ONETIME_MODE:
        history = context.user_data.get('history', [])
    else:
        filename = f'history_{user_id}.json'
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []
    if not history:
        await update.message.reply_text("History is empty.")
        return
    # Формируем последние сообщения
    lines = []
    last_entries = history[-6:]
    for entry in last_entries:
        role = entry['role']
        content = entry['content']
        if len(content) > 100:
            content = content[:97] + "..."
        if role == 'user':
            lines.append(f"Пользователь: {content}")
        else:
            lines.append(f"Бот: {content}")
    text = "Last messages:\n" + "\n".join(lines)
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка входящих текстовых сообщений."""
    user_id = update.effective_user.id
    user_text = update.message.text
    # Загрузка или инициализация истории
    if ONETIME_MODE:
        history = context.user_data.get('history', [])
    else:
        filename = f'history_{user_id}.json'
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []
    # Добавляем сообщение пользователя в историю
    history.append({"role": "user", "content": user_text})
    # Определяем модель (по умолчанию gpt-3.5-turbo)
    model = context.user_data.get('model', 'gpt-3.5-turbo')
    client = Client()
    try:
        # Запрос к g4f (GPT)
        chat_completion = client.chat.completions.create(
            model=model,
            messages=history,
            stream=False
        )
        if isinstance(chat_completion, dict):
            answer = chat_completion['choices'][0]['message']['content']
        else:
            # В данном примере поток не используется, но можно собрать содержимое:
            answer = ""
            for token in chat_completion:
                part = token.choices[0].delta.content
                if part:
                    answer += part
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Error.")
        return
    # Добавляем ответ бота в историю
    history.append({"role": "assistant", "content": answer})
    # Сохраняем историю
    if ONETIME_MODE:
        context.user_data['history'] = history
    else:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    # Готовим inline-кнопки (модель и регенерация)
    buttons = [
        [
            InlineKeyboardButton("gpt-3.5-turbo", callback_data="model_gpt-3.5-turbo"),
            InlineKeyboardButton("gpt-4o", callback_data="model_gpt-4o"),
        ],
        [InlineKeyboardButton("Перегенерировать", callback_data="regenerate")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    # Отправляем ответ вместе с клавиатурой
    await update.message.reply_text(answer, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий на inline-кнопки."""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()  # подтв. нажатия
    # Переключение модели
    if data.startswith("model_"):
        new_model = data.split("model_")[1]
        context.user_data['model'] = new_model
        await query.answer(f"Model was changed to {new_model}")
        return
    # Перегенерация ответа
    if data == "regenerate":
        if ONETIME_MODE:
            history = context.user_data.get('history', [])
        else:
            filename = f'history_{user_id}.json'
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = []
        # Удаляем последний ответ бота
        if history and history[-1]['role'] == 'assistant':
            history.pop()
        if not history or history[-1]['role'] != 'user':
            await query.message.reply_text("No query for regeneration.")
            return
        # Новый запрос к ИИ с той же историей (без последнего ответа)
        model = context.user_data.get('model', 'gpt-3.5-turbo')
        client = Client()
        try:
            chat_completion = client.chat.completions.create(
                model=model,
                messages=history,
                stream=False
            )
            if isinstance(chat_completion, dict):
                new_answer = chat_completion['choices'][0]['message']['content']
            else:
                new_answer = ""
                for token in chat_completion:
                    part = token.choices[0].delta.content
                    if part:
                        new_answer += part
        except Exception as e:
            logger.error(f"Error with regeneration: {e}")
            await query.message.reply_text("Error.")
            return
        history.append({"role": "assistant", "content": new_answer})
        # Сохраняем историю после регена
        if ONETIME_MODE:
            context.user_data['history'] = history
        else:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        # Обновляем текст сообщения бота
        buttons = [
            [
                InlineKeyboardButton("gpt-3.5-turbo", callback_data="model_gpt-3.5-turbo"),
                InlineKeyboardButton("gpt-4o", callback_data="model_gpt-4o"),
            ],
            [InlineKeyboardButton("Перегенерировать", callback_data="regenerate")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(new_answer, reply_markup=reply_markup)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логгирование непойманных исключений."""
    logger.error(f"Update {update} made an error: {context.error}")

def main():
    global ONETIME_MODE
    mode = input("Do you want to use a onetime mode? (Y/N): ")
    if mode.strip().lower() == 'y':
        ONETIME_MODE = True
    else:
        ONETIME_MODE = False
    # Замените строку ниже на токен вашего бота
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    app = Application.builder().token(TOKEN).build()
    # Регистрируем обработчики команд и сообщений
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    # Запуск бота
    app.run_polling()

if __name__ == '__main__':
    main()
