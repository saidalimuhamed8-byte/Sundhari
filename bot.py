import os
import asyncio
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler

# ------------------------
# Logging setup
# ------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------
# Environment variables
# ------------------------
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if not TOKEN or not WEBHOOK_URL:
    raise ValueError("Please set BOT_TOKEN and WEBHOOK_URL environment variables!")

# ------------------------
# Telegram bot application
# ------------------------
app_bot = Application.builder().token(TOKEN).build()

# Command handler
async def start(update: Update, context):
    await update.message.reply_text("Hello! Bot is running ✅")

app_bot.add_handler(CommandHandler("start", start))

# ------------------------
# Queue for incoming updates
# ------------------------
update_queue = asyncio.Queue()

# Process updates with flood control handling
async def process_updates():
    while True:
        update = await update_queue.get()
        retry_attempts = 0
        max_retries = 5
        wait_time = 1  # initial backoff in seconds

        while retry_attempts < max_retries:
            try:
                await app_bot.process_update(update)
                break  # Success
            except RetryAfter as e:
                # Telegram flood control triggered, apply exponential backoff
                wait_time = e.retry_after * (2 ** retry_attempts)
                logger.warning(f"Flood control exceeded. Retry in {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                retry_attempts += 1
            except Exception as e:
                logger.error(f"Error processing update: {e}")
                break  # Don't retry other errors
        update_queue.task_done()

# ------------------------
# FastAPI app with lifespan
# ------------------------
async def lifespan(app: FastAPI):
    # Startup: set webhook and start processing updates
    await app_bot.bot.set_webhook(WEBHOOK_URL)
    logger.info("Bot started and webhook set ✅")
    task = asyncio.create_task(process_updates())
    yield
    # Shutdown: cancel task and delete webhook
    task.cancel()
    await app_bot.bot.delete_webhook()
    logger.info("Webhook deleted and bot stopped ❌")

app = FastAPI(lifespan=lifespan)

# ------------------------
# Telegram webhook endpoint
# ------------------------
@app.post("/")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, app_bot.bot)
    await update_queue.put(update)
    return {"ok": True}
