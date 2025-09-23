# Sundari 🔞 Bot

# Telegram Video Bot with Health Check

A simple Telegram bot that welcomes users and sends video files on request.  
Includes a Flask health check endpoint for deployment readiness.

## Features

- `/start`: Welcomes the user.
- Type a video filename to receive it (e.g., `cat_video.mp4`).
- Health check endpoint at `/health` (port 8000).

## Setup

1. **Clone the repo**  
   ```bash
   git clone https://github.com/yourusername/your-repo-name.git
   cd your-repo-name
   ```

2. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your Telegram Bot Token**  
   - Open `bot.py`
   - Replace `'YOUR_TELEGRAM_BOT_TOKEN'` with your token from [BotFather](https://core.telegram.org/bots#botfather)

4. **Add video files**  
   - Place video files in the `videos/` directory.
   - Supported formats: `.mp4`, `.mov`, `.avi`, `.mkv`

5. **Run the bot**  
   ```bash
   python bot.py
   ```

6. **Health check**  
   - Access `http://localhost:8000/health` (or your deployment IP) for readiness status.

## Example Usage

- Start the bot in Telegram: `/start`
- Request a video: send the filename (e.g. `sample.mp4`)
- If the video exists in `/videos/`, you'll receive it.

## Deployment Notes

- The health check runs in a background thread; the bot runs in the main thread.
- Works in most environments needing a port-8000 health check (Heroku, Railway, etc).

## Directory Structure

```
.
├── bot.py
├── requirements.txt
├── .gitignore
├── README.md
└── videos/
    └── [your video files here]
```

## License

MIT
