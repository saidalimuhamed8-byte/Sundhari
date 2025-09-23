# This script is a modified version of the Telegram bot that uses a webhook
# instead of long polling. This is required for deployment environments
# that rely on a public port and health checks.

import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Environment Variables ---
# The bot token is retrieved from environment variables for security.
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

# Webhook URL and port are required for a webhook setup.
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL not set in environment variables")

PORT = int(os.environ.get("PORT", "8080"))

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
    """Sends a message with inline keyboard to choose a category."""
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
    """Handles button presses and sends the appropriate video batch."""
    query = update.callback_query
    await query.answer()

    category, page = query.data.split(":")
    page = int(page)
    videos = VIDEOS.get(category, [])

    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.edit_message_text("❌ No more videos.")
        return

    media = [InputMediaVideo(url) for url in batch]

    if media:
        try:
            await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Failed to send videos: {e}")

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        try:
            await query.edit_message_text("Navigate:", reply_markup=nav_markup)
        except Exception:
            # Handle the case where the message can't be edited.
            pass

# --- Telegram Bot Application ---
def main():
    """Initializes and runs the Telegram bot using a webhook."""
    # Enable logging for debugging.
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )

    bot_app = ApplicationBuilder().token(TOKEN).build()

    # Add handlers to the application.
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_handler))

    # Run the webhook on the specified port.
    # The webhook URL is set via environment variables.
    bot_app.run_webhook(listen="0.0.0.0",
                        port=PORT,
                        url_path=TOKEN,
                        webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    main()
