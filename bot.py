import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------- Config ---------------- #
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))  # Replace or set in env

# ---------------- Logging ---------------- #
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Database ---------------- #
DB_FILE = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_user_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

def set_channel(channel: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('channel', ?)", (channel,))
    conn.commit()
    conn.close()

def get_channel():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='channel'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------------- Handlers ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)

    keyboard = [
        [InlineKeyboardButton("✅ Yes, I’m 18+", callback_data="age_yes")],
        [InlineKeyboardButton("❌ No", callback_data="age_no")],
    ]
    await update.message.reply_text("🔞 Are you 18+?", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "age_yes":
        keyboard = [
            [InlineKeyboardButton("🔥 Mallu", callback_data="cat_mallu")],
            [InlineKeyboardButton("💃 Desi", callback_data="cat_desi")],
            [InlineKeyboardButton("📈 Trending", callback_data="cat_trending")],
            [InlineKeyboardButton("🆕 Latest", callback_data="cat_latest")],
            [InlineKeyboardButton("⭐ Premium", callback_data="cat_premium")],
        ]
        await query.edit_message_text("Choose your category:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "age_no":
        await query.edit_message_text("❌ You must be 18+ to use this bot.")
    elif query.data.startswith("cat_"):
        await query.edit_message_text(f"✅ You chose: {query.data.split('_')[1].title()}")

# ---------------- Admin Commands ---------------- #
async def setchannel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Not authorized")
    if not context.args:
        return await update.message.reply_text("Usage: /setchannel <channel_username_or_id>")
    channel = context.args[0]
    set_channel(channel)
    await update.message.reply_text(f"✅ Force-subscription channel set to: {channel}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Not authorized")
    count = get_user_count()
    await update.message.reply_text(f"📊 Total users: {count}")

async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Not authorized")
    await update.message.reply_text("🔄 Restarting...")
    os._exit(0)  # Heroku/Koyeb will auto-restart the dyno

# ---------------- Main ---------------- #
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Admin commands
    app.add_handler(CommandHandler("setchannel", setchannel_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))

    # Start webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
    )

if __name__ == "__main__":
    main()
