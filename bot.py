import os
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

# Flask app for Koyeb
flask_app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# -------- VIDEO LISTS --------
VIDEOS = {
    "mallu": [
        "https://example.com/mallu1.mp4",
        "https://example.com/mallu2.mp4"
    ],
    "latest": [
        "https://example.com/latest1.mp4",
        "https://example.com/latest2.mp4"
    ],
    "desi": [
        "https://example.com/desi1.mp4",
        "https://example.com/desi2.mp4"
    ],
    "trending": [
        "https://example.com/trending1.mp4",
        "https://example.com/trending2.mp4"
    ]
}

# -------- HANDLERS --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Mallu", callback_data="mallu"),
            InlineKeyboardButton("Latest", callback_data="latest"),
        ],
        [
            InlineKeyboardButton("Desi", callback_data="desi"),
            InlineKeyboardButton("Trending", callback_data="trending"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to സുന്ദരി 🔞 bot\nChoose a category:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category = query.data
    if category in VIDEOS:
        await query.message.reply_text(f"📹 Sending {category.capitalize()} videos...")

        for video in VIDEOS[category]:
            try:
                await query.message.reply_video(video)
            except Exception as e:
                await query.message.reply_text(f"⚠️ Could not send video: {e}")

# -------- ROUTES FOR KOYEB --------
@flask_app.route("/")
def index():
    return "Bot is running!"

@flask_app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

async def set_webhook():
    webhook_url = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.koyeb.app
    await application.bot.set_webhook(f"{webhook_url}/{TOKEN}")

# -------- MAIN --------
def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    flask_app.before_first_request_funcs.append(lambda: application.create_task(set_webhook()))

if __name__ == "__main__":
    main()
    flask_app.run(host="0.0.0.0", port=8000)

