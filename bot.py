import os
import sqlite3
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaVideo,
)
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
if not WEBHOOK_URL:
    # allow polling if WEBHOOK_URL is not set
    WEBHOOK_URL = None

# Admins who can use admin commands
ADMIN_IDS = [8301447343]  # change to your admin ids
LOG_CHANNEL_ID = -1002871565651  # optional: channel to send logs (change if needed)

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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            first_name TEXT,
            username TEXT,
            is_active INTEGER DEFAULT 1,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # videos
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """
    )

    # pending join requests
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER,
            channel_id INTEGER,
            requested_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, channel_id)
        )
    """
    )

    # force_join config (single row id=1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS force_join (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER,
            invite_link TEXT
        )
    """
    )
    cur.execute("INSERT OR IGNORE INTO force_join (id, channel_id, invite_link) VALUES (1, NULL, NULL)")

    conn.commit()
    conn.close()


# --- force_join helpers
def get_force_join():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, invite_link FROM force_join WHERE id=1")
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None


def update_force_join(channel_id, invite_link):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE force_join SET channel_id=?, invite_link=? WHERE id=1", (channel_id, invite_link))
    conn.commit()
    conn.close()


# --- chats helpers
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


# --- videos helpers
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


# --- pending requests DB
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


def is_pending_request(user_id: int, channel_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pending_requests WHERE user_id=? AND channel_id=?", (user_id, channel_id))
    r = cur.fetchone()
    conn.close()
    return bool(r)


# --- logging utility (optional)
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not LOG_CHANNEL_ID:
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass


# --- membership check
async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channel_id, _ = get_force_join()
    if not channel_id:
        return True  # if not configured, skip check
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    add_chat(chat.id, chat.type, getattr(chat, "first_name", None), getattr(chat, "username", None))
    users, groups = get_active_counts()
    log_text = (
        f"👤 New user started bot:\nID: `{chat.id}`\nName: {chat.first_name}\nUsername: @{chat.username or 'N/A'}\n\n"
        f"📊 Now: 👤 {users} users | 👥 {groups} groups"
    )
    await log_to_channel(context, log_text)

    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"), InlineKeyboardButton("🆕 Latest", callback_data="latest:0")],
        [InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"), InlineKeyboardButton("🔥 Trending", callback_data="trending:0")],
    ]
    await update.message.reply_text("👋 Welcome! Choose a category:", reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    channel_id, invite_link = get_force_join()
    if not channel_id:
        await query.message.reply_text("⚠️ Force-join channel is not configured. Ask admin to set it via /setchannel.")
        return

    # ensure cache entry
    if channel_id not in verified_users:
        verified_users[channel_id] = set()

    # --------- request button (immediately verify & send) ----------
    if query.data.startswith("request:"):
        # callback: request:<category>:<page>
        try:
            _, category, page_str = query.data.split(":")
            page = int(page_str)
        except Exception:
            await query.edit_message_text("❌ Invalid request data.")
            return

        # mark verified locally and remove pending
        verified_users[channel_id].add(user_id)
        if is_pending_request(user_id, channel_id):
            remove_pending_request(user_id, channel_id)

        await query.message.reply_text("✅ Request recorded — sending videos now...")

        # send requested page
        videos = get_videos(category)
        start_idx = page * BATCH_SIZE
        end_idx = start_idx + BATCH_SIZE
        batch = videos[start_idx:end_idx]

        if not batch:
            await query.message.reply_text("❌ No videos in this category.")
            return

        media = [InputMediaVideo(f) for f in batch]
        # send media group (max 10)
        await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

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
        return

    # --------- normal flow: check verified/pending ----------
    if user_id not in verified_users[channel_id]:
        # not verified yet
        if not is_pending_request(user_id, channel_id):
            add_pending_request(user_id, channel_id)
        # callback for request should encode category and page
        # query.data is like "category:page" so pass that into request callback
        keyboard = [[InlineKeyboardButton("Request to Join", callback_data=f"request:{query.data}")]]
        message = (
            "📌 To access videos you must request to join our private channel.\n\n"
            "Click **Request to Join** below — you'll get videos immediately after requesting."
        )
        await query.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --------- user is verified -> send requested page ----------
    # expected callback data: "<category>:<page>"
    try:
        category, page_str = query.data.split(":")
        page = int(page_str)
    except Exception:
        await query.edit_message_text("❌ Invalid button data.")
        return

    videos = get_videos(category)
    start_idx = page * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.edit_message_text("❌ No more videos in this category.")
        return

    media = [InputMediaVideo(f) for f in batch]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

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
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    stats = get_chat_stats()
    msg = "📊 *Bot Usage Stats:*\n"
    for chat_type, count in stats:
        if chat_type == "private":
            msg += f"👤 Users: {count}\n"
        else:
            msg += f"👥 Groups: {count}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setchannel <channel_id> <invite_link>")
        return
    try:
        channel_id = int(context.args[0])
        invite_link = context.args[1]
        update_force_join(channel_id, invite_link)
        # clear in-memory cache for the previous channel if any:
        if channel_id not in verified_users:
            verified_users[channel_id] = set()
        await update.message.reply_text(
            f"✅ Force-join channel updated:\nID: `{channel_id}`\nLink: {invite_link}", parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# --- Video management (admin) ---
async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addvideo <category>\nThen send the video file.")
        return
    category = context.args[0].lower()
    pending_videos[user_id] = category
    await update.message.reply_text(f"📥 Now send the video file to add to category *{category}*", parse_mode="Markdown")


async def bulkadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /bulkadd <category>\nThen send multiple videos as an album.")
        return
    category = context.args[0].lower()
    pending_videos[user_id] = category
    await update.message.reply_text(
        f"📥 Now send multiple videos as an album to add them to category *{category}*", parse_mode="Markdown"
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle single video or each video in an album
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    if user_id not in pending_videos:
        return  # no pending add command
    category = pending_videos[user_id]
    # store file_id
    # support both message.video and message.media_group
    message = update.message
    # single video
    if message.video:
        add_video_to_db(category, message.video.file_id)
    # if it's part of an album, telegram will call this for each video separately (same handler)
    await update.message.reply_text(f"✅ Video added to category *{category}*", parse_mode="Markdown")


async def listvideos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) FROM videos GROUP BY category")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("ℹ️ No videos added yet.")
        return
    msg = "📂 *Video categories:*\n"
    for cat, cnt in rows:
        msg += f"• {cat}: {cnt} videos\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def listcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /listcategory <category>")
        return
    category = context.args[0].lower()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, file_id FROM videos WHERE category=? ORDER BY id ASC", (category,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"No videos in category *{category}*", parse_mode="Markdown")
        return
    txt = f"📂 *Videos in {category}:*\n"
    for i, (vid_id, file_id) in enumerate(rows, start=1):
        txt += f"{i}. `{file_id}`\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


async def removevideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /removevideo <category> <video_number>")
        return
    category = context.args[0].lower()
    try:
        num = int(context.args[1])
    except Exception:
        await update.message.reply_text("Video number must be an integer.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM videos WHERE category=? ORDER BY id ASC", (category,))
    rows = cur.fetchall()
    if not rows or num < 1 or num > len(rows):
        conn.close()
        await update.message.reply_text("Invalid video number.")
        return
    vid_id = rows[num - 1][0]
    cur.execute("DELETE FROM videos WHERE id=?", (vid_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Removed video #{num} from *{category}*", parse_mode="Markdown")


# ---------- Chat member tracking ----------
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("member", "administrator"):
        add_chat(chat.id, chat.type, getattr(chat, "title", None), None)
        update_chat_status(chat.id, 1)
        users, groups = get_active_counts()
        await log_to_channel(context, f"✅ Bot added to group: `{chat.id}` — Now: 👤 {users} users | 👥 {groups} groups")
    elif status in ("left", "kicked"):
        update_chat_status(chat.id, 0)
        users, groups = get_active_counts()
        await log_to_channel(context, f"❌ Bot removed from group: `{chat.id}` — Now: 👤 {users} users | 👥 {groups} groups")


# ---------- Main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # user commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # admin commands
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("setchannel", set_channel))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CommandHandler("bulkadd", bulkadd))
    app.add_handler(CommandHandler("listvideos", listvideos))
    app.add_handler(CommandHandler("listcategory", listcategory))
    app.add_handler(CommandHandler("removevideo", removevideo))

    # chat member & video handlers
    app.add_handler(ChatMemberHandler(chat_member_update, chat_member_types=["my_chat_member"]))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video, block=False))

    if WEBHOOK_URL:
        # run webhook
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}")
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
