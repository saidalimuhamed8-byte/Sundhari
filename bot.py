import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# --- Environment Variables ---
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g., https://yourdomain.com
PORT = int(os.environ.get("PORT", 8000))

# --- Database Setup ---
conn = sqlite3.connect("sundhari.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT
)
""")
conn.commit()

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES(?, ?)", (user.id, user.username))
    conn.commit()
    await update.message.reply_text("👋 Hello! Welcome to Sundhari Bot.")

async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Send the video file ID after /addvideo command.")
        return
    file_id = context.args[0]
    cursor.execute("INSERT INTO videos(file_id) VALUES(?)", (file_id,))
    conn.commit()
    await update.message.reply_text("✅ Video added successfully!")

async def bulk_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Send multiple video file IDs separated by space.")
        return
    for file_id in context.args:
        cursor.execute("INSERT INTO videos(file_id) VALUES(?)", (file_id,))
    conn.commit()
    await update.message.reply_text("✅ Bulk videos added successfully!")

async def remove_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Send the video ID to remove.")
        return
    video_id = context.args[0]
    cursor.execute("DELETE FROM videos WHERE id=?", (video_id,))
    conn.commit()
    await update.message.reply_text("✅ Video removed successfully!")

async def list_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, file_id FROM videos")
    videos = cursor.fetchall()
    if not videos:
        await update.message.reply_text("No videos added yet.")
        return
    msg = "\n".join([f"ID: {vid[0]}, FileID: {vid[1]}" for vid in videos])
    await update.message.reply_text(msg)

# --- Main Function ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addvideo", add_video))
    app.add_handler(CommandHandler("bulkadd", bulk_add))
    app.add_handler(CommandHandler("removevideo", remove_video))
    app.add_handler(CommandHandler("listvideos", list_videos))

    # Run webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()

