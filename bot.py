from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Example video paths
VIDEOS = {
    "mallu": ["videos/mallu1.mp4", "videos/mallu2.mp4", "videos/mallu3.mp4", "..."], 
    "latest": ["videos/latest1.mp4", "videos/latest2.mp4", "..."],
    "desi": ["videos/desi1.mp4", "..."],
    "trending": ["videos/trending1.mp4", "..."]
}

PAGE_SIZE = 10  # Videos per album

# --- /start handler ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
            InlineKeyboardButton("🆕 Latest", callback_data="latest:0")
        ],
        [
            InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
            InlineKeyboardButton("🔥 Trending", callback_data="trending:0")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome to സുന്ദരി 🔞 bot! Choose a category to see videos:",
        reply_markup=reply_markup
    )

# --- Button handler with pagination ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Extract category and page number
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

    # Send videos as media group
    from telegram import InputMediaVideo
    media = [InputMediaVideo(video) for video in batch]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    # Navigation buttons
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        await query.message.reply_text("Navigate:", reply_markup=nav_markup)

# --- Main ---
def main():
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
