# bot.py - updated
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
APP_URL = os.environ.get("APP_URL", "")  # public URL for webhook (no token in path)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 8000))

# LOG_CHANNEL can be numeric id or username/ invite link
LOG_CHANNEL = os.environ.get("LOG_CHANNEL")
if LOG_CHANNEL:
    try:
        LOG_CHANNEL = int(LOG_CHANNEL)
    except Exception:
        pass  # leave as string if not numeric

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- DB ---
DB_FILE = "bot.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

cur.execute(
    """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    username TEXT,
    first_name TEXT,
    age_confirmed INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0
)
"""
)

cur.execute(
    """
CREATE TABLE IF NOT EXISTS videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    category TEXT
)
"""
)

# store current fsub link (channel invite) in config table
cur.execute(
    """
CREATE TABLE IF NOT EXISTS config(
    key TEXT PRIMARY KEY,
    value TEXT
)
"""
)

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
        logger.warning("Failed to send log message: %s", e)


async def try_verify_user_via_chat_member(app, chat_identifier, user_id: int) -> bool:
    """
    Attempt to verify user against channel by calling get_chat_member.
    chat_identifier may be numeric id (int) or username (string like '@channelusername').
    This works only if bot has access to the channel (bot must be admin or at least member).
    Returns True if user is member/admin/creator. False otherwise.
    """
    try:
        # if numeric string, convert to int
        if isinstance(chat_identifier, str) and chat_identifier.startswith("https://"):
            # can't use invite URLs to call get_chat_member
            return False
        if isinstance(chat_identifier, str) and chat_identifier.lstrip("-").isdigit():
            chat_id = int(chat_identifier)
        else:
            chat_id = chat_identifier  # could be '@channelname' or numeric
        member = await app.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception as e:
        # most private links and invite URLs won't work here; that's expected
        logger.debug("verify check failed: %s", e)
    return False


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""

    # store user
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name),
    )
    conn.commit()

    # Log first-time starts to log channel (include username & name)
    await safe_send_log(context.bot, f"👤 New /start: {first_name} (@{username}) — id: {user_id}")

    # Attractive welcome message with emoji
    welcome = (
        "🔥 *Welcome!* 🔥\n\n"
        "Welcome to your personal adult playground — available *24/7*.\n"
        "Whether you're looking for spicy content, safely and anonymously — this is the right place.\n\n"
        "👉 *You must be 18 or older to use this bot.*\n"
        "By continuing you confirm you are of legal age."
    )

    keyboard = [
        [InlineKeyboardButton("✅ I am 18 or older", callback_data="age_confirm")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    await update.message.reply_markdown(welcome, reply_markup=InlineKeyboardMarkup(keyboard))


async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    text = (
        "ℹ️ *How this bot works*\n\n"
        "• Hit *I am 18 or older* to continue.\n"
        "• Choose a category to request channel access.\n"
        "• After requesting, use the Request->Join button then come back — the bot will check verification.\n\n"
        "Admin commands: /addvideo (reply to a video or follow prompts), /bulkadd <category>, /done, /removevideo <category> <index>, /fsub <link>, /stats, /restart"
    )
    await q.edit_message_text(text, parse_mode="Markdown")


async def age_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    # mark age confirmed
    cur.execute("UPDATE users SET age_confirmed = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    # categories with icons
    keyboard = [
        [
            InlineKeyboardButton("🏝 Mallu", callback_data="cat_Mallu"),
            InlineKeyboardButton("🇮🇳 Desi", callback_data="cat_Desi"),
        ],
        [
            InlineKeyboardButton("🔥 Trending", callback_data="cat_Trending"),
            InlineKeyboardButton("🆕 Latest", callback_data="cat_Latest"),
        ],
        [InlineKeyboardButton("💎 Premium", callback_data="cat_Premium")],
    ]
    await q.edit_message_text("✅ Age verified!\n\nSelect a category:", reply_markup=InlineKeyboardMarkup(keyboard))


async def category_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    When user selects category:
     - check force-sub config (fsub)
     - if not verified, send Request link button (link from config)
     - if verified, send first page of videos (10)
    """
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    category = q.data.split("_", 1)[1]

    fsub = get_config("fsub")  # None or a link or an id/username
    # first check DB verified flag
    cur.execute("SELECT verified FROM users WHERE user_id = ?", (user_id,))
    r = cur.fetchone()
    if r and r[0] == 1:
        verified = True
    else:
        verified = False

    # Try automatic verification if fsub is set and bot can call get_chat_member
    if not verified and fsub:
        ok = await try_verify_user_via_chat_member(context.application, fsub, user_id)
        if ok:
            verified = True
            cur.execute("UPDATE users SET verified=1 WHERE user_id = ?", (user_id,))
            conn.commit()

    if not verified:
        # show request to join button (use fsub if set; otherwise instruct admin to set)
        if fsub:
            # if fsub is an invite link or t.me link, use it directly
            link = fsub
        else:
            link = "https://t.me/yourchannel"
        kb = [
            [InlineKeyboardButton("📩 Request to Join Channel", url=link)],
            [InlineKeyboardButton("🔁 I've requested — Check again", callback_data=f"verifynow_{category}_0")],
        ]
        await q.edit_message_text(
            f"🔒 To access *{category}* videos you must request access to the channel first.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    # Verified -> send first page of videos
    all_videos = get_videos_by_category(category)
    if not all_videos:
        await q.edit_message_text(f"⚠️ No videos available for *{category}*.", parse_mode="Markdown")
        return

    page = 0
    chunk = paginate_list(all_videos, page, 10)
    media = [InputMediaVideo(media=vid) for vid in chunk]

    # send media group to user (create new message rather than editing previous text)
    await context.bot.send_message(chat_id=user_id, text=f"📂 *{category}* — Page {page+1}", parse_mode="Markdown")
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
    except Exception as e:
        # fallback: send individually
        logger.warning("send_media_group failed: %s", e)
        for m in media:
            await context.bot.send_video(chat_id=user_id, video=m.media)

    # navigation
    nav_kb = [
        [
            InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
            InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}"),
        ]
    ]
    await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))


async def verifynow_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked 'I've requested — Check again' button"""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    parts = q.data.split("_")
    # format verifynow_category_page
    category = parts[1] if len(parts) > 1 else "General"

    fsub = get_config("fsub")
    if not fsub:
        await q.edit_message_text("❗ Force-sub channel not configured yet. Ask admin to run /fsub <invite_link>.")
        return

    # attempt verification via get_chat_member (works if bot is admin in the channel and chat identifier is usable)
    ok = await try_verify_user_via_chat_member(context.application, fsub, user_id)
    if ok:
        cur.execute("UPDATE users SET verified=1 WHERE user_id = ?", (user_id,))
        conn.commit()
        await q.edit_message_text("✅ Verified! Sending videos...")
        # now trigger category flow programmatically by sending a message to user
        # call category_cb-like behavior: we will send first page
        all_videos = get_videos_by_category(category)
        if not all_videos:
            await context.bot.send_message(chat_id=user_id, text=f"No videos for {category}.")
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
        nav_kb = [
            [
                InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
                InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}"),
            ]
        ]
        await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))
    else:
        await q.answer("Still not verified. Make sure you requested and try again in a moment.", show_alert=True)


