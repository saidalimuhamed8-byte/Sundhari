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
            stats_shown INTEGER DEFAULT 0,
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

def mark_stats_shown(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE chats SET stats_shown=1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def has_shown_stats(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT stats_shown FROM chats WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False

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

def remove_video_from_db(category: str, index: int):
    videos = get_videos(category)
    if index < 0 or index >= len(videos):
        return False
    file_id = videos[index]
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM videos WHERE category=? AND file_id=?", (category, file_id))
    conn.commit()
    conn.close()
    return True

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
    
    # Show categories directly
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
    user_data = context.user_data

    if query.data == "continue":
        user_data["joined"] = True
        if "pending_category" in user_data:
            category = user_data.pop("pending_category")
            await send_videos_after_join(query, context, category, 0)
        return

    if ":" in query.data:
        category, page_str = query.data.split(":")
        page = int(page_str)

        if not user_data.get("joined", False):
            user_data["pending_category"] = category
            await send_join_prompt(update, context)
        else:
            await send_videos_after_join(query, context, category, page)

async def send_videos_after_join(query, context, category, page):
    videos = get_videos(category)
    if not videos:
        await query.message.reply_text("❌ No videos in this category.")
        return

    start_idx = page * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    batch = videos[start_idx:end_idx]
    media = [InputMediaVideo(f, has_spoiler=False, supports_streaming=True, has_protected_content=True) for f in batch]

    try:
        await context.bot.send_media_group(chat_id=query.from_user.id, media=media)
    except Exception:
        await query.message.reply_text("❌ Cannot send PM. Make sure you started the bot.")

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))
    if buttons:
        await query.message.reply_text("Navigate:", reply_markup=InlineKeyboardMarkup([buttons]))

# ---------- Admin Commands ----------
async def fsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /fsub <invite_link>")
        return
    set_fsub_channel(context.args[0])
    await update.message.reply_text(f"✅ Force sub channel set to `{context.args[0]}`", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if has_shown_stats(chat_id):
        await update.message.reply_text("ℹ️ Stats already shown.")
        return
    users, groups = get_active_counts()
    msg = f"📊 *Bot Stats:*\n👤 Users: {users}\n👥 Groups: {groups}"
    await update.message.reply_text(msg, parse_mode="Markdown")
    mark_stats_shown(chat_id)
    await log_to_channel(context, f"📊 User {chat_id} checked bot stats.\nUsers: {users} | Groups: {groups}")

async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addvideo <category>\nThen send a video")
        return
    pending_videos[update.effective_user.id] = context.args[0].lower()
    await update.message.reply_text(f"📥 Send a video to add to category *{context.args[0]}*", parse_mode="Markdown")

async def bulkadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /bulkadd <category>\nThen send multiple videos. Send /done when finished.")
        return
    category = context.args[0].lower()
    pending_videos[update.effective_user.id] = {"category": category, "bulk": True}
    await update.message.reply_text(f"📥 Send videos for category *{category}*.\nSend /done to finish.", parse_mode="Markdown")

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
        if remove_video_from_db(category, index):
            await update.message.reply_text(f"✅ Removed video {index+1} from category *{category}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Invalid index")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ---------- Chat member tracking ----------
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("member", "administrator"):
        add_chat(chat.id, chat.type, getattr(chat, "title", None), getattr(chat, "username", None))
    elif status in ("left", "kicked"):
        update_chat_status(chat.id, 0)

# ---------- Main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fsub", fsub_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CommandHandler("bulkadd", bulkadd))
    app.add_handler(CommandHandler("done", done_bulk))
    app.add_handler(CommandHandler("removevideo", removevideo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video, block=False))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatMemberHandler(chat_member_update, chat_member_types=["my_chat_member"]))

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
