import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler

TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # e.g. https://naughty-suzette-sasis-fdd9317b.koyeb.app

app = Flask(__name__)

# Create bot application
application = Application.builder().token(TOKEN).build()

# --- Handlers ---
async def start(update: Update, context):
    await update.message.reply_text("Hello! Bot is running on webhook 🚀")

application.add_handler(CommandHandler("start", start))

# --- Flask Routes ---
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is alive ✅", 200

# --- Startup: Set Webhook ---
async def set_webhook():
    webhook_url = f"{APP_URL}/{TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to {webhook_url}")

if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(set_webhook())
    app.run(host="0.0.0.0", port=8000)
