# bot.py
import os
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler

# ----------------------------
# Environment variables
# ----------------------------
TOKEN = os.environ.get("BOT_TOKEN")  # Set this in Koyeb
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # https://<your-app>.koyeb.app/

# ----------------------------
# Create FastAPI app
# ----------------------------
app = FastAPI()

# ----------------------------
# Create Telegram Bot Application
# ----------------------------
app_bot = Application.builder().token(TOKEN).build()


# ----------------------------
# Example command
# ----------------------------
async def start(update: Update, context):
    await update.message.reply_text("Hello! Bot is running on Koyeb ✅")


app_bot.add_handler(CommandHandler("start", start))


# ----------------------------
# Webhook endpoint
# ----------------------------
@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, app_bot.bot)
    await app_bot.update_queue.put(update)
    return {"status": "ok"}


# ----------------------------
# Startup event
# ----------------------------
@app.on_event("startup")
async def startup_event():
    # Initialize bot
    await app_bot.initialize()
    # Set webhook
    await app_bot.bot.set_webhook(WEBHOOK_URL)


# ----------------------------
# Shutdown event
# ----------------------------
@app.on_event("shutdown")
async def shutdown_event():
    # Delete webhook
    await app_bot.bot.delete_webhook()
    await app_bot.stop()
