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

# ---------- FSUB helpers ----------
async def is_member(bot, user_id, chat_id):
    if not chat_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False

async def can_request_join(bot, chat_id):
    try:
        me = await bot.get_me()
        my_status = await bot.get_chat_member(chat_id=chat_id, user_id=me.id)
        return my_status.status == "administrator"
    except Exception:
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
    fs_chat_id = get_forcesub_channel()
    if fs_chat_id:
        if not await is_member(context.bot, user_id, fs_chat_id):
            try:
                chat = await context.bot.get_chat(fs_chat_id)
                title = getattr(chat, "title", "No title")
                username = getattr(chat, "username", None)
                chat_type = getattr(chat, "type", "channel")
                bot_can_request = await can_request_join(context.bot, fs_chat_id)

                if username and chat_type in ("channel", "supergroup") and not bot_can_request:
                    link = f"https://t.me/{username}"
                    button = InlineKeyboardButton("📌 Join", url=link)
                    await query.message.reply_text(
                        f"🔗 You must join: [{title}]({link})",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[button]]),
                        disable_web_page_preview=True
                    )
                elif bot_can_request:
                    button = InlineKeyboardButton("🚪 REQUEST TO JOIN", request_join_chat=fs_chat_id)
                    await query.message.reply_text(
                        f"🔗 You must join the private {chat_type}: *{title}*",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[button]]),
                        disable_web_page_preview=True
                    )
                else:
                    await query.message.reply_text(
                        "You must join the required chat to access videos.\n"
                        "Since it is private, please join manually using the invite link."
                    )
            except Exception:
                await query.message.reply_text(
                    "You must join the required chat to access videos.\n"
                    "Since it is private, please join manually using the invite link."
                )
            return  # Stop here until user joins

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

    media = [InputMediaVideo(f, has_spoiler=False, supports_streaming=True, has_protected_content=True) for f in batch]
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

# ---------- Admin / Bot commands ----------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized.")
        return
    stats = get_chat_stats()
    msg = "📊 *Bot Usage Stats:*\n"
    for chat_type, count in stats:
        msg += f"👤 Users: {count}\n" if chat_type == "private" else f"👥 Groups: {count}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def forcesub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /forcesub <channel_id>")
        return
    try:
        channel_id = int(context.args[0])
        set_forcesub_channel(channel_id)
        await update.message.reply_text(f"✅ Forcesub channel set to `{channel_id}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fs_channel = get_forcesub_channel()
    if not fs_channel:
        await update.message.reply_text("ℹ️ Force subscription is not enabled.")
        return
    try:
        chat = await context.bot.get_chat(fs_channel)
        title = getattr(chat, "title", "No title")
        username = getattr(chat, "username", None)
        if username:
            link = f"https://t.me/{username}"
            button = InlineKeyboardButton("📌 Join Channel", url=link)
            await update.message.reply_text(
                f"🔗 You must join: [{title}]({link})",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[button]]),
                disable_web_page_preview=True
            )
        else:
            button = InlineKeyboardButton("🚪 REQUEST TO JOIN", request_join_chat=fs_channel)
            await update.message.reply_text(
                f"🔗 You must join the private channel: *{title}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[button]]),
                disable_web_page_preview=True
            )
    except Exception:
        await update.message.reply_text(
            "You must join the required channel to access videos.\n"
            "Since it is private, please join manually using the invite link."
        )

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

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(f"📌 This chat ID is: `{chat.id}`", parse_mode="Markdown")

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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("forcesub", forcesub))
    app.add_handler(CommandHandler("fsub", fsub))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CommandHandler("bulkadd", bulkadd))
    app.add_handler(CommandHandler("done", done_bulk))
    app.add_handler(CommandHandler("removevideo", removevideo))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video, block=False))
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
