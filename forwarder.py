import os
import re
import asyncio
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import threading
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for health checks (equivalent to Express server)
app = Flask(__name__)
PORT = int(os.environ.get('PORT', 3000))

# Environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
SOURCE_GROUP_ID = os.environ.get('SOURCE_GROUP_ID')
TARGET_CHANNEL_ID = os.environ.get('TARGET_CHANNEL_ID')

# Validation
if not all([BOT_TOKEN, SOURCE_GROUP_ID, TARGET_CHANNEL_ID]):
    logger.error('❌ Missing required environment variables:')
    logger.error(f'BOT_TOKEN: {bool(BOT_TOKEN)}')
    logger.error(f'SOURCE_GROUP_ID: {bool(SOURCE_GROUP_ID)}')
    logger.error(f'TARGET_CHANNEL_ID: {bool(TARGET_CHANNEL_ID)}')
    exit(1)

# Global variables
telegram_app = None
start_time = time.time()

# Signal patterns to match
SIGNAL_PATTERNS = [
    re.compile(r'Boom 1000 Index BUY Signal', re.IGNORECASE),
    re.compile(r'Crash 1000 Index BUY Signal', re.IGNORECASE),
    re.compile(r'Boom 1000 Index SELL Signal', re.IGNORECASE),
    re.compile(r'Crash 1000 Index SELL Signal', re.IGNORECASE),
    re.compile(r'Boom 500 Index (BUY|SELL) Signal', re.IGNORECASE),
    re.compile(r'NO TRADE ALERT', re.IGNORECASE),
    re.compile(r'Volatility.*Index.*(BUY|SELL) Signal', re.IGNORECASE),
]

# Flask routes for health checking
@app.route('/')
def home():
    uptime = time.time() - start_time
    return jsonify({
        'status': 'Bot is running!',
        'uptime': uptime,
        'timestamp': datetime.now().isoformat(),
        'bot_info': {
            'polling': telegram_app is not None and telegram_app.running,
            'source_group': SOURCE_GROUP_ID,
            'target_channel': TARGET_CHANNEL_ID
        }
    })

@app.route('/health')
def health():
    uptime = time.time() - start_time
    return jsonify({
        'status': 'healthy',
        'bot_running': telegram_app is not None and telegram_app.running,
        'uptime': uptime
    })

@app.route('/restart', methods=['GET', 'POST'])
def restart():
    logger.info('🔄 Manual restart requested')
    # In production, you might want to implement actual restart logic
    return jsonify({'message': 'Bot restart initiated'})

def contains_signal(text):
    """Check if message contains trading signals"""
    if not text:
        return False
    return any(pattern.search(text) for pattern in SIGNAL_PATTERNS)

async def forward_signal(message_text, context: ContextTypes.DEFAULT_TYPE):
    """Forward trading signal to target channel"""
    try:
        # Create formatted message
        formatted_message = (
            f"🔥 TRADING SIGNAL 🔥\n\n"
            f"{message_text}\n\n"
            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send to channel
        await context.bot.send_message(
            chat_id=TARGET_CHANNEL_ID,
            text=formatted_message
        )
        
        logger.info(f'✅ Signal forwarded successfully: {message_text[:50]}...')
    except Exception as error:
        logger.error(f'❌ Error forwarding signal: {error}')

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    try:
        # Only process messages from the source group
        if str(update.effective_chat.id) != SOURCE_GROUP_ID:
            return
        
        message_text = update.message.text or update.message.caption or ''
        
        # Check if message contains trading signals
        if contains_signal(message_text):
            logger.info(f'🎯 Trading signal detected: {message_text[:100]}...')
            await forward_signal(message_text, context)
            
    except Exception as error:
        logger.error(f'❌ Error processing message: {error}')

async def test_channel_access(application):
    """Test function to verify bot can access channel"""
    try:
        await application.bot.send_message(
            chat_id=TARGET_CHANNEL_ID,
            text='🤖 Bot deployed and running on Render!'
        )
        logger.info('✅ Bot can access the target channel!')
    except Exception as error:
        logger.error(f'❌ Bot cannot access channel: {error}')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f'Update {update} caused error {context.error}')

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

async def main():
    """Main function to run the bot"""
    global telegram_app
    
    logger.info('🔧 Initializing bot...')
    
    # Create the Application
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    telegram_app.add_handler(MessageHandler(filters.ALL, message_handler))
    telegram_app.add_error_handler(error_handler)
    
    try:
        # Get bot info
        bot_info = await telegram_app.bot.get_me()
        logger.info('🤖 Trading Signal Bot started!')
        logger.info(f'📋 Bot Info: @{bot_info.username}')
        logger.info(f'👥 Monitoring group: {SOURCE_GROUP_ID}')
        logger.info(f'📢 Forwarding to channel: {TARGET_CHANNEL_ID}')
        
        # Test channel access after a delay
        asyncio.create_task(asyncio.sleep(3))
        asyncio.create_task(test_channel_access(telegram_app))
        
        # Start the bot
        logger.info('🚀 Starting bot polling...')
        await telegram_app.run_polling(
            poll_interval=0.3,
            timeout=10,
            bootstrap_retries=5,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
        
    except Exception as error:
        logger.error(f'❌ Failed to start bot: {error}')
        raise

if __name__ == '__main__':
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info(f'🌐 Server running on port {PORT}')
    
    # Wait a bit for Flask to start
    time.sleep(2)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('\n🛑 Bot shutting down...')
    except Exception as e:
        logger.error(f'❌ Bot crashed: {e}')
        exit(1)