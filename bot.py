import os
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask

TOKEN = '8224276236:AAFqXBAGkD7jTv5f7Y-kiUztO82jo0W3mB0'
VIDEO_DIR = "./videos"

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Send the name of the video you want and I'll send it to you.")

async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    video_path = os.path.join(VIDEO_DIR, query)
    if not os.path.exists(video_path):
        for ext in (".mp4", ".mov", ".avi", ".mkv"):
            if os.path.exists(video_path + ext):
                video_path = video_path + ext
                break
    if os.path.exists(video_path):
        await update.message.reply_video(video=open(video_path, "rb"))
    else:
        await update.message.reply_text("❌ Sorry, video not found. Please check the name and try again.")

def run_flask():
    flask_app = Flask(__name__)

    @flask_app.route('/health')
    def health():
        return "OK", 200

    flask_app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()
    # Run Telegram bot in main thread (NO threading)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_video))
    app.run_polling()
