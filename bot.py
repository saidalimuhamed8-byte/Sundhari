# bot.py - full updated version with instant verification
import os
import sys
import sqlite3
import logging
from typing import List

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
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Config / env ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
APP_URL = os.environ.get("APP_URL", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 8000))
LOG_CHANNEL = os.environ.get("LOG_CHANNEL")

if LOG_CHANNEL:
    try:
        LOG_CHANNEL = int(LOG_CHANNEL)
    except Exception:
        pass

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- DB ---
DB_FILE = "bot.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    username TEXT,
    first_name TEXT,
    age_confirmed INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0,
    last_category TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    category TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS config(
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
conn.commit()

# --- Helpers ---
def get_config(key: str):
    cur.execute("SELECT value FROM config WHERE key = ?", (key,))
    r = cur.fetchone()
    return r[0] if r else None

def set_config(key: str, value: str):
    cur.execute("INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)", (key, value))
    conn.commit()

def add_video_to_db(file_id: str, category: str):
    cur.execute("INSERT INTO videos(file_id, category) VALUES(?, ?)", (file_id, category))
    conn.commit()

def remove_video_from_db(category: str, index: int) -> bool:
    cur.execute("SELECT id FROM videos WHERE category = ? ORDER BY id ASC", (category,))
    rows = cur.fetchall()
    if 0 <= index < len(rows):
        cur.execute("DELETE FROM videos WHERE id = ?", (rows[index][0],))
        conn.commit()
        return True
    return False

def get_videos_by_category(category: str) -> List[str]:
    cur.execute("SELECT file_id FROM videos WHERE category=? ORDER BY id ASC", (category,))
    return [r[0] for r in cur.fetchall()]

def paginate_list(items: List, page: int, page_size: int = 10) -> List:
    start = page * page_size
    end = start + page_size
    return items[start:end]

async def safe_send_log(bot, text: str):
    if not LOG_CHANNEL:
        return
    try:
        await bot.send_message(LOG_CHANNEL, text)
    except Exception as e:
        logger.warning("Failed to send log message: %s", e)

async def try_verify_user_in_pending(app, chat_identifier, user_id: int) -> bool:
    """
    Check if user is in pending join requests of the channel.
    Works only if bot is admin.
    """
    try:
        # Only works if numeric or username
        if isinstance(chat_identifier, str) and chat_identifier.startswith("https://"):
            return False  # cannot use invite link
        if isinstance(chat_identifier, str) and chat_identifier.lstrip("-").isdigit():
            chat_id = int(chat_identifier)
        else:
            chat_id = chat_identifier
        member = await app.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
        # if status is "pending" or "restricted" we can consider verified in pending
        if member.status == "restricted" or member.status == "left":
            return False
    except Exception as e:
        logger.debug("Pending verification check failed: %s", e)
    return False

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""

    cur.execute("INSERT OR IGNORE INTO users(user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name))
    conn.commit()
    await safe_send_log(context.bot, f"👤 New /start: {first_name} (@{username}) — id: {user_id}")

    welcome = (
        "🔥 *Welcome!* 🔥\n\n"
        "Your personal adult playground — available *24/7*.\n"
        "Safe, anonymous, and spicy content.\n\n"
        "👉 *You must be 18 or older to use this bot.*"
    )
    keyboard = [[InlineKeyboardButton("✅ I am 18 or older", callback_data="age_confirm")]]
    await update.message.reply_markdown(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

async def age_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    cur.execute("UPDATE users SET age_confirmed=1 WHERE user_id=?", (user_id,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("🏝 Mallu", callback_data="cat_Mallu"),
         InlineKeyboardButton("🇮🇳 Desi", callback_data="cat_Desi")],
        [InlineKeyboardButton("🔥 Trending", callback_data="cat_Trending"),
         InlineKeyboardButton("🆕 Latest", callback_data="cat_Latest")],
        [InlineKeyboardButton("💎 Premium", callback_data="cat_Premium")],
    ]
    await q.edit_message_text("✅ Age verified!\n\nSelect a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def category_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category selection and auto-verification flow."""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    category = q.data.split("_", 1)[1]

    fsub = get_config("fsub")
    cur.execute("SELECT verified FROM users WHERE user_id=?", (user_id,))
    r = cur.fetchone()
    verified = r[0] == 1 if r else False

    # Attempt instant verification if fsub set
    if fsub and not verified:
        ok = await try_verify_user_in_pending(context.application, fsub, user_id)
        if ok:
            verified = True
            cur.execute("UPDATE users SET verified=1, last_category=? WHERE user_id=?", (category, user_id))
            conn.commit()
        else:
            kb = [[InlineKeyboardButton("📩 Request to Join Channel", url=fsub)]]
            await q.edit_message_text(
                f"🔒 To access *{category}* videos you must request access first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

    if verified:
        cur.execute("UPDATE users SET last_category=? WHERE user_id=?", (category, user_id))
        conn.commit()
        await send_videos_page(user_id, context, category, 0)

async def send_videos_page(user_id, context, category, page):
    all_videos = get_videos_by_category(category)
    if not all_videos:
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ No videos available for *{category}*.", parse_mode="Markdown")
        return
    chunk = paginate_list(all_videos, page)
    media = [InputMediaVideo(media=v) for v in chunk]
    await context.bot.send_message(chat_id=user_id, text=f"📂 *{category}* — Page {page+1}", parse_mode="Markdown")
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
    except Exception:
        for m in media:
            await context.bot.send_video(chat_id=user_id, video=m.media)
    nav_kb = [
        [InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
         InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}")]
    ]
    await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))

async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    parts = q.data.split("_")
    if len(parts) != 3:
        return
    direction, category, page = parts
    page = int(page)
    page = page + 1 if direction == "next" else max(page - 1, 0)
    await send_videos_page(user_id, context, category, page)

# --- Admin commands ---
async def addvideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    context.user
