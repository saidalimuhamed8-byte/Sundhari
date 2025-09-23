import os
import asyncio
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if not TOKEN or not WEBHOOK_URL:
    raise ValueError("Set BOT_TOKEN and WEBHOOK_URL environment variables!")

# Create bot application
app_bot = Application.builder().token(TOKEN).build()

# Example command
async def start(update: Update, context):
    await update.message.reply_text("Hello! Bot is running ✅")

app_bot.add_handler(CommandHandler("start", start))

# Async queue to prevent flood control
update_queue = asyncio.Queue()

async def process_updates():
    while True:
        update = await update_queue.get()
        try:
            await app_bot.process_update(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
        update_queue.task_done()

# FastAPI app
app = FastAPI()

# Telegram webhook endpoint
@app.post("/")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, app_bot.bot)
    await update_queue.put(update)  # Add update to queue
    return {"ok": True}

# Startup event
@app.on_event("startup")
async def startup():
    # Set webhook
    await app_bot.bot.set_webhook(WEBHOOK_URL)
    logger.info("Bot started and webhook set ✅")
    # Start queue processor
    asyncio.create_task(process_updates())

# Shutdown event
@app.on_event("shutdown")
async def shutdown():
    await app_bot.bot.delete_webhook()
    logger.info("Webhook deleted and bot stopped ❌")
