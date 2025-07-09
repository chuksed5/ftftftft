import os
import re
import asyncio
import logging
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import threading
import time

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed. Using system environment variables only.")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for health checks
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
start_time = time.time()
bot_running = False

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

# Flask routes
@app.route('/')
def home():
    uptime = time.time() - start_time
    return jsonify({
        'status': 'Bot is running!',
        'uptime': uptime,
        'timestamp': datetime.now().isoformat(),
        'bot_info': {
            'polling': bot_running,
            'source_group': SOURCE_GROUP_ID,
            'target_channel': TARGET_CHANNEL_ID
        }
    })

@app.route('/health')
def health():
    uptime = time.time() - start_time
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_running,
        'uptime': uptime
    })

@app.route('/restart', methods=['GET', 'POST'])
def restart():
    logger.info('🔄 Manual restart requested')
    return jsonify({'message': 'Bot restart initiated'})

def contains_signal(text):
    """Check if message contains trading signals"""
    if not text:
        return False
    return any(pattern.search(text) for pattern in SIGNAL_PATTERNS)

async def forward_signal(message_text, context: ContextTypes.DEFAULT_TYPE):
    """Forward trading signal to target channel"""
    try:
        formatted_message = (
            f"🔥 TRADING SIGNAL 🔥\n\n"
            f"{message_text}\n\n"
            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
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
        if str(update.effective_chat.id) != SOURCE_GROUP_ID:
            return
        
        message_text = update.message.text or update.message.caption or ''
        
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
            text='🤖 Bot deployed and running!'
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
    global bot_running
    
    while True:  # Outer restart loop
        try:
            application = None
            logger.info('🔧 Initializing bot...')
            
            # Create the Application
            application = Application.builder().token(BOT_TOKEN).build()
            
            # Add handlers
            application.add_handler(MessageHandler(filters.ALL, message_handler))
            application.add_error_handler(error_handler)
            
            await application.initialize()
            await application.start()
            
            # Start background tasks
            asyncio.create_task(heartbeat(application))
            asyncio.create_task(memory_cleaner())
            
            bot_info = await application.bot.get_me()
            logger.info(f'🤖 Bot @{bot_info.username} started successfully')
            
            # Main running loop
            bot_running = True
            while bot_running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info('Shutdown requested')
            break
        except Exception as e:
            logger.error(f'Main loop error: {e}', exc_info=True)
            # Wait before restarting
            await asyncio.sleep(10)
        finally:
            bot_running = False
            if application:
                try:
                    await application.stop()
                    await application.shutdown()
                except Exception as e:
                    logger.error(f'Shutdown error: {e}')

def run_bot():
    """Run the bot in a separate thread with its own event loop"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('\n🛑 Bot shutting down...')
    except Exception as e:
        logger.error(f'❌ Bot crashed: {e}')
    finally:
        global bot_running
        bot_running = False

if __name__ == '__main__':
    # Start Flask server in daemon thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info(f'🌐 Server running on port {PORT}')
    time.sleep(2)  # Give Flask time to start
    
    # Run the telegram bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=False)
    bot_thread.start()
    
    try:
        # Keep the main thread alive
        bot_thread.join()
    except KeyboardInterrupt:
        logger.info('\n🛑 Shutting down...')
        bot_running = False
