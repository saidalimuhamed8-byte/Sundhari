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
    filters
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
FORCE_JOIN_CHANNEL_ID = -1003093267832  # Replace with your private channel ID
FORCE_JOIN_LINK = "https://t.me/+Goi69V3Dr242NzA9"  # Private channel invite link (join requests enabled)

# --- Verified users cache (per channel) ---
verified_users = {}  # key = channel_id, value = set(user_ids)

# --- SQLite Database ---
DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

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

# --- Logging Utility ---
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to send log message: {e}")

# --- Force join channel check ---
async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL_ID, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception as e:
        print(f"Error checking membership: {e}")
    return False

# --- Video upload storage ---
pending_videos = {}  # key=user_id, value=category

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
    channel_id = FORCE_JOIN_CHANNEL_ID

    # Initialize set for the channel if not exists
    if channel_id not in verified_users:
        verified_users[channel_id] = set()

    # --- Force join check (users request to join private channel) ---
    if user_id not in verified_users[channel_id]:
        is_member = await check_channel_membership(user_id, context)
        if not is_member:
            await query.message.reply_text(
                f"⛔ You must request to join our private channel to access videos!\n"
                f"Click here to request: [Request to Join]({FORCE_JOIN_LINK})",
                parse_mode="Markdown"
            )
            return
        else:
            verified_users[channel_id].add(user_id)

    # --- Extract category and page ---
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

    # --- Navigation buttons ---
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

# --- Include all previous admin commands, video handlers, chat_member_update as before ---

# --- Main bot ---
def main():
    init_db()
    webhook_url_path = TOKEN
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    # Add all admin command handlers and video handlers here
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_url_path,
        webhook_url=f"{WEBHOOK_URL.rstrip('/')}/{webhook_url_path}"
    )

if __name__ == "__main__":
    main()