async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    _, direction, category, page_str = q.data.split("_") if q.data.count("_") == 3 else (None, None, None, None)

    # older callback_data format: next_Category_page OR prev_Category_page
    # support previous code format (next_cat_page)
    if not direction:
        # new code: maybe format "next_Category_page"
        parts = q.data.split("_")
        if len(parts) == 3:
            direction = parts[0]  # next or prev
            category = parts[1]
            page_str = parts[2]
        else:
            await q.answer("Invalid navigation data.")
            return

    page = int(page_str)

    if direction == "next":
        page += 1
    else:
        page = max(page - 1, 0)

    all_videos = get_videos_by_category(category)
    chunk = paginate_list(all_videos, page, 10)
    if not chunk:
        await q.answer("No videos on this page.", show_alert=True)
        return

    media = [InputMediaVideo(media=vid) for vid in chunk]
    # send new page header + media
    await context.bot.send_message(chat_id=user_id, text=f"📂 *{category}* — Page {page+1}", parse_mode="Markdown")
    try:
        await context.bot.send_media_group(chat_id=user_id, media=media)
    except Exception:
        for m in media:
            await context.bot.send_video(chat_id=user_id, video=m.media)

    nav_kb = [
        [
            InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{category}_{page}"),
            InlineKeyboardButton("Next ➡️", callback_data=f"next_{category}_{page}"),
        ]
    ]
    await context.bot.send_message(chat_id=user_id, text="Navigate:", reply_markup=InlineKeyboardMarkup(nav_kb))


