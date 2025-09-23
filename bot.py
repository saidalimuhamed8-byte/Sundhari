import os
from flask import Flask, request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "YOUR_BOT_TOKEN_HERE"
WEBHOOK_URL = "https://<your-app-name>.koyeb.app/"  # Replace with your Koyeb app URL

VIDEOS = {
    "mallu": ["videos/mallu1.mp4", "videos/mallu2.mp4", "..."],
    "latest": ["videos/latest1.mp4", "videos/latest2.mp4", "..."],
    "desi": ["videos/desi1.mp4", "..."],
    "trending": ["videos/trending1.mp4", "..."]
}
PAGE_SIZE = 10

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
         InlineKeyboardButton("🆕 Latest", callback_data="latest:0")],
        [InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
         InlineKeyboardButton("🔥 Trending", callback_data="trending:0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome to സുന്ദരി 🔞 bot! Choose a category to see videos:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    category = data[0]
    page = int(data[1]) if len(data) > 1 else 0

    videos = VIDEOS.get(category, [])
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    batch = videos[start:end]

    if not batch:
        await query.message.reply_text("❌ No videos available.")
        return

    media = [InputMediaVideo(video) for video in batch]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        await query.message.reply_text("Navigate:", reply_markup=nav_markup)

# --- Flask App ---
flask_app = Flask(__name__)
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))

@flask_app.route('/health')
def health():
    return "OK", 200

@flask_app.route('/', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.create_task(app.update_queue.put(update))
    return "OK", 200

if __name__ == "__main__":
    # Set the webhook before running Flask
    import asyncio
    async def set_webhook():
        await app.bot.set_webhook(WEBHOOK_URL)
    asyncio.run(set_webhook())

    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
