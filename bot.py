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
from telegram.error import BadRequest
import logging

# Set logging level for detailed debugging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)

# ---------- Config ----------
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL not set in environment variables")

# Admins and log channel
ADMIN_IDS = [8301447343]  # your admin ids
LOG_CHANNEL_ID = -1002871565651  # optional
BATCH_SIZE = 10  # videos per page

# ---------- In-memory caches ----------
pending_videos = {}

# ---------- DB ----------
DB_FILE = os.environ.get("BOT_DB", "bot_data.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # chats
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
    # videos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """)
    # forcesub channel
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forcesub (
            id INTEGER PRIMARY KEY CHECK (id=1),
            channel_id INTEGER
        )
    """)
    cur.execute("INSERT OR IGNORE INTO forcesub (id, channel_id) VALUES (1, NULL)")
    conn.commit()
    conn.close()

def get_forcesub_channel():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM forcesub WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_forcesub_channel(channel_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE forcesub SET channel_id=? WHERE id=1", (channel_id,))
    conn.commit()
    conn.close()

def get_video_categories():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM videos")
    results = [r[0] for r in cur.fetchall()]
    conn.close()
    return results

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

# ---------- FSUB helper ----------
async def is_member(bot, user_id, channel_id):
    if not channel_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

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

    # Log new user
    if chat.type == "private":
        name = chat.first_name or ""
        username = f"@{chat.username}" if chat.username else "❌ No username"
        users, groups = get_active_counts()
        log_text = (
            "👤 New user started bot:\n"
            f"ID: `{chat.id}`\n"
            f"Name: {name}\n"
            f"Username: {username}\n\n"
            f"📊 Now: 👤 {users} users | 👥 {groups} groups"
        )
        await log_to_channel(context, log_text)

    categories = get_video_categories()
    if categories:
        keyboard = [[InlineKeyboardButton(cat.capitalize(), callback_data=f"{cat}:0")] for cat in categories]
        await update.message.reply_text("👋 Welcome! Choose a category:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Welcome! No categories found. An admin needs to add videos first.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # --- The Force Subscribe check is now here! ---
    fs_channel = get_forcesub_channel()
    if fs_channel and not await is_member(context.bot, user_id, fs_channel):
        chat_info = await context.bot.get_chat(fs_channel)
        username = getattr(chat_info, "username", "")
        
        join_link = f"https://t.me/{username}" if username else await context.bot.create_chat_invite_link(fs_channel).invite_link

        keyboard = [[InlineKeyboardButton("📌 Join Channel", url=join_link)]]
        await query.message.reply_text(
            "You must join the channel to access videos:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # --- If the user is a member, continue with the video logic ---
    category, page_str = query.data.split(":")
    page = int(page_str)

    videos = get_videos(category)
    start_idx = page * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.message.reply_text("❌ No videos in this category.")
        return

    media = [InputMediaVideo(f) for f in batch]
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
        await query.message.reply_text("✅ Videos sent to your PM.")
    except Exception:
        await query.message.reply_text("❌ Cannot send PM. Make sure you started the bot in PM.")

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))
    if buttons:
        await query.message.reply_text("Navigate:", reply_markup=InlineKeyboardMarkup([buttons]))
        
async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
        
    if not update.message.video or not context.args:
        await update.message.reply_text("Usage: Forward a video and use /addvideo <category> in the caption.")
        return

    category = context.args[0].lower()
    file_id = update.message.video.file_id
    
    add_video_to_db(category, file_id)
    await update.message.reply_text(f"✅ Video added to category '{category}'.")
    
async def set_forcesub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: `/setfsub <channel_id>`\nExample: `/setfsub -10012345678`")
        return
    
    try:
        channel_id = int(context.args[0])
        set_forcesub_channel(channel_id)
        await update.message.reply_text(f"✅ Force subscription channel set to `{channel_id}`.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid channel ID. Must be a number.")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setfsub", set_forcesub))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, add_video))
    app.add_handler(CallbackQueryHandler(button_handler))

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
