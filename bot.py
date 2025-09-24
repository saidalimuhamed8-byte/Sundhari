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

# ---------- Config ----------
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

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

    users, groups = get_active_counts()

    # Log private user
    if chat.type == "private":
        name = chat.first_name or ""
        username = f"@{chat.username}" if chat.username else "❌ No username"
        log_text = (
            "👤 New user started bot:\n"
            f"ID: `{chat.id}`\n"
            f"Name: {name}\n"
            f"Username: {username}\n\n"
            f"📊 Now: 👤 {users} users | 👥 {groups} groups"
        )
        await log_to_channel(context, log_text)

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
    user_id = query.from_user.id

    # ---------- FSUB check ----------
    fs_channel = get_forcesub_channel()
    if fs_channel and not await is_member(context.bot, user_id, fs_channel):
        chat = await context.bot.get_chat(fs_channel)
        username = getattr(chat, "username", "")

        if username:  # Public channel
            join_link = f"https://t.me/{username}"
            keyboard = [[InlineKeyboardButton("📌 Join Channel", url=join_link)]]
            await query.message.reply_text(
                "You must join the channel to access videos:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:  # Private channel → try to create invite link
            try:
                invite_link = await context.bot.create_chat_invite_link(chat.id, creates_join_request=False)
                keyboard = [[InlineKeyboardButton("📌 Join Channel", url=invite_link.invite_link)]]
                await query.message.reply_text(
                    "You must join the private channel to access videos:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await query.message.reply_text(
                    "❌ Could not generate invite link.\n"
                    "➡️ Make sure the bot is an *admin* of the private channel."
                )
        return

    # ---------- Video pagination ----------
    category, page_str = query.data.split(":")
    page = int(page_str)

    videos = get_videos(category)
    start_idx = page * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.message.reply_text("❌ No videos in this category.")
        return

    media = [InputMediaVideo(f, has_protected_content=True, supports_streaming=True) for f in batch]
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
        await query.message.reply_text("✅ Videos sent to your PM.")
    except Exception:
        await query.message.reply_text("❌ Cannot send PM. Make sure you started the bot.")

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))
    if buttons:
        await query.message.reply_text("Navigate:", reply_markup=InlineKeyboardMarkup([buttons]))

# ---------- (rest of the code: stats, forcesub, add/remove video, chat member logs, etc. stays same) ----------

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    # ... (all other handlers same as before)

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
