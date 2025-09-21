import os
from telegram.ext import Application, CommandHandler

# Get token from environment
BOT_TOKEN = os.getenv("8330389043:AAH3NF1PFazQd_1dhRVtePyTYJ49dPj4Lt")

# Start command
async def start(update, context):
    await update.message.reply_text("Welcome to സുന്ദരി 🔞 bot")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
