import os
import sys
import logging
import aiosqlite
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest

# --- Config ---
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "YOUR_WEBHOOK_URL")
ADMIN_ID = 5409412733
LOG_CHANNEL = -1002871565651
DB_PATH = "bot.db"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Helper functions ---
async def get_force_channel():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM config WHERE key='force_channel'") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_force_channel(channel):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO config(key, value) VALUES('force_channel', ?)", (channel,))
        await db.commit()

async def add_user(user_id, username):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, username) VALUES(?, ?)", (user_id, username)
        )
        await db.commit()

async def get_total_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0]

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.username)

    # Log first-time user
    await context.bot.send_message(LOG_CHANNEL, f"👤 User started bot: {user.first_name} (@{user.username})")

    # Check force channel
    force_channel = await get_force_channel()
    if force_channel:
        try:
            member = await context.bot.get_chat_member(force_channel, user.id)
            if member.status in ["left", "kicked"]:
                await update.message.reply_text(
                    f"⚠️ You must join the channel {force_channel} first to use this bot."
                )
                return
        except BadRequest:
            await update.message.reply_text(f"⚠️ Force channel {force_channel} is invalid.")
            return

    # Age verification
    keyboard = [
        [InlineKeyboardButton("✅ I am 18+", callback_data="age_verified")],
        [InlineKeyboardButton("❌ Under 18", callback_data="under_18")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚠️ You must be 18+ to use this bot. Please verify:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "age_verified":
        keyboard = [
            [InlineKeyboardButton("🏝 Mallu", callback_data="category_mallu"),
             InlineKeyboardButton("🇮🇳 Desi", callback_data="category_desi")],
            [InlineKeyboardButton("🔥 Trending", callback_data="category_trending"),
             InlineKeyboardButton("🆕 Latest", callback_data="category_latest")],
            [InlineKeyboardButton("💎 Premium", callback_data="category_premium")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✅ Age verified!\n\nPlease select a category:", reply_markup=reply_markup)

    elif query.data == "under_18":
        await query.edit_message_text("❌ You must be 18+ to use this bot.")

    elif query.data.startswith("category_"):
        category = query.data.split("_")[1].capitalize()
        await query.edit_message_text(f"🎯 You selected: {category}\nContent coming soon!")

# --- Admin Commands ---
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    await update.message.reply_text("🔄 Restarting bot...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    total_users = await get_total_users()
    await update.message.reply_text(f"👥 Total users: {total_users}")

async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setchannel <channel_username_or_id>")
        return
    channel = context.args[0]
    await set_force_channel(channel)
    await update.message.reply_text(f"✅ Force channel set to: {channel}")

# --- Main Function ---
async def main():
    # Initialize DB tables
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)""")
        await db.commit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("setchannel", setchannel))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    # Webhook
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        webhook_url=f"{WEBHOOK_URL}{TOKEN}"
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
