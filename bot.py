import os
import asyncio
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler
from contextlib import asynccontextmanager

# Environment variables
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g., https://<your-app>.koyeb.app/webhook

if not TOKEN:
    raise ValueError("BOT_TOKEN must be set!")

# Telegram bot application
app_bot = Application.builder().token(TOKEN).build()

# Example command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is running ✅")

app_bot.add_handler(CommandHandler("start", start))

# Lifespan context for FastAPI startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start bot safely on app startup
    try:
        await app_bot.initialize()
        await app_bot.start()
        await app_bot.bot.set_webhook(WEBHOOK_URL)
        print("Bot started and webhook set ✅")
    except Exception as e:
        print(f"Error starting bot: {e}")

    try:
        yield
    finally:
        # Shutdown bot safely on app shutdown
        try:
            await app_bot.bot.delete_webhook()
            await app_bot.stop()
            await app_bot.shutdown()
            print("Bot stopped ✅")
        except Exception as e:
            print(f"Error stopping bot: {e}")

# FastAPI app
app = FastAPI(lifespan=lifespan)

# Telegram webhook endpoint
@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, await app_bot.bot.get_bot())
    await app_bot.update_queue.put(update)
    return Response(status_code=200)

# Simple health check
@app.get("/")
async def root():
    return {"status": "Bot is running ✅"}

# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
