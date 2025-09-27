import os
import sys
import sqlite3
import logging
from typing import List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
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
    age_confirmed INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0
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

async def try_verify_user_via_chat_member(app, chat_identifier, user_id: int) -> bool:
    try:
        if isinstance(chat_identifier, str) and chat_identifier.startswith("https://"):
            return False
        if isinstance(chat_identifier, str) and chat_identifier.lstrip("-").isdigit():
            chat_id = int(chat_identifier)
        else:
            chat_id = chat_identifier
        member = await app.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception as e:
        logger.debug("Verification failed: %s", e)
    return False

# --- fsub helper ---
async def check_fsub_user(app, user_id: int) -> bool:
    fsub = get_config("fsub")
    if not fsub:
        return True  # No fsub set
    try:
        chat_id = int(fsub) if fsub.lstrip("-").isdigit() else fsub
        member = await app.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            cur.execute("UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.warning("Fsub verification failed: %s", e)
    return False

async def ensure_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id == ADMIN_ID:
        return True

    cur.execute("SELECT verified FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    verified = row[0] == 1 if row else False
    if verified:
        return True

    if not await check_fsub_user(context.application, user_id):
        fsub = get_config("fsub") or "https://t.me/yourchannel"
        kb = [
            [InlineKeyboardButton("📩 Join Channel", url=fsub)],
            [InlineKeyboardButton("🔁 I've joined — Verify", callback_data="verifynow_General_0")]
        ]
        try:
            if update.message:
                await update.message.reply_text(
                    "🔒 You must join the channel to use this bot.",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            elif update.callback_query:
                await update.callback_query.edit_message_text(
                    "🔒 You must join the channel to use this bot.",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        except:
            pass
        return False
    return True

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_fsub(update, context):
        return
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
    if not await ensure_fsub(update, context):
        return
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
    if not await ensure_fsub(update, context):
        return
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    category = q.data.split("_", 1)[1]

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

async def verifynow_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    parts = q.data.split("_")
    category = parts[1] if len(parts) > 1 else "General"

    if await check_fsub_user(context.application, user_id):
        await q.edit_message_text("✅ Verified! Sending videos...")
        await category_cb(update, context)
    else:
        await q.answer("❌ Still not verified. Make sure you joined the channel.", show_alert=True)

async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_fsub(update, context):
        return
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    direction, category, page = q.data.split("_")
    page = int(page)
    if direction == "next":
        page += 1
    else:
        page = max(page - 1, 0)
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
async def addvideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    context.user_data["adding_single"] = True
    await update.message.reply_text("📤 Reply/send a video with caption as category. /cancel to abort.")

async def bulkadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    if not context.args:
        return await update.message.reply_text("Usage: /bulkadd <category>")
    context.user_data["bulk_mode"] = True
    context.user_data["bulk_category"] = context.args[0]
    await update.message.reply_text(f"📥 Bulk add started for *{context.args[0]}*. Send videos, /done to finish.", parse_mode="Markdown")

async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("bulk_mode"):
        context.user_data.pop("bulk_mode")
        context.user_data.pop("bulk_category")
        await update.message.reply_text("✅ Bulk add finished.")
    else:
        await update.message.reply_text("No bulk add in progress.")

async def video_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    file_id = update.message.video.file_id
    if context.user_data.get("adding_single"):
        category = update.message.caption or ""
        if not category:
            await update.message.reply_text("Send caption as category.")
            return
        add_video_to_db(file_id, category)
        context.user_data.pop("adding_single")
        await update.message.reply_text(f"✅ Video added to *{category}*", parse_mode="Markdown")
        return
    if context.user_data.get("bulk_mode"):
        category = context.user_data.get("bulk_category")
        add_video_to_db(file_id, category)
        await update.message.reply_text(f"✅ Bulk: saved to *{category}*", parse_mode="Markdown")

async def removevideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    if len(context.args) != 2:
        return await update.message.reply_text("Usage: /removevideo <category> <index>")
    category = context.args[0]
    index = int(context.args[1])
    ok = remove_video_from_db(category, index)
    if ok:
        await update.message.reply_text(f"🗑️ Removed video {index} from *{category}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❗ Invalid category or index.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM videos")
    vids = cur.fetchone()[0]
    await update.message.reply_text(f"📊 Users: {users}\n🎞 Videos: {vids}")

async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await safe_send_log(context.bot, f"⚠️ Bot restart requested by admin {update.effective_user.id}")
    await update.message.reply_text("🔄 Restarting... (clean)")
    await context.application.shutdown()
    await context.application.stop()
    sys.exit(0)

async def fsub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /fsub <link_or_channel_id>")
    link = context.args[0]
    set_config("fsub", link)
    cur.execute("UPDATE users SET verified=0")  # reset verification
    conn.commit()
    await update.message.reply_text(f"✅ Force-sub channel set: {link}\nOld verifications cleared.")

# --- App bootstrap ---
def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # user
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(age_confirm_cb, pattern="^age_confirm$"))
    app.add_handler(CallbackQueryHandler(category_cb, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(verifynow_cb, pattern="^verifynow_"))
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
