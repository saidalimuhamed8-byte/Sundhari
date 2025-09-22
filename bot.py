# This script combines a Flask web server with a Telegram bot
# to handle webhooks, which is the recommended method for
# deploying a bot on a platform like Koyeb.

import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Set up basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables from a .env file (for local testing)
# Koyeb will use its own environment variables, so this is for local dev.
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    # Raise an error if the token is not found. Koyeb requires this
    # to be set as a secret environment variable.
    raise RuntimeError("❌ BOT_TOKEN environment variable not set.")

# Initialize the Flask web application
app = Flask(__name__)

# Create the bot application instance.
# This uses the modern python-telegram-bot syntax (v20+).
application = Application.builder().token(BOT_TOKEN).build()

# Define the async handler for the /start command.
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the command /start is issued."""
    logger.info("Received /start command from user: %s", update.message.from_user.id)
    await update.message.reply_text("Welcome to സുന്ദരി 🔞 bot")

# Register the command handler with the bot application.
application.add_handler(CommandHandler("start", start_command))

# This is the webhook route. It's the URL that Telegram sends updates to.
# We're using a dynamic path based on the bot token for security.
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    """Handle incoming Telegram updates via webhook."""
    # Parse the JSON payload from the Telegram request.
    update = Update.de_json(request.get_json(force=True), application.bot)
    # The application processes the update directly.
    application.process_update(update)
    logger.info("Received and processed an update from Telegram.")
    return "ok"

# This is the root route for health checks.
# Koyeb's health checks will send requests to this URL to ensure the service is running.
@app.route("/")
def index_handler():
    """A simple health check endpoint."""
    return "Bot is running!"

if __name__ == "__main__":
    # Get the port from the environment variable provided by Koyeb.
    PORT = int(os.environ.get("PORT", 8080))
    
    # Run the Flask web server to handle incoming webhooks and health checks.
    logger.info("Starting Flask server on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