# --- Admin flow: add / bulk add videos via replying to video messages ---
async def addvideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: start single-add flow. Reply to a video with caption/category or send after command."""
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    # Put admin into an "adding" state
    context.user_data["adding_single"] = True
    await update.message.reply_text("📤 Send or *reply* to a video now. Caption (or reply text) should be the category. Use /cancel to abort.", parse_mode="Markdown")


async def bulkadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: bulk add mode for a given category. Usage: /bulkadd <category>"""
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    if not context.args:
        return await update.message.reply_text("Usage: /bulkadd <category>")
    category = context.args[0]
    context.user_data["bulk_mode"] = True
    context.user_data["bulk_category"] = category
    await update.message.reply_text(f"📥 Bulk add started for *{category}*. Send videos (one by one). When finished send /done", parse_mode="Markdown")


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("bulk_mode"):
        context.user_data.pop("bulk_mode", None)
        context.user_data.pop("bulk_category", None)
        await update.message.reply_text("✅ Bulk add finished.")
    else:
        await update.message.reply_text("No bulk add in progress.")


async def video_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives incoming video when admin is in add or bulk mode."""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return  # ignore non-admin uploads here

    # If single-add mode
    if context.user_data.get("adding_single"):
        # Use caption or prompt for category
        caption = update.message.caption or ""
        if not caption:
            await update.message.reply_text("Send video with caption = category, or type category text before sending the video.")
            return
        category = caption.strip()
        file_id = update.message.video.file_id
        add_video_to_db(file_id, category)
        await update.message.reply_text(f"✅ Video added to *{category}*", parse_mode="Markdown")
        context.user_data.pop("adding_single", None)
        return

    # If bulk-mode
    if context.user_data.get("bulk_mode"):
        category = context.user_data.get("bulk_category")
        if not category:
            await update.message.reply_text("Bulk mode misconfigured. Cancel and restart.")
            return
        file_id = update.message.video.file_id
        add_video_to_db(file_id, category)
        await update.message.reply_text(f"✅ Bulk: saved to *{category}*", parse_mode="Markdown")
        return

    # Not in any admin add mode; maybe admin wants to add by reply to /addvideo
    # ignore otherwise
    return


async def removevideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Unauthorized.")
    if len(context.args) != 2:
        return await update.message.reply_text("Usage: /removevideo <category> <index>  (index is 0-based)")
    category = context.args[0]
    try:
        index = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("Index must be an integer (0-based).")
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
    # optional log
    await safe_send_log(context.bot, f"⚠️ Bot restart requested by admin {update.effective_user.id}")
    await update.message.reply_text("🔄 Restarting... (clean)")

    # flush DB (already committed normally). exit cleanly
    await context.application.shutdown()
    await context.application.stop()
    # exit process so host (koyeb/render) will restart
    sys.exit(0)


async def fsub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /fsub <channel_link_or_id_or_username>")
    link = context.args[0]
    set_config("fsub", link)
    # clear verified flags
    cur.execute("UPDATE users SET verified = 0")
    conn.commit()
    await update.message.reply_text(f"✅ Force-sub channel set to: {link}\nOld verifications cleared.")


# --- Application bootstrap ---
def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # user-facing
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(age_confirm_cb, pattern="^age_confirm$"))
    app.add_handler(CallbackQueryHandler(category_cb, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(verifynow_cb, pattern="^verifynow_"))
    # navigation: both old style (next_cat_page) and new style (next_cat_page)
    app.add_handler(CallbackQueryHandler(nav_cb, pattern="^(next|prev)_"))
    # admin commands
    app.add_handler(CommandHandler("addvideo", addvideo_cmd))
    app.add_handler(CommandHandler("bulkadd", bulkadd_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("removevideo", removevideo_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("fsub", fsub_cmd))

    # receive videos for admin add flows
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(user_id=ADMIN_ID), video_receiver))

    return app


def main():
    app = build_app()

    # Webhook: keep path empty and set webhook_url to APP_URL (without token)
    # This expects APP_URL to be the exact public URL that accepts POSTs from Telegram
    if not APP_URL:
        logger.error("APP_URL not set in environment; please set APP_URL to your public URL.")
        sys.exit(1)

    logger.info("Setting up webhook at %s", APP_URL)
    # run webhook (this will block)
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path="", webhook_url=APP_URL)


if __name__ == "__main__":
    main()
