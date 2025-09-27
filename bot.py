import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Environment Variables ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
APP_URL = os.environ["APP_URL"]  # Your Koyeb URL, e.g., https://mybot.koyeb.app
PORT = int(os.environ.get("PORT", 8000))

# --- Database Setup ---
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE
    )
"""
)
conn.commit()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    conn.commit()
    await update.message.reply_text("Hello! Bot is running on Koyeb.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This is a help message!")

# Example button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Selected option: {query.data}")

# --- Main ---
async def main():
    # Create application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Run webhook (no /TOKEN in URL)
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="",           # No token in webhook path
        webhook_url=APP_URL,   # Full public URL
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
