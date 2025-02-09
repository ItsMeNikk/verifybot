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

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# Initialize MongoDB
client = MongoClient(MONGODB_URI)
db = client['verifiedusers']  # Database name
verified_collection = db['users']  # Collection name

# Store authorized users with IDs
authorized_users = {OWNER_ID}

# Helper function to get verification data
def get_verified_user(username):
    # Remove @ if present
    username = username.replace('@', '')
    return verified_collection.find_one({"username": username.lower()})

# Helper function to save verification data
def save_verified_user(username, service):
    # Remove @ if present and convert to lowercase for consistency
    username = username.replace('@', '').lower()
    verified_collection.update_one(
        {"username": username},
        {"$set": {"service": service}},
        upsert=True
    )

# Helper function to remove verified user
def remove_verified_user(username):
    username = username.replace('@', '').lower()
    verified_collection.delete_one({"username": username})

# Check if the user is authorized
def is_authorized(user):
    return user.id in authorized_users

# Escape MarkdownV2 special characters
def escape_markdown(text):
    special_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in text)

@bot.message_handler(commands=['check'])
def check_verification(message):
    # If replying to a message
    if message.reply_to_message and message.reply_to_message.from_user.username:
        username = message.reply_to_message.from_user.username
    # If username is provided in command
    elif len(message.text.split()) == 2:
        username = message.text.split()[1]
    else:
        bot.reply_to(message, "Usage:\n1. Reply to a message with /check\n2. Or use: /check @username")
        return

    # Remove @ if present
    username = username.replace('@', '')
    user_data = get_verified_user(username)
    
    if user_data:
        service = escape_markdown(user_data['service'])
        response = f"*🟢 {escape_markdown(username)} IS VERIFIED FOR:*\n\n>`{service}`\n\n*WE STILL RECOMMEND USING ESCROW: Scrizon / Cupid*"
    else:
        response = f"*🔴 {escape_markdown(username)} IS NOT VERIFIED*\n\n*WE HIGHLY RECOMMEND USING ESCROW: Scrizon / Cupid*"

    bot.reply_to(message, response, parse_mode='MarkdownV2')

@bot.message_handler(commands=['add'])
def add_verified(message):
    if not is_authorized(message.from_user):
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        bot.reply_to(message, "Usage: /add @username - Service")
        return

    username = args[1]
    service = args[2]

    # Remove @ if present
    username = username.replace('@', '')
    save_verified_user(username, service)
    bot.reply_to(message, f"@{username} has been added as verified for {service}.")

@bot.message_handler(commands=['remove'])
def remove_verified(message):
    if not is_authorized(message.from_user):
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    if len(message.text.split()) != 2:
        bot.reply_to(message, "Usage: /remove @username")
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
    return "Bot is running!"

@app.route('/ping')
def ping():
    return "Pong! Bot is alive"

# Keep-alive function
def keep_alive():
    while True:
        try:
            # Send a request to your app URL every 5 minutes
            url = "https://your-render-app-name.onrender.com"
            requests.get(url)
            logger.info("Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(300)  # 5 minutes

def bot_polling():
    while True:
        try:
            logger.info("Bot polling started...")
            bot.polling(timeout=20, none_stop=True)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            time.sleep(15)

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
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
