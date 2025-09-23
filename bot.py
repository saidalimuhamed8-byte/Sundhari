from flask import Flask, request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # your Koyeb app URL

flask_app = Flask(__name__)

application = Application.builder().token(BOT_TOKEN).build()

# --- Bot handlers ---
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Mallu", callback_data="mallu")],
        [InlineKeyboardButton("Latest", callback_data="latest")],
        [InlineKeyboardButton("Desi", callback_data="desi")],
        [InlineKeyboardButton("Trending", callback_data="trending")],
    ]
    await update.message.reply_text(
        "🎉 Welcome to സുന്ദരി 🔞 bot!\nChoose a category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def handle_category(update: Update, context):
    query = update.callback_query
    await query.answer()

    videos = {
        "mallu": [
            "https://example.com/mallu1.mp4",
            "https://example.com/mallu2.mp4",
        ],
        "latest": [
            "https://example.com/latest1.mp4",
            "https://example.com/latest2.mp4",
        ],
        "desi": [
            "https://example.com/desi1.mp4",
            "https://example.com/desi2.mp4",
        ],
        "trending": [
            "https://example.com/trending1.mp4",
            "https://example.com/trending2.mp4",
        ],
    }

    category = query.data
    if category in videos:
        for video in videos[category]:
            await query.message.reply_video(video)

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(handle_category))

# --- Flask webhook route ---
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok", 200

@flask_app.route("/")
def home():
    return "Bot is running!", 200

# --- Startup ---
if __name__ == "__main__":
    # Important: don't use flask_app.before... without completing it
    port = int(os.environ.get("PORT", 8000))
    flask_app.run(host="0.0.0.0", port=port)
