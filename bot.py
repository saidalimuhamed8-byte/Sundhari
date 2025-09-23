import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- Video links ---
VIDEOS = {
    "mallu": [
        "https://example.com/videos/mallu1.mp4",
        "https://example.com/videos/mallu2.mp4"
    ],
    "latest": [
        "https://example.com/videos/latest1.mp4",
        "https://example.com/videos/latest2.mp4"
    ],
    "desi": [
        "https://example.com/videos/desi1.mp4"
    ],
    "trending": [
        "https://example.com/videos/trending1.mp4"
    ]
}

PAGE_SIZE = 10

TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Your Koyeb HTTPS domain

if not TOKEN or not WEBHOOK_URL:
    raise ValueError("BOT_TOKEN or WEBHOOK_URL not set")

app = FastAPI()
bot_app = ApplicationBuilder().token(TOKEN).build()

# --- /start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
            InlineKeyboardButton("🆕 Latest", callback_data="latest:0")
        ],
        [
            InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
            InlineKeyboardButton("🔥 Trending", callback_data="trending:0")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome to സുന്ദരി 🔞 bot! Choose a category:",
        reply_markup=reply_markup
    )

# --- Button handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category, page = query.data.split(":")
    page = int(page)
    videos = VIDEOS.get(category, [])

    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.edit_message_text("❌ No more videos.")
        return

    media = []
    for url in batch:
        try:
            media.append(InputMediaVideo(url))
        except Exception as e:
            print(f"Skipping invalid video URL: {url} - {e}")

    if media:
        try:
            await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Failed to send videos: {e}")

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text("Navigate:", reply_markup=nav_markup)

# --- Webhook endpoint ---
@app.post(f"/webhook/{TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)  # Use Application's queue
    await bot_app.process_updates()          # Process pending updates
    return {"ok": True}

# --- Setup handlers ---
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(button_handler))

# --- Startup event: set webhook ---
@app.on_event("startup")
async def on_startup():
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook/{TOKEN}")
    print(f"Webhook set to {WEBHOOK_URL}/webhook/{TOKEN}")

# --- Health check ---
@app.get("/")
async def health():
    return {"status": "ok"}

# --- Run with uvicorn ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
