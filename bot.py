import os
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set in environment")

# /start command
def start(update, context):
    update.message.reply_text("Welcome to സുന്ദരി 🔞 bot")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
