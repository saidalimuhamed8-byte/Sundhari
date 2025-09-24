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

# Admins and log channel
ADMIN_IDS = [8301447343]  # your admin ids
LOG_CHANNEL_ID = -1002871565651  # optional

BATCH_SIZE = 10  # videos per page

# ---------- In-memory caches ----------
# verified_users[channel_id] = set(user_ids)
verified_users = {}
# pending videos during admin add: pending_videos[user_id] = category
pending_videos = {}

# ---------- DB ----------
DB_FILE = "bot_data.db"


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

    # pending join requests
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER,
            channel_id INTEGER,
            requested_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, channel_id)
        )
    """)

    # force_join config (single row id=1)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS force_join (
            id INTEGER PRIMARY KEY CHECK (id=1),
            channel_id INTEGER
        )
    """)
    cur.execute("INSERT OR IGNORE INTO force_join (id, channel_id) VALUES (1, NULL)")

    conn.commit()
    conn.close()


# ---------- Force join helpers ----------
def get_force_join():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM force_join WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def update_force_join(channel_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE force_join SET channel_id=? WHERE id=1", (channel_id,))
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


# ---------- Pending requests helpers ----------
def add_pending_request(user_id: int, channel_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO pending_requests (user_id, channel_id) VALUES (?, ?)", (user_id, channel_id))
    conn.commit()
    conn.close()


def remove_pending_request(user_id: int, channel_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_requests WHERE user_id=? AND channel_id=?", (user_id, channel_id))
    conn.commit()
    conn.close()


def is_pending_request(user_id: int, channel_id: int):
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
    channel_id = get_force_join()
    if not channel_id:
        await query.message.reply_text("⚠️ Force-join channel not set.")
        return

    # ---------- Check pending request ----------
    if not is_pending_request(user_id, channel_id):
        # add to pending if not exists
        add_pending_request(user_id, channel_id)
        keyboard = [[InlineKeyboardButton("Request Access", callback_data=f"request:{query.data}")]]
        await query.message.reply_text(
            "📌 You must request access to view videos. Click below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ---------- Send videos ----------
    # decode callback data
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
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    # navigation buttons
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
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /setchannel <channel_id>")
        return
    try:
        new_channel_id = int(context.args[0])
        update_force_join(new_channel_id)
        # clear all verified users and pending requests
        verified_users.clear()
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_requests")
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Force-join channel updated to `{new_channel_id}`.\nAll verifications cleared.",
                                        parse_mode="Markdown")
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


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS or user_id not in pending_videos:
        return
    category = pending_videos[user_id]
    if update.message.video:
        add_video_to_db(category, update.message.video.file_id)
        await update.message.reply_text(f"✅ Video added to category *{category}*", parse_mode="Markdown")


# ---------- Chat member tracking ----------
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("member", "administrator"):
        add_chat(chat.id, chat.type, getattr(chat, "title", None), None)
    elif status in ("left", "kicked"):
        update_chat_status(chat.id, 0)


# ---------- Main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("setchannel", set_channel))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video, block=False))
    app.add_handler(ChatMemberHandler(chat_member_update, chat_member_types=["my_chat_member"]))

    if WEBHOOK_URL:
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN,
                        webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}")
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
