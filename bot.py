import os
import asyncio
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler

# ---------------------------
# Configuration
# ---------------------------
TOKEN = os.environ.get("BOT_TOKEN")  # Set your bot token in environment
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Set your full webhook URL in environment

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------
# Create Telegram Bot Application
# ---------------------------
app_bot = Application.builder().token(TOKEN).build()

# ---------------------------
# Example Command Handler
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is running.")

app_bot.add_handler(CommandHandler("start", start))

# ---------------------------
# Queue to process updates
# ---------------------------
update_queue = asyncio.Queue()

# Background processor to handle updates
async def process_updates():
    while True:
        update = await update_queue.get()
        try:
            await app_bot.update_queue.put(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")

# ---------------------------
# FastAPI app
# ---------------------------
app = FastAPI()

# Lifespan function keeps the bot running
@app.on_event("startup")
async def startup():
    logger.info("Starting bot...")
    # Set webhook
    await app_bot.bot.set_webhook(WEBHOOK_URL)
    # Start the background update processor
    app.state.task = asyncio.create_task(process_updates())
    logger.info("Bot started and webhook set ✅")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down bot...")
    app.state.task.cancel()
    await app_bot.bot.delete_webhook()
    logger.info("Webhook deleted and bot stopped ❌")

# ---------------------------
# Webhook route
# ---------------------------
@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, app_bot.bot)
    await update_queue.put(update)
    return {"ok": True}

# ---------------------------
# Run the bot manually if needed
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8000)
