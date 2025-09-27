import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Environment Variables ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
APP_URL = os.environ["APP_URL"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 8000))

LOG_CHANNEL = os.environ.get("LOG_CHANNEL")
try:
    LOG_CHANNEL = int(LOG_CHANNEL)
except:
    LOG_CHANNEL = None

# Dynamic channel link
CHANNEL_LINK = None  # Initially None

# --- Database Setup ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    age_confirmed INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT UNIQUE,
    category TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS channel_requests(
    user_id INTEGER UNIQUE
)
""")
conn.commit()

# --- Helper Functions ---
async def check_channel_membership(user_id):
    """Check if user already requested access (we can’t verify private channel membership via API)."""
    if not CHANNEL_LINK:
        return True  # Skip check if no channel set

    cursor.execute("SELECT 1 FROM channel_requests WHERE user_id=?", (user_id,))
    return bool(cursor.fetchone())

def paginate_videos(videos, page=0, page_size=10):
    start = page * page_size
    end = start + page_size
    return videos[start:end]

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    conn.commit()

    if LOG_CHANNEL:
        try:
            await context.bot.send_message(LOG_CHANNEL, f"User started bot: {user_id}")
        except:
            pass

    keyboard = [[InlineKeyboardButton("I am 18 or older", callback_data="confirm_age")]]
    text = (
        "Welcome to your personal adult playground — available 24/7.\n\n"
        "Whether you're looking for spicy content safely and anonymously this is the right place.\n\n"
        "👉 Must be 18 or older to use. By starting the bot, you confirm you're of legal age."
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # --- Age Confirmation ---
    if query.data == "confirm_age":
        cursor.execute("UPDATE users SET age_confirmed=1 WHERE user_id=?", (user_id,))
        conn.commit()

        keyboard = [
            [InlineKeyboardButton("Mallu", callback_data="category_Mallu")],
            [InlineKeyboardButton("Desi", callback_data="category_Desi")],
            [InlineKeyboardButton("Trending", callback_data="category_Trending")],
            [InlineKeyboardButton("Latest", callback_data="category_Latest")],
            [InlineKeyboardButton("Premium", callback_data="category_Premium")],
        ]
        await query.edit_message_text("Select the category:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Category Selection ---
    if query.data.startswith("category_"):
        category = query.data.split("_")[1]
        joined = await check_channel_membership(user_id)

        if not joined:
            # Record request
            cursor.execute("INSERT OR IGNORE INTO channel_requests(user_id) VALUES(?)", (user_id,))
            conn.commit()

            keyboard = [[InlineKeyboardButton("Request to Join Channel", url=CHANNEL_LINK)]]
            await query.edit_message_text(
                f"To access {category} videos, please request to join the private channel first.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Send videos
        cursor.execute("SELECT file_id FROM videos WHERE category=?", (category,))
        all_videos = [v[0] for v in cursor.fetchall()]
        if not all_videos:
            await query.edit_message_text(f"No videos available for {category}.")
            return

        page = 0
        videos = paginate_videos(all_videos, page)
        media_group = [InputMediaVideo(media=v) for v in videos]

        await query.edit_message_media(media_group[0])
        if len(media_group) > 1:
            await context.bot.send_media_group(chat_id=user_id, media=media_group[1:])

        keyboard = [
            [
                InlineKeyboardButton("Previous", callback_data=f"prev_{category}_{page}"),
                InlineKeyboardButton("Next", callback_data=f"next_{category}_{page}")
            ]
        ]
        await context.bot.send_message(chat_id=user_id, text="Navigation:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Pagination ---
    if query.data.startswith("next_") or query.data.startswith("prev_"):
        _, category, page = query.data.split("_")
        page = int(page)
        cursor.execute("SELECT file_id FROM videos WHERE category=?", (category,))
        all_videos = [v[0] for v in cursor.fetchall()]

        if query.data.startswith("next_"):
            page += 1
        else:
            page = max(page - 1, 0)

        videos = paginate_videos(all_videos, page)
        if not videos:
            await query.answer("No more videos.")
            return

        media_group = [InputMediaVideo(media=v) for v in videos]
        await query.edit_message_media(media_group[0])
        if len(media_group) > 1:
            await context.bot.send_media_group(chat_id=user_id, media=media_group[1:])

        keyboard = [
            [
                InlineKeyboardButton("Previous", callback_data=f"prev_{category}_{page}"),
                InlineKeyboardButton("Next", callback_data=f"next_{category}_{page}")
            ]
        ]
        await context.bot.send_message(chat_id=user_id, text="Navigation:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Admin Commands ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM videos")
    total_videos = cursor.fetchone()[0]
    await update.message.reply_text(f"Users: {total_users}\nVideos: {total_videos}")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Restarting bot...")
    os._exit(1)

# --- Dynamic Channel Link ---
async def fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHANNEL_LINK
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /fsub <channel_link>")
        return

    try:
        CHANNEL_LINK = context.args[0]
        cursor.execute("DELETE FROM channel_requests")
        conn.commit()
        await update.message.reply_text(f"Channel updated successfully to {CHANNEL_LINK}. All previous requests cleared.")
    except Exception as e:
        await update.message.reply_text(f"Failed to set channel: {e}")

# --- Main ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CommandHandler("fsub", fsub))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="",
        webhook_url=APP_URL,
    )

if __name__ == "__main__":
    main()
