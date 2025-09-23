import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

VIDEOS = {
    "mallu": ["videos/mallu1.mp4", "videos/mallu2.mp4"],
    "latest": ["videos/latest1.mp4", "videos/latest2.mp4"],
    "desi": ["videos/desi1.mp4"],
    "trending": ["videos/trending1.mp4"]
}

PAGE_SIZE = 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
         InlineKeyboardButton("🆕 Latest", callback_data="latest:0")],
        [InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
         InlineKeyboardButton("🔥 Trending", callback_data="trending:0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome! Choose a category:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category, page = query.data.split(":")
    page = int(page)
    videos = VIDEOS.get(category, [])

    if not videos:
        await query.edit_message_text("❌ No videos in this category.")
        return

    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    batch = videos[start_idx:end_idx]

    media = [InputMediaVideo(video) for video in batch]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    # Navigation
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text("Navigate:", reply_markup=nav_markup)

def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set in environment variables")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
