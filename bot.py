import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

# ---------- Config ----------
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

ADMIN_IDS = [8301447343]  # Admin IDs
LOG_CHANNEL_ID = -1002871565651
BATCH_SIZE = 10

pending_videos = {}
DB_FILE = os.environ.get("BOT_DB", "bot_data.db")

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            first_name TEXT,
            username TEXT,
            is_active INTEGER DEFAULT 1,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsub_channel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invite_link TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---------- Chat helpers ----------
def add_chat(chat_id, chat_type, first_name=None, username=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO chats (chat_id, chat_type, first_name, username, is_active) VALUES (?, ?, ?, ?, 1)",
        (chat_id, chat_type, first_name, username),
    )
    conn.commit()
    conn.close()

def update_chat_status(chat_id, is_active: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE chats SET is_active=? WHERE chat_id=?", (is_active, chat_id))
    conn.commit()
    conn.close()

def get_active_counts():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT chat_type, COUNT(*) FROM chats WHERE is_active=1 GROUP BY chat_type")
    stats = dict(cur.fetchall())
    conn.close()
    users = stats.get("private", 0)
    groups = stats.get("group", 0) + stats.get("supergroup", 0)
    return users, groups

def get_chat_stats():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT chat_type, COUNT(*) FROM chats WHERE is_active=1 GROUP BY chat_type")
    stats = cur.fetchall()
    conn.close()
    return stats

# ---------- Video helpers ----------
def add_video_to_db(category: str, file_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO videos (category, file_id) VALUES (?, ?)", (category, file_id))
    conn.commit()
    conn.close()

def get_videos(category: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT file_id FROM videos WHERE category=? ORDER BY id ASC", (category,))
    results = [r[0] for r in cur.fetchall()]
    conn.close()
    return results

# ---------- Fsub helpers ----------
def set_fsub_channel(invite_link: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM fsub_channel")
    cur.execute("INSERT INTO fsub_channel (invite_link) VALUES (?)", (invite_link,))
    conn.commit()
    conn.close()

def get_fsub_channel() -> str:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT invite_link FROM fsub_channel LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

async def send_join_prompt(update, context):
    invite_link = get_fsub_channel()
    if not invite_link:
        return False
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=invite_link)],
        [InlineKeyboardButton("✅ I Joined / Continue", callback_data="continue")]
    ]
    kb = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("⚠️ Please join the channel first:", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_text("⚠️ Please join the channel first:", reply_markup=kb)
    return True

# ---------- Logging ----------
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not LOG_CHANNEL_ID:
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    add_chat(chat.id, chat.type, getattr(chat, "first_name", None), getattr(chat, "username", None))
    
    # Show categories directly (no join button)
    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
         InlineKeyboardButton("🆕 Latest", callback_data="latest:0")],
        [InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
         InlineKeyboardButton("🔥 Trending", callback_data="trending:0")],
    ]
    await update.message.reply_text("👋 Welcome! Choose a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # If user clicked continue after join
    if query.data == "continue":
        # Send videos after join
        if "pending_category" in context.user_data:
            category = context.user_data.pop("pending_category")
            await send_videos_after_join(query, context, category)
        return

    # If user clicked a category
    if ":" in query.data:
        category, page_str = query.data.split(":")
        page = int(page_str)

        # Save category in user_data and show join button first
        context.user_data["pending_category"] = category
        await send_join_prompt(update, context)

async def send_videos_after_join(query, context, category):
    videos = get_videos(category)
    if not videos:
        await query.message.reply_text("❌ No videos in this category.")
        return
    media = [InputMediaVideo(f, has_spoiler=False, supports_streaming=True, has_protected_content=True) for f in videos[:BATCH_SIZE]]
    try:
        await context.bot.send_media_group(chat_id=query.from_user.id, media=media)
        await query.message.reply_text("✅ Videos sent to your PM.")
    except Exception:
        await query.message.reply_text("❌ Cannot send PM. Make sure you started the bot.")

# ---------- Admin Commands ----------
async def fsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /fsub <invite_link>")
        return
    try:
        invite_link = context.args[0]
        set_fsub_channel(invite_link)
        await update.message.reply_text(f"✅ Force sub channel set to `{invite_link}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# Add other admin commands (addvideo, bulkadd, done_bulk, removevideo, getid) here as needed

# ---------- Main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fsub", fsub_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    # Add other admin / video handlers here

    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
