import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- Config ---
TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = os.environ.get("APP_URL")  # Must be set in Koyeb -> https://your-app-name.koyeb.app
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN or not APP_URL:
    raise RuntimeError("BOT_TOKEN or APP_URL is missing! Set them in Koyeb environment variables.")

WEBHOOK_URL = f"{APP_URL}/{TOKEN}"


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Yes, I am 18+", callback_data="age_yes"),
            InlineKeyboardButton("No, I am under 18", callback_data="age_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Are you 18+?", reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "age_yes":
        await query.edit_message_text("✅ Access granted. Welcome!")
    elif query.data == "age_no":
        await query.edit_message_text("❌ Sorry, you must be 18+ to use this bot.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Bot is running on Koyeb and webhook is active!")


# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button))

    # Run with webhook (Koyeb)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL,
    )


if __name__ == "__main__":
    main()
