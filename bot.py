import os
import json
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # set this in Koyeb as your own Telegram user ID

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

app = Flask(__name__)

# Track users & groups
users = set()
groups = set()

# Telegram Application
application = Application.builder().token(BOT_TOKEN).build()

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        users.add(chat.id)
    elif chat.type in ["group", "supergroup"]:
        groups.add(chat.id)

    await update.message.reply_text("Welcome to സുന്ദരി 🔞 bot")

# /log command (admin only)
async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    msg = (
        f"📊 Bot Statistics:\n\n"
        f"👤 Users: {len(users)}\n"
        f"👥 Groups: {len(groups)}\n\n"
        f"Users: {list(users)}\n"
        f"Groups: {list(groups)}"
    )
    await update.message.reply_text(msg)

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("log", log))

# Webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
