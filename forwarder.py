import os
import re
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_GROUP_ID = os.getenv('SOURCE_GROUP_ID')
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')

# Validate config
if not all([BOT_TOKEN, SOURCE_GROUP_ID, TARGET_CHANNEL_ID]):
    logger.error("Missing required environment variables")
    exit(1)

# Signal patterns
PATTERNS = [
    re.compile(r'Boom \d+ Index (BUY|SELL) Signal', re.IGNORECASE),
    re.compile(r'Crash \d+ Index (BUY|SELL) Signal', re.IGNORECASE),
    re.compile(r'NO TRADE ALERT', re.IGNORECASE),
    re.compile(r'Volatility.*Index.*(BUY|SELL) Signal', re.IGNORECASE),
]

def is_signal(text):
    """Check if message matches any signal pattern"""
    return any(pattern.search(text) for pattern in PATTERNS) if text else False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process and forward matching messages"""
    try:
        # Only process messages from source group
        if str(update.effective_chat.id) != SOURCE_GROUP_ID:
            return
            
        message = update.message.text or update.message.caption or ''
        
        if is_signal(message):
            logger.info(f"Detected signal: {message[:50]}...")
            await forward_to_channel(message, context)
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")

async def forward_to_channel(message, context):
    """Forward message to target channel"""
    try:
        await context.bot.send_message(
            chat_id=TARGET_CHANNEL_ID,
            text=f"📢 SIGNAL ALERT 📢\n\n{message}"
        )
        logger.info("Signal forwarded successfully")
    except Exception as e:
        logger.error(f"Failed to forward message: {e}")

async def on_startup(app):
    """Notify when bot starts"""
    logger.info("Bot is now running and monitoring for signals...")
    try:
        await app.bot.send_message(
            chat_id=TARGET_CHANNEL_ID,
            text="✅ Signal forwarder bot is now active"
        )
    except Exception as e:
        logger.warning(f"Couldn't send startup notification: {e}")

def main():
    """Start the bot"""
    app = Application.builder() \
        .token(BOT_TOKEN) \
        .post_init(on_startup) \
        .build()
    
    # Add message handler
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    # Start the bot
    logger.info("Starting signal forwarder bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
