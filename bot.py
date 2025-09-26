import os
import sys
import sqlite3
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest

# --- Config ---
TOKEN = os.environ.get("BOT_TOKEN", "7515243964:AAHGtdybkCP6SNirAloWHFI8CmYN_LefQFk")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://naughty-suzette-sasis-fdd9317b.koyeb.app/")
ADMIN_ID = 5409412733
LOG_CHANNEL = -1002871565651

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- Database ---
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

# Users table
cursor.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)""")
# Config table (force channel)
cursor.execute("""CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)""")
# Videos table
cursor.execute("""CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    file_id TEXT
)""")
conn.commit()

# --- Helper functions ---
def get_force_channel():
    cursor.execute("SELECT value FROM config WHERE key='force_channel'")
    row = cursor.fetchone()
    return row[0] if row else None

def set_force_channel(channel):
    cursor.execute("INSERT OR REPLACE INTO config(key, value) VALUES('force_channel', ?)", (channel,))
    conn.commit()

def add_video(category, file_id):
    cursor.execute("INSERT INTO videos(category, file_id) VALUES(?, ?)", (category, file_id))
    conn.commit()

def remove_video(category, file_id):
    cursor.execute("DELETE FROM videos WHERE category=? AND file_id=?", (category, file_id))
    conn.commit()

def get_videos(category):
    cursor.execute("SELECT file_id FROM videos WHERE category=?", (category,))
    return [row[0] for row in cursor.fetchall()]

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES(?, ?)", (user.id, user.username))
    conn.commit()

    # Log first-time user
    await context.bot.send_message(LOG_CHANNEL, f"👤 User started bot: {user.first_name} (@{user.username})")

    # Check dynamic force channel
    force_channel = get_force_channel()
    if force_channel:
        try:
            member = await context.bot.get_chat_member(force_channel, user.id)
            if member.status in ["left", "kicked"]:
                await update.message.reply_text(f"⚠️ You must join the channel {force_channel} first to use this bot.")
                return
        except BadRequest:
            await update.message.reply_text(f"⚠️ Force channel {force_channel} is invalid.")
            return

    # Age verification
    keyboard = [
        [InlineKeyboardButton("✅ I am 18+", callback_data="age_verified")],
        [InlineKeyboardButton("❌ Under 18", callback_data="under_18")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚠️ You must be 18+ to use this bot. Please verify:", reply_markup=reply_markup)

# --- Callback Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "age_verified":
        keyboard = [
            [
                InlineKeyboardButton("🏝 Mallu", callback_data="category_mallu"),
                InlineKeyboardButton("🇮🇳 Desi", callback_data="category_desi")
            ],
            [
                InlineKeyboardButton("🔥 Trending", callback_data="category_trending"),
                InlineKeyboardButton("🆕 Latest", callback_data="category_latest")
            ],
            [
                InlineKeyboardButton("💎 Premium", callback_data="category_premium")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✅ Age verified!\n\nPlease select a category:", reply_markup=reply_markup)

    elif query.data == "under_18":
        await query.edit_message_text("❌ You must be 18+ to use this bot.")

    elif query.data.startswith("category_"):
        category = query.data.split("_")[1].lower()
        videos = get_videos(category)
        if not videos:
            await query.edit_message_text(f"🎯 You selected: {category.capitalize()}\nNo videos uploaded yet.")
            return

        for file_id in videos:
            await context.bot.send_video(query.message.chat_id, video=file_id)
        await query.edit_message_text(f"🎯 Sent all videos in category: {category.capitalize()}")

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
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    await update.message.reply_text(f"👥 Total users: {total_users}")

async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setchannel <channel_username_or_id>")
        return
    channel = context.args[0]
    set_force_channel(channel)
    await update.message.reply_text(f"✅ Force channel set to: {channel}")

# --- Bulk Add Videos ---
bulk_category = None
async def bulkadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bulk_category
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /bulkadd <category>")
        return
    bulk_category = context.args[0].lower()
    await update.message.reply_text(f"📥 Send videos now to add to category: {bulk_category}")

# --- Receive Videos for Bulk Add ---
async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bulk_category
    if update.effective_user.id != ADMIN_ID:
        return
    if not bulk_category:
        return
    file_id = update.message.video.file_id
    add_video(bulk_category, file_id)
    await update.message.reply_text(f"✅ Video added to category: {bulk_category}")

# --- Remove Video ---
async def removevideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removevideo <category> <file_id>")
        return
    category, file_id = context.args[0].lower(), context.args[1]
    remove_video(category, file_id)
    await update.message.reply_text(f"🗑 Removed video from category: {category}")

# --- Main ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("setchannel", setchannel))
    app.add_handler(CommandHandler("bulkadd", bulkadd))
    app.add_handler(CommandHandler("removevideo", removevideo))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(button_handler))
    # Video messages
    app.add_handler(MessageHandler(filters.VIDEO, video_handler))

    # Webhook
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        webhook_url=f"{WEBHOOK_URL}{TOKEN}"
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
