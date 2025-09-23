import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Define videos for each button ---
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

# --- /start handler ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Mallu 🎥", callback_data="mallu"),
            InlineKeyboardButton("Latest 🔥", callback_data="latest"),
        ],
        [
            InlineKeyboardButton("Desi 🇮🇳", callback_data="desi"),
            InlineKeyboardButton("Trending 📈", callback_data="trending"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to സുന്ദരി 🔞 bot!\n\nChoose a category below:",
        reply_markup=reply_markup
    )

# --- Button press handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category = query.data
    videos = VIDEOS.get(category, [])

    if videos:
        await query.message.reply_text(f"📂 Sending {category.title()} videos...")
        for video_url in videos:
            await context.bot.send_video(chat_id=query.message.chat_id, video=video_url)
    else:
        await query.message.reply_text("❌ No videos available for this category.")

# --- Main ---
def main():
    bot_token = os.getenv("BOT_TOKEN")  # set BOT_TOKEN in your Koyeb env
    application = Application.builder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()

if __name__ == "__main__":
    main()
