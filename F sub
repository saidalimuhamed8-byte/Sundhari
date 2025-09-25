import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

DB_FILE = "bot_data.db"

# ---------- DB Helpers ----------
def set_fsub_channel(chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM fsub_channel")
    cur.execute("INSERT INTO fsub_channel (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()

def get_fsub_channel() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM fsub_channel LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- Command Handler ----------
async def fsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ADMIN_IDS = [8301447343]
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Not authorized")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /fsub <channel_id>")
        return
    try:
        channel_id = int(context.args[0])
        set_fsub_channel(channel_id)
        await update.message.reply_text(f"✅ Force sub channel set to `{channel_id}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ---------- Show Join Button ----------
async def send_join_message(update, context):
    channel_id = get_fsub_channel()
    if not channel_id:
        return
    invite_link = f"https://t.me/c/{str(channel_id)[4:]}"  # convert private channel ID
    keyboard = [[InlineKeyboardButton("📢 Join Channel", url=invite_link)]]
    kb = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("⚠️ Please join the channel to use the bot:", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_text("⚠️ Please join the channel to use the bot:", reply_markup=kb)
