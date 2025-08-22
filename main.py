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
# This part keeps the web service "alive" for hosting platforms.
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for the hosting platform."""
    return "VIP RpmShare Bot is alive and running!", 200

def run_flask_app():
    """Runs the Flask app on the port specified by the environment."""
    # Render and Koyeb provide the PORT environment variable.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Telegram Bot Code ---
# (The bot logic remains mostly the same, just structured to run with Flask)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VIPRpmShareBot:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if not self.telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        self.init_database()
        # Create an asyncio event loop for the bot to run in
        self.loop = asyncio.new_event_loop()

    def init_database(self):
        # Database functions remain the same
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        api_key TEXT NOT NULL,
                        upload_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:
                cursor.execute("PRAGMA table_info(users)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'upload_count' not in columns:
                    cursor.execute('ALTER TABLE users ADD COLUMN upload_count INTEGER DEFAULT 0')
                if 'created_at' not in columns:
                    cursor.execute('ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            conn.commit()
            conn.close()
            logger.info("VIP Database system initialized")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    # All other bot methods (get_user_api_key, save_user_api_key, etc.) remain here...
    def get_user_api_key(self, user_id: int) -> Optional[str]:
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT api_key FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error retrieving user credentials: {e}")
            return None
    
    def save_user_api_key(self, user_id: int, api_key: str) -> bool:
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO users (user_id, api_key, upload_count) VALUES (?, ?, COALESCE((SELECT upload_count FROM users WHERE user_id = ?), 0))', (user_id, api_key, user_id))
            conn.commit()
            conn.close()
            logger.info(f"VIP credentials updated for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving user credentials: {e}")
            return False
    
    def increment_upload_count(self, user_id: int):
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET upload_count = upload_count + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating upload statistics: {e}")
    
    def get_upload_stats(self, user_id: int) -> int:
        try:
            conn = sqlite3.connect('user_data.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT upload_count FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error retrieving upload statistics: {e}")
            return 0

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        welcome_message = """🔥 **PREMIUM VIDEO UPLOAD SERVICE** 🔥
Welcome to the **VIP RpmShare Upload Bot** - Your professional video hosting solution.
🚀 **FEATURES:**
• High-speed video uploads to RpmShare
• Secure API key management
• Professional upload confirmation
• Upload statistics tracking
🔑 **SETUP REQUIRED:**
Use `/setapi YOUR_RPMSHARE_KEY` to configure your account
📋 **AVAILABLE COMMANDS:**
• `/setapi <key>` - Configure your RpmShare API key
• `/stats` - View your upload statistics
⚡ **READY TO UPLOAD?**
Simply send any video file after setting your API key."""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def setapi(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("⚠️ **Usage:** `/setapi YOUR_RPMSHARE_API_KEY`", parse_mode='Markdown')
            return
        api_key = ' '.join(context.args).strip()
        if self.save_user_api_key(user_id, api_key):
            await update.message.reply_text("✅ **VIP ACCOUNT CONFIGURED**", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ **SYSTEM ERROR**", parse_mode='Markdown')

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        api_key = self.get_user_api_key(user_id)
        if not api_key:
            await update.message.reply_text("🔒 **AUTHENTICATION REQUIRED**\n\nUse `/setapi` first.", parse_mode='Markdown')
            return
        upload_count = self.get_upload_stats(user_id)
        masked_key = "*" * (len(api_key) - 6) + api_key[-6:]
        stats_message = f"""📊 **VIP ACCOUNT STATISTICS**
🔑 **API Key:** `{masked_key}`
📈 **Total Uploads:** {upload_count}
⚡ **Status:** Premium Active"""
        await update.message.reply_text(stats_message, parse_mode='Markdown')
    
    async def get_upload_server(self, api_key: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f'https://rpmshare.com/api/upload/server?key={api_key}', timeout=45) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data.get('result')
            except Exception as e:
                logger.error(f"Server acquisition failed: {e}")
        return None

    async def upload_to_rpmshare(self, file_path: str, upload_server: str, api_key: str) -> Optional[dict]:
        async with aiohttp.ClientSession() as session:
            try:
                data = aiohttp.FormData()
                data.add_field('key', api_key)
                data.add_field('file', open(file_path, 'rb'))
                async with session.post(upload_server, data=data, timeout=900) as response:
                    response.raise_for_status()
                    return await response.json()
            except Exception as e:
                logger.error(f"Upload failed: {e}")
        return None

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_api_key = self.get_user_api_key(user_id)
        if not user_api_key:
            await update.message.reply_text("🔒 **ACCESS DENIED**\n\nUse `/setapi`", parse_mode='Markdown')
            return
        
        status_message = await update.message.reply_text("⚡ **UPLOAD INITIATED**", parse_mode='Markdown')
        video = update.message.video or update.message.document
        temp_file_path = None
        
        try:
            file_size_mb = video.file_size / (1024 * 1024) if video.file_size else 0
            file = await context.bot.get_file(video.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                temp_file_path = temp_file.name
            
            await status_message.edit_text(f"📥 **DOWNLOADING...** ({file_size_mb:.1f}MB)", parse_mode='Markdown')
            await file.download_to_drive(temp_file_path)

            await status_message.edit_text(f"🚀 **UPLOADING...** ({file_size_mb:.1f}MB)", parse_mode='Markdown')
            
            upload_server = await self.get_upload_server(user_api_key)
            if not upload_server:
                await status_message.edit_text("❌ **SERVER ACCESS FAILED**", parse_mode='Markdown')
                return

            upload_response = await self.upload_to_rpmshare(temp_file_path, upload_server, user_api_key)
            if not upload_response:
                await status_message.edit_text("❌ **UPLOAD FAILED**", parse_mode='Markdown')
                return
            
            filecode = upload_response.get('result', [{}])[0].get('filecode')
            if filecode:
                self.increment_upload_count(user_id)
                total_uploads = self.get_upload_stats(user_id)
                await status_message.edit_text(f"✅ **UPLOAD COMPLETED**\n\nFile Code: `{filecode}`", parse_mode='Markdown')
            else:
                await status_message.edit_text(f"❌ **ERROR:** {upload_response.get('msg', 'Unknown')}", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Critical upload error: {e}")
            await status_message.edit_text("❌ **SYSTEM ERROR**", parse_mode='Markdown')
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def run_bot(self):
        """Sets up and runs the bot in the asyncio event loop."""
        asyncio.set_event_loop(self.loop)
        application = Application.builder().token(self.telegram_token).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("setapi", self.setapi))
        application.add_handler(CommandHandler("stats", self.stats))
        application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, self.handle_video))
        
        logger.info("🔥 VIP RpmShare Upload Service ACTIVATED 🔥")
        self.loop.run_until_complete(application.run_polling(allowed_updates=Update.ALL_TYPES))

# --- Main Execution ---
if __name__ == '__main__':
    try:
        bot = VIPRpmShareBot()

        # Run the bot in a separate thread
        bot_thread = Thread(target=bot.run_bot)
        bot_thread.start()

        # Run the Flask app in the main thread
        run_flask_app()

    except Exception as e:
        logger.critical(f"Failed to start application: {e}")
