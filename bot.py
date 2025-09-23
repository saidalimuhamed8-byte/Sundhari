import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("TOKEN")  # Set this in Koyeb environment variables
VIDEO_DIR = "./videos"           # Folder containing your videos
PAGE_SIZE = 10                   # Videos per batch

# ---------------- INIT ----------------
app_bot = Application.builder().token(TOKEN).build()
web_app = FastAPI()

# ---------------- /start HANDLER ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Mallu", callback_data="mallu_0")],
        [InlineKeyboardButton("Latest", callback_data="latest_0")],
        [InlineKeyboardButton("Desi", callback_data="desi_0")],
        [InlineKeyboardButton("Trending", callback_data="trending_0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Welcome! Choose a category:", reply_markup=reply_markup)

# ---------------- VIDEO BATCH SENDER ----------------
async def send_video_batch(category, page, update):
    files = sorted([f for f in os.listdir(VIDEO_DIR) if f.startswith(category)])
    start_index = page * PAGE_SIZE
    end_index = start_index + PAGE_SIZE
    batch = files[start_index:end_index]

    if not batch:
        await update.callback_query.message.reply_text("❌ No more videos in this category.")
        return

    for video_file in batch:
        await update.callback_query.message.reply_video(
            video=open(os.path.join(VIDEO_DIR, video_file), "rb")
        )

    # Add "Next" button if more videos exist
    if end_index < len(files):
        keyboard = [[InlineKeyboardButton("Next ➡️", callback_data=f"{category}_{page+1}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.reply_text("Next batch:", reply_markup=reply_markup)

# ---------------- BUTTON HANDLER ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category, page = query.data.split("_")
    page = int(page)
    await send_video_batch(category, page, update)

# ---------------- ADD BOT HANDLERS ----------------
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CallbackQueryHandler(button_handler))

# ---------------- WEBHOOK ENDPOINT ----------------
@web_app.post("/")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, app_bot.bot)
    asyncio.create_task(app_bot.update_queue.put(update))
    return {"ok": True}

# ---------------- HEALTH CHECK ----------------
@web_app.get("/health")
async def health():
    return {"status": "ok"}

# ---------------- START BOT IN BACKGROUND ----------------
async def start_bot():
    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()  # Optional: for dev/testing

asyncio.create_task(start_bot())
