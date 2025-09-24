import os
import re
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

ADMIN_IDS = [8301447343]  # your admin ids
LOG_CHANNEL_ID = -1002871565651
BATCH_SIZE = 10

# ---------- FSUB / Request Channel ----------
id_pattern = re.compile(r"^-?\d+$")
auth_channel = os.environ.get('AUTH_CHANNEL')
AUTH_CHANNEL = int(auth_channel) if auth_channel and id_pattern.search(auth_channel) else None

req_channel = os.environ.get("REQ_CHANNEL")
REQ_CHANNEL = (int(req_channel) if req_channel and id_pattern.search(req_channel) else False) if req_channel is not None else None

# ---------- Caches ----------
verified_users = {}
pending_videos = {}

# ---------- DB ----------
DB_FILE = os.environ.get("JOIN_REQS_DB", "bot_data.db")


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Chats
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
    # Videos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """)
    # Pending join requests
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER,
            channel_id TEXT,
            requested_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, channel_id)
        )
    """)
    # Force join config
    cur.execute("""
        CREATE TABLE IF NOT EXISTS force_join (
            id INTEGER PRIMARY KEY CHECK (id=1),
            channel_id TEXT,
            join_link TEXT
        )
    """)
    cur.execute("INSERT OR IGNORE INTO force_join (id, channel_id, join_link) VALUES (1, NULL, NULL)")
    conn.commit()
    conn.close()


# ---------- FSUB helper ----------
async def is_member(bot, user_id, channel_id):
    """Check if a user is member of channel"""
    if not channel_id:
        return True
    try:
        if str(channel_id).isdigit():
            member = await bot.get_chat_member(chat_id=int(channel_id), user_id=user_id)
            return member.status in ["member", "administrator", "creator"]
        return False
    except BadRequest:
        return False


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


# ---------- Pending requests helpers ----------
def add_pending_request(user_id: int, channel_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO pending_requests (user_id, channel_id) VALUES (?, ?)", (user_id, channel_id))
    conn.commit()
    conn.close()


def remove_pending_request(user_id: int, channel_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_requests WHERE user_id=? AND channel_id=?", (user_id, channel_id))
    conn.commit()
    conn.close()


def is_pending_request(user_id: int, channel_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pending_requests WHERE user_id=? AND channel_id=?", (user_id, channel_id))
    r = cur.fetchone()
    conn.close()
    return bool(r)


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
    await log_to_channel(context, f"👤 New user: `{chat.id}` — Now: 👤 {users} users | 👥 {groups} groups")

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
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, join_link FROM force_join WHERE id=1")
    row = cur.fetchone()
    conn.close()

    channel_id, join_link = row if row else (None, None)

    if channel_id and not await is_member(context.bot, user_id, int(channel_id) if str(channel_id).isdigit() else None):
        add_pending_request(user_id, channel_id)
        if join_link:
            keyboard = [[InlineKeyboardButton("🔗 Join Channel", url=join_link)]]
            await query.message.reply_text("📌 You must join the channel first:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text("❌ You must join the channel first. Contact admin.")
        return

    # ---------- Existing video logic ----------
    if query.data.startswith("request:"):
        _, data = query.data.split(":", 1)
        category, page_str = data.split(":")
    else:
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
        await query.message.reply_text("❌ Cannot send PM. Make sure you started the bot.")

    # navigation
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))
    if buttons:
        await query.message.reply_text("Navigate:", reply_markup=InlineKeyboardMarkup([buttons]))
    else:
        await query.message.reply_text("End of videos.")


# ---------- Admin commands ----------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized.")
        return
    stats = get_chat_stats()
    msg = "📊 *Bot Usage Stats:*\n"
    for chat_type, count in stats:
        msg += f"👤 Users: {count}\n" if chat_type == "private" else f"👥 Groups: {count}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setchannel <channel_id_or_username> <join_link>")
        return

    channel_input = context.args[0]
    join_link = context.args[1]

    try:
        if channel_input.startswith("@"):
            chat = await context.bot.get_chat(channel_input)
            channel_id = str(chat.id)
        else:
            channel_id = channel_input

        global AUTH_CHANNEL
        AUTH_CHANNEL = int(channel_id) if str(channel_id).isdigit() else channel_id

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("UPDATE force_join SET channel_id=?, join_link=? WHERE id=1", (AUTH_CHANNEL, join_link))
        cur.execute("DELETE FROM pending_requests")
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Force-join channel set.\nChannel ID: `{channel_id}`\nJoin link: {join_link}", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ---------- Video management ----------
async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addvideo <category>\nThen send the video.")
        return
    pending_videos[update.effective_user.id] = context.args[0].lower()
    await update.message.reply_text(f"📥 Now send the video to add to category *{context.args[0]}*", parse_mode="Markdown")


async def bulkadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /bulkadd <category>\nThen send multiple videos. Send /done to finish.")
        return
    category = context.args[0].lower()
    pending_videos[update.effective_user.id] = {"category": category, "bulk": True}
    await update.message.reply_text(f"📥 Now send the videos for category *{category}*.\nSend /done when finished.", parse_mode="Markdown")


async def done_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in pending_videos and isinstance(pending_videos[user_id], dict) and pending_videos[user_id].get("bulk"):
        del pending_videos[user_id]
        await update.message.reply_text("✅ Bulk upload finished.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS or user_id not in pending_videos:
        return
    if isinstance(pending_videos[user_id], dict):
        category = pending_videos[user_id]["category"]
    else:
        category = pending_videos[user_id]

    if update.message.video:
        add_video_to_db(category, update.message.video.file_id)
        await update.message.reply_text(f"✅ Video added to category *{category}*", parse_mode="Markdown")


async def removevideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /removevideo <category> <index>")
        return
    category = context.args[0].lower()
    try:
        index = int(context.args[1]) - 1
        videos = get_videos(category)
        if index < 0 or index >= len(videos):
            await update.message.reply_text("❌ Invalid index")
            return
        file_id = videos[index]
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("DELETE FROM videos WHERE category=? AND file_id=?", (category, file_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Video at index {index+1} removed from category *{category}*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ---------- Chat member tracking ----------
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("member", "administrator"):
        add_chat(chat.id, chat.type, getattr
