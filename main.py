import telebot
import time
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from flask import Flask, request
import threading
import logging
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
load_dotenv()

# Configuration from .env with error checking
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Error: TELEGRAM_TOKEN not found")
    exit(1)

OWNER_ID = int(os.getenv('OWNER_ID'))  # Convert to integer
MONGODB_URI = os.getenv('MONGODB_URI')

# Print confirmation
print(f"Token loaded: {TOKEN[:5]}...{TOKEN[-5:]}")
print(f"Owner ID loaded: {OWNER_ID}")

# Initialize bot with a larger timeout
bot = telebot.TeleBot(TOKEN, threaded=True)

# Initialize MongoDB
client = MongoClient(MONGODB_URI)
db = client['verifiedusers']  # Database name
verified_collection = db['users']  # Collection name

# Store authorized users with IDs
authorized_users = {OWNER_ID}

# Global variable to track bot status
bot_running = False

# Helper function to format username (normalize format)
def format_username(username):
    # Ensure @ is at the start and convert to lowercase
    username = username.lower().strip()
    username = username.replace('@', '')  # Remove any existing @
    return f"@{username}"  # Always add @ at the start

# Helper function to get verification data
def get_verified_user(username):
    formatted_username = format_username(username)

    result = verified_collection.find_one({
        "$or": [
            {"username": formatted_username},
            {"username": formatted_username.lower()},
            {"username": formatted_username.replace('_', '')},
            {"username": formatted_username.replace('_', '-')}
        ]
    })

    if result:
        # Use .get() to avoid KeyError if 'source' is missing
        result['source'] = result.get('source', 'Unknown')  
        result['service'] = result.get('service', 'Unknown') 
    
    return result

# Helper function to save verification data
def save_verified_user(username, service):
    # Store username with @ and in lowercase
    formatted_username = format_username(username)
    verified_collection.update_one(
        {"username": formatted_username},
        {"$set": {"service": service}},
        upsert=True
    )

# Helper function to remove verified user
def remove_verified_user(username):
    username = format_username(username)
    verified_collection.delete_one({"username": username})

# Check if the user is authorized
def is_authorized(user):
    return user.id in authorized_users

# Escape MarkdownV2 special characters
def escape_markdown(text):
    special_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in str(text))

@bot.message_handler(commands=['check'])
def check_verification(message):
    # Get username from command or reply
    if len(message.text.split()) > 1:
        username = message.text.split()[1].strip()
    elif message.reply_to_message and message.reply_to_message.from_user.username:
        username = message.reply_to_message.from_user.username
    else:
        bot.reply_to(message, "Usage:\n1. Reply to a message with /check\n2. Or use: /check username")
        return
    
    user_data = get_verified_user(username)
    display_name = format_username(username).upper()  # Capitalize username
    
    if user_data:
        service = user_data['service'].upper()  # Capitalize service
        response = (
            f"*🟢 {escape_markdown(display_name)} is verified for:*\n\n"
            f"{escape_markdown(service)}\n\n"
            f"*💬 We still recommend using escrow:*\n"
            f"[Scrizon](https://t\\.me/scrizon) \\| [Cupid](https://t\\.me/cupid)"
        )
    else:
        response = (
            f"*🔴 {escape_markdown(display_name)} is not verified\\!*\n\n"
            f"*⚠️ We highly recommend using escrow:*\n"
            f"[Scrizon](https://t\\.me/scrizon) \\| [Cupid](https://t\\.me/cupid)"
        )

    try:
        bot.reply_to(message, response, parse_mode='MarkdownV2', disable_web_page_preview=True)
    except Exception as e:
        # Fallback to plain text if markdown fails
        bot.reply_to(message, response.replace('*', '').replace('\\', ''), disable_web_page_preview=True)

@bot.message_handler(commands=['add'])
def add_verified(message):
    if not is_authorized(message.from_user):
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        bot.reply_to(message, "Usage: /add username - Service")
        return

    username = format_username(args[1])
    service = args[2]

    save_verified_user(username, service)
    bot.reply_to(message, f"{username} has been added as verified for {service}.")

@bot.message_handler(commands=['remove'])
def remove_verified(message):
    if not is_authorized(message.from_user):
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    if len(message.text.split()) != 2:
        bot.reply_to(message, "Usage: /remove username")
        return

    username = message.text.split()[1]
    if get_verified_user(username):
        remove_verified_user(username)
        bot.reply_to(message, f"{username} has been removed from verified users.")
    else:
        bot.reply_to(message, f"{username} is not a verified user.")

@bot.message_handler(commands=['auth'])
def authorize_user(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "Only the owner can authorize users.")
        return

    if len(message.text.split()) != 2:
        bot.reply_to(message, "Usage: /auth <user_id>")
        return

    try:
        user_id = int(message.text.split()[1])
        authorized_users.add(user_id)
        bot.reply_to(message, f"User {user_id} has been authorized.")
    except ValueError:
        bot.reply_to(message, "Please provide a valid user ID")

# Add these new routes
@app.route('/')
def home():
    return f"Bot is {'running' if bot_running else 'stopped'}"

@app.route('/health')
def health():
    status = "running" if bot_running else "stopped"
    return f"OK - Bot is {status}", 200

# Add a simple command to test bot
@bot.message_handler(commands=['ping'])
def ping_command(message):
    bot.reply_to(message, "Pong! Bot is working!")

def bot_polling():
    global bot_running
    while True:
        try:
            logger.info("Bot polling started...")
            bot_running = True
            bot.polling(timeout=60, long_polling_timeout=60, non_stop=True)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            bot_running = False
            time.sleep(10)
            continue
        finally:
            bot_running = False

# Keep-alive function with bot status check
def keep_alive():
    while True:
        try:
            # Check if bot is running
            if not bot_running:
                logger.warning("Bot not running, restarting polling...")
                # Restart polling thread
                polling_thread = threading.Thread(target=bot_polling)
                polling_thread.daemon = True
                polling_thread.start()
            
            logger.info("Bot status: " + ("running" if bot_running else "stopped"))
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(30)  # Check every 30 seconds

if __name__ == '__main__':
    # Start bot polling in a separate thread
    polling_thread = threading.Thread(target=bot_polling)
    polling_thread.daemon = True
    polling_thread.start()
    
    # Start keep-alive in a separate thread
    keep_alive_thread = threading.Thread(target=keep_alive)
    keep_alive_thread.daemon = True
    keep_alive_thread.start()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
