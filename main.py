import os
import logging
import sqlite3
import tempfile
import aiohttp
import asyncio
from threading import Thread
from flask import Flask
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Flask Web Server Setup ---
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for the hosting platform."""
    return "VIP RpmShare Bot is alive and running!", 200

def run_flask_app():
    """Runs the Flask app on the port specified by the environment."""
    port = int(os.environ.get("PORT", 8080))
    # Use 'waitress' for production instead of Flask's dev server
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)

# --- Telegram Bot Code ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Set higher logging level for HTTPX and other libraries to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class VIPRpmShareBot:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.telegram_token:
            logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not found!")
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        self.init_database()

    def init_database(self):
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    api_key TEXT NOT NULL,
                    upload_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("Database system initialized successfully.")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    # ... (All other database and helper methods remain the same)
    def get_user_api_key(self, user_id: int) -> Optional[str]:
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT api_key FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error retrieving API key for user {user_id}: {e}")
            return None
    
    def save_user_api_key(self, user_id: int, api_key: str) -> bool:
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO users (user_id, api_key, upload_count) VALUES (?, ?, COALESCE((SELECT upload_count FROM users WHERE user_id = ?), 0))', (user_id, api_key, user_id))
            conn.commit()
            conn.close()
            logger.info(f"API key updated for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving API key for user {user_id}: {e}")
            return False

    # All async handlers with added logging
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info(f"Received /start command from user {update.effective_user.id}")
        welcome_message = "🔥 **PREMIUM VIDEO UPLOAD SERVICE** 🔥\nWelcome to the **VIP RpmShare Upload Bot**."
        try:
            await update.message.reply_text(welcome_message, parse_mode='Markdown')
            logger.info(f"Successfully sent welcome message to user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Failed to send welcome message to user {update.effective_user.id}: {e}")

    async def setapi(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info(f"Received /setapi command from user {update.effective_user.id}")
        user_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("⚠️ **Usage:** `/setapi YOUR_RPMSHARE_API_KEY`", parse_mode='Markdown')
            return
        api_key = ' '.join(context.args).strip()
        if self.save_user_api_key(user_id, api_key):
            await update.message.reply_text("✅ **VIP ACCOUNT CONFIGURED**", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ **SYSTEM ERROR**", parse_mode='Markdown')

    # ... (Other handlers like stats and handle_video should also have logging, but let's fix start first)
    
    async def run_bot_async(self):
        """The main async function to run the bot."""
        logger.info("Building bot application...")
        application = Application.builder().token(self.telegram_token).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("setapi", self.setapi))
        # Add other handlers here
        
        logger.info("Bot application built. Starting polling...")
        try:
            await application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.critical(f"Bot polling crashed with error: {e}", exc_info=True)

    def start_bot_thread(self):
        """Starts the bot in a new thread."""
        logger.info("Starting bot in a background thread.")
        asyncio.run(self.run_bot_async())

# --- Main Execution ---
if __name__ == '__main__':
    logger.info("Application starting up...")
    try:
        bot_instance = VIPRpmShareBot()

        # Run the bot in a separate thread
        bot_thread = Thread(target=bot_instance.start_bot_thread, daemon=True)
        bot_thread.start()
        logger.info("Bot thread has been started.")

        # Run the Flask app in the main thread
        logger.info("Starting Flask web server...")
        run_flask_app()

    except Exception as e:
        logger.critical(f"Failed to start application: {e}", exc_info=True)
