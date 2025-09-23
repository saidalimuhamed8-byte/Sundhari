import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Environment Variables ---
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL not set in environment variables")

# --- Video links ---
VIDEOS = {
    "mallu": [
        "https://example.com/videos/mallu1.mp4",
        "https://example.com/videos/mallu2.mp4"
    ],
    "latest": [
        "https://example.com/videos/latest1.mp4",
        "https://example.com/videos/latest2.mp4"
    ],
    "desi": [
        "https://example.com/videos/desi1.mp4"
    ],
    "trending": [
        "https://example.com/videos/trending1.mp4"
    ]
}

PAGE_SIZE = 1

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and a menu of video categories."""
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
        "👋 Welcome to സുന്ദരി 🔞 bot! Choose a category:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button presses and sends the corresponding videos."""
    query = update.callback_query
    await query.answer()

    # Extract category and page from the callback data
    try:
        category, page_str = query.data.split(":")
        page = int(page_str)
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Invalid button data.")
        return

    videos = VIDEOS.get(category, [])

    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        try:
            await query.edit_message_text("❌ No more videos in this category.")
        except Exception as e:
            print(f"Failed to edit message: {e}")
        return

    media = [InputMediaVideo(url) for url in batch]

    # Use a new reply_text message for the videos
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    # Navigation buttons
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    try:
        if buttons:
            nav_markup = InlineKeyboardMarkup([buttons])
            await query.message.reply_text("Navigate:", reply_markup=nav_markup)
        else:
            await query.message.reply_text("End of videos.")
    except Exception as e:
        print(f"Failed to send navigation buttons: {e}")

# --- Telegram Bot Application ---
def main():
    """Initializes and runs the bot using a webhook."""
    # Ensure URL and PORT are correctly set in the environment
    webhook_url_path = TOKEN
    
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_handler))

    # Set up the webhook
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_url_path,
        webhook_url=f"{WEBHOOK_URL}/{webhook_url_path}"
    )

if __name__ == "__main__":
    main()
