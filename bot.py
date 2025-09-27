import os
import sys
import sqlite3
import logging
from typing import List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo, ChatMember
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
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 8000))
LOG_CHANNEL = os.environ.get("LOG_CHANNEL")
if LOG_CHANNEL:
    try:
        LOG_CHANNEL = int(LOG_CHANNEL)
    except Exception:
        pass

# --- Logging ---
logging.basicConfig(level=logging.INFO)
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
    age_confirmed INTEGER DEFAULT 0
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
    cur.execute("INSERT INTO videos (file_id, category) VALUES (?, ?)", (file_id, category))
    conn.commit()

def remove_video_from_db(category: str, index: int) -> bool:
    cur.execute("SELECT id FROM videos WHERE category = ? ORDER BY id ASC", (category,))
    rows = cur.fetchall()
    if 0 <= index < len(rows):
        rowid = rows[index][0]
        cur.execute("DELETE FROM videos WHERE id = ?", (rowid,))
        conn.commit()
        return True
    return False

def get_videos_by_category(category: str) -> List[str]:
    cur.execute("SELECT file_id FROM videos WHERE category = ? ORDER BY id ASC", (category,))
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
        logger.warning("Failed to send log: %s", e)

# --- User Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name)
    )
    conn.commit()
    await safe_send_log(context.bot, f"👤 /start: {first_name} (@{username}) — id:{user_id}")

    welcome = (
        "🔥 *Welcome!* 🔥\n\n"
        "Your personal adult playground — available *24/7*.\n"
        "You must be 18+ to continue."
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
        [InlineKeyboardButton("💎 Premium", callback_data="cat_Premium")]
    ]
    await q.edit_message_text("✅ Age verified!\nSelect a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def category_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    category = q.data.split("_", 1)[1]

    all_videos = get_videos_by_category(category)
    if not all_videos:
        await q.edit_message_text(f"⚠️ No videos available for *{category}*", parse_mode="Markdown")
        return

    fsub_link = get_config("fsub") or "https://t.me/yourchannel"
    kb = [[InlineKeyboardButton("📩 Request to Join Channel", callback_data=f"reqjoin_{category}")]]
    await q.edit_message_text(
        f"🔒 Access to *{category}* requires joining the channel.\n"
        "Click the button below to request access.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def request_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    category = q.data.split("_", 1)[1]
    fsub_channel = get_config("fsub")
    if not fsub_channel:
        await q.edit_message_text("⚠️ Force-sub channel not set by admin.")
        return

    # Save requested category for this user
    context.user_data["requested_category"] = category

    try:
        # Check if user is in the join request list
        member = await context.bot.get_chat_member(chat_id=fsub_channel, user_id=user_id)
        if member.status == ChatMember.RESTRICTED:  # Pending join request
            kb = [[InlineKeyboardButton("🔁 I've requested — Get Videos", callback_data=f"force_{category}_0")]]
            await q.edit_message_text(
                f"✅ Join request detected! Click below to receive videos for *{category}*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            # User has not requested yet → show request button
            kb = [[InlineKeyboardButton("📩 Request to Join Channel", url=fsub_channel)]]
            await q.edit_message_text(
                f"🔒 Access to *{category}* requires requesting access to the private channel.\n"
                "Click the button below to request access first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
    except Exception as e:
        await q.edit_message_text(f"⚠️ Error checking join request: {e}")

async def force_sub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    parts = q.data.split("_")
    category = parts[1]

    all_videos = get_videos_by_category(category)
    if not all_videos:
        await q.edit_message_text(f"⚠️ No videos available for *{category}*", parse_mode="Markdown")
        return

    page = 0
    chunk = paginate_list(all_videos, page, 10)
    media = [InputMediaVideo(media=vid) for vid in chunk]
    await context.bot.send_message(chat_id=user_id, text=f"📂 *{category}* — Page {page+1}", parse_mode="Markdown")
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
    except:
        for m in media:
            await context.bot.send_video(chat_id=user_id, video=m.media)

    nav_kb = [[InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
               InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}")]]
    await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))

async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    direction, category, page = q.data.split("_")
    page = int(page)
    page = page + 1 if direction == "next" else max(page - 1, 0)

    all_videos = get_videos_by_category(category)
    chunk = paginate_list(all_videos, page, 10)
    if not chunk:
        await q.answer("No videos on this page.", show_alert=True)
        return
    media = [InputMediaVideo(media=v) for v in chunk]
    await context.bot.send_message(chat_id=user_id, text=f"📂 *{category}* — Page {page+1}", parse_mode="Markdown")
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
    except:
        for m in media:
            await context.bot.send_video(chat_id=user_id, video=m.media)
    nav_kb = [[InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
               InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}")]]
    await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))

# --- Admin commands ---
# (Your admin commands remain unchanged)
# addvideo_cmd, bulkadd_cmd, done_cmd, video_receiver, removevideo_cmd, stats_cmd, restart_cmd, fsub_cmd

# --- App bootstrap ---
def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # user
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(age_confirm_cb, pattern="^age_confirm$"))
    app.add_handler(CallbackQueryHandler(category_cb, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(request_join_cb, pattern="^reqjoin_"))
    app.add_handler(CallbackQueryHandler(force_sub_cb, pattern="^force_"))
    app.add_handler(CallbackQueryHandler(nav_cb, pattern="^(next|prev)_"))
    # admin
    app.add_handler(CommandHandler("addvideo", addvideo_cmd))
    app.add_handler(CommandHandler("bulkadd", bulkadd_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("removevideo", removevideo_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("fsub", fsub_cmd))
    # video receiver
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(user_id=ADMIN_ID), video_receiver))
    return app

def main():
    app = build_app()
    if not APP_URL:
        logger.error("APP_URL not set.")
        sys.exit(1)
    logger.info("Starting bot with webhook at %s", APP_URL)
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path="", webhook_url=APP_URL)

if __name__ == "__main__":
    main()
