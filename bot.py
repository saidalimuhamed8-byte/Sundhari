import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# --- Environment Variables ---
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8000))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL not set in environment variables")

# --- Admin & Log Config ---
ADMIN_IDS = [8301447343]  # Replace with your Telegram user ID
LOG_CHANNEL_ID = -1002871565651  # Replace with your log channel ID

# --- Verified users cache (per channel) ---
verified_users = {}  # key = channel_id, value = set(user_ids)

# --- SQLite Database ---
DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Chats table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            first_name TEXT,
            username TEXT,
            is_active INTEGER DEFAULT 1,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Videos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """)
    # Pending requests
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER,
            channel_id INTEGER,
            requested_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, channel_id)
        )
    """)
    # Force join channel (only one row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS force_join (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER,
            invite_link TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO force_join (id, channel_id, invite_link) VALUES (1, NULL, NULL)")
    conn.commit()
    conn.close()

# --- Force join helpers ---
def get_force_join():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, invite_link FROM force_join WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None)

def update_force_join(channel_id, invite_link):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE force_join SET channel_id=?, invite_link=? WHERE id=1",
                   (channel_id, invite_link))
    conn.commit()
    conn.close()

# --- DB helper functions ---
def add_chat(chat_id, chat_type, first_name=None, username=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO chats (chat_id, chat_type, first_name, username, is_active)
        VALUES (?, ?, ?, ?, 1)
    """, (chat_id, chat_type, first_name, username))
    conn.commit()
    conn.close()

def update_chat_status(chat_id, is_active: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE chats SET is_active=? WHERE chat_id=?", (is_active, chat_id))
    conn.commit()
    conn.close()

def get_active_counts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_type, COUNT(*) FROM chats WHERE is_active=1 GROUP BY chat_type")
    stats = dict(cursor.fetchall())
    conn.close()
    users = stats.get("private", 0)
    groups = stats.get("group", 0) + stats.get("supergroup", 0)
    return users, groups

def get_videos(category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM videos WHERE category=? ORDER BY id ASC", (category,))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

# --- Pending requests DB ---
def add_pending_request(user_id, channel_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO pending_requests (user_id, channel_id) VALUES (?, ?)
    """, (user_id, channel_id))
    conn.commit()
    conn.close()

def remove_pending_request(user_id, channel_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM pending_requests WHERE user_id=? AND channel_id=?
    """, (user_id, channel_id))
    conn.commit()
    conn.close()

def is_pending_request(user_id, channel_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM pending_requests WHERE user_id=? AND channel_id=?
    """, (user_id, channel_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# --- Logging Utility ---
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to send log message: {e}")

# --- Force join check ---
async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channel_id, _ = get_force_join()
    if not channel_id:
        return True  # No force join set
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception as e:
        print(f"Error checking membership: {e}")
    return False

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    add_chat(chat.id, chat.type, getattr(chat, 'first_name', None), getattr(chat, 'username', None))

    users, groups = get_active_counts()
    log_text = (
        f"👤 New user started bot:\nID: `{chat.id}`\n"
        f"Name: {chat.first_name}\nUsername: @{chat.username or 'N/A'}\n\n"
        f"📊 Now: 👤 {users} users | 👥 {groups} groups"
    )
    await log_to_channel(context, log_text)

    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="mallu:0"),
         InlineKeyboardButton("🆕 Latest", callback_data="latest:0")],
        [InlineKeyboardButton("🇮🇳 Desi", callback_data="desi:0"),
         InlineKeyboardButton("🔥 Trending", callback_data="trending:0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome! Choose a category:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    channel_id, invite_link = get_force_join()
    if not channel_id:
        await query.message.reply_text("⚠️ No force-join channel set. Ask admin to configure with /setchannel.")
        return

    if channel_id not in verified_users:
        verified_users[channel_id] = set()

    # --- Handle Request to Join ---
    if query.data.startswith("request:"):
        try:
            _, category, page_str = query.data.split(":")
            page = int(page_str)
        except:
            await query.edit_message_text("❌ Invalid request data.")
            return

        verified_users[channel_id].add(user_id)
        if is_pending_request(user_id, channel_id):
            remove_pending_request(user_id, channel_id)

        await query.message.reply_text("✅ Request sent! You now have access to videos.")

    # --- Force join check for other buttons ---
    elif user_id not in verified_users[channel_id]:
        if not is_pending_request(user_id, channel_id):
            add_pending_request(user_id, channel_id)
        keyboard = [
            [InlineKeyboardButton("Request to Join", callback_data=f"request:{query.data}")]
        ]
        await query.message.reply_text(
            "📌 Click **Request to Join** to access videos instantly.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- Send video batch ---
    try:
        category, page_str = query.data.split(":")
        page = int(page_str)
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Invalid button data.")
        return

    videos = get_videos(category)
    start_idx = page * 1
    end_idx = start_idx + 1
    batch = videos[start_idx:end_idx]

    if not batch:
        await query.edit_message_text("❌ No more videos in this category.")
        return

    media = [InputMediaVideo(file_id) for file_id in batch]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{category}:{page-1}"))
    if end_idx < len(videos):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{category}:{page+1}"))

    if buttons:
        nav_markup = InlineKeyboardMarkup([buttons])
        await query.message.reply_text("Navigate:", reply_markup=nav_markup)
    else:
        await query.message.reply_text("End of videos.")

# --- Admin Command: Set Force Join Channel ---
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /setchannel <channel_id> <invite_link>")
        return

    try:
        channel_id = int(context.args[0])
        invite_link = context.args[1]
        update_force_join(channel_id, invite_link)
        await update.message.reply_text(
            f"✅ Force-join channel updated:\n\nID: `{channel_id}`\nLink: {invite_link}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- Main bot ---
def main():
    init_db()
    webhook_url_path = TOKEN
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("setchannel", set_channel))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_url_path,
        webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{webhook_url_path}"
    )

if __name__ == "__main__":
    main()
