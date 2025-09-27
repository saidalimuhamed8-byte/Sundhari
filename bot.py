import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
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
APP_URL = os.environ["APP_URL"]  # Your Koyeb public URL
PORT = int(os.environ.get("PORT", 8000))

# --- Database Setup ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT UNIQUE
    )
""")
conn.commit()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    conn.commit()
    await update.message.reply_text("Hello! Bot is running on Koyeb.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /bulkadd or /remvideo to manage videos.")

# Bulk add videos (admin only)
async def bulk_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = int(os.environ.get("ADMIN_ID", 0))
    if update.effective_user.id != admin_id:
        await update.message.reply_text("You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /bulkadd <file_id1> <file_id2> ...")
        return

    for file_id in context.args:
        cursor.execute("INSERT OR IGNORE INTO videos(file_id) VALUES(?)", (file_id,))
    conn.commit()
    await update.message.reply_text(f"Added {len(context.args)} videos.")

# Remove video (admin only)
async def remove_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = int(os.environ.get("ADMIN_ID", 0))
    if update.effective_user.id != admin_id:
        await update.message.reply_text("You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /remvideo <file_id1> <file_id2> ...")
        return

    removed_count = 0
    for file_id in context.args:
        cursor.execute("DELETE FROM videos WHERE file_id=?", (file_id,))
        removed_count += cursor.rowcount
    conn.commit()
    await update.message.reply_text(f"Removed {removed_count} videos.")

# Send all videos to user
async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT file_id FROM videos")
    videos = cursor.fetchall()
    if not videos:
        await update.message.reply_text("No videos available.")
        return

    media_group = [InputMediaVideo(media=v[0]) for v in videos]
    await update.message.reply_media_group(media_group)

# --- Callback Query Example ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Selected option: {query.data}")

# --- Main ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bulkadd", bulk_add))
    app.add_handler(CommandHandler("remvideo", remove_video))
    app.add_handler(CommandHandler("videos", send_videos))

    # Callback handler
    app.add_handler(CallbackQueryHandler(button_handler))

    # Run webhook on Koyeb
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="",           # No token in path
        webhook_url=APP_URL,   # Public URL
    )

if __name__ == "__main__":
    main()
