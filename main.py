import telebot
import time
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from flask import Flask, request
import threading

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
load_dotenv()

# Configuration from .env with error checking
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    print("Error: TELEGRAM_TOKEN not found in .env file")
    print("Current working directory:", os.getcwd())
    exit(1)

OWNER_USERNAME = os.getenv('OWNER_USERNAME')
MONGODB_URI = os.getenv('MONGODB_URI')

# Print confirmation
print(f"Token loaded: {TOKEN[:5]}...{TOKEN[-5:]}")
print(f"Owner username loaded: {OWNER_USERNAME}")

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# Initialize MongoDB
client = MongoClient(MONGODB_URI)
db = client['verifiedusers']  # Database name
verified_collection = db['users']  # Collection name

# Store authorized users
authorized_users = {OWNER_USERNAME}

# Helper function to get verification data
def get_verified_user(username):
    return verified_collection.find_one({"username": username})

# Helper function to save verification data
def save_verified_user(username, service):
    verified_collection.update_one(
        {"username": username},
        {"$set": {"service": service}},
        upsert=True
    )

# Helper function to remove verified user
def remove_verified_user(username):
    verified_collection.delete_one({"username": username})

# Check if the user is authorized
def is_authorized(user):
    return user.username in authorized_users

# Escape MarkdownV2 special characters
def escape_markdown(text):
    special_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in text)

@bot.message_handler(commands=['check'])
def check_verification(message):
    if len(message.text.split()) != 2:
        bot.reply_to(message, "Usage: /check @username")
        return

    username = message.text.split()[1]
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

    username, service = args[1], args[2]
    save_verified_user(username, service)
    bot.reply_to(message, f"{username} has been added as verified for {service}.")

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
    if message.from_user.username != OWNER_USERNAME:
        bot.reply_to(message, "Only the owner can authorize users.")
        return

    if len(message.text.split()) != 2:
        bot.reply_to(message, "Usage: /auth @username")
        return

    username = message.text.split()[1].lstrip('@')
    authorized_users.add(username)
    bot.reply_to(message, f"{username} has been authorized.")

# Add these new routes
@app.route('/')
def home():
    return "Bot is running!"

def bot_polling():
    while True:
        try:
            print("Starting bot polling...")
            bot.polling(timeout=20)
        except Exception as e:
            print(f"Bot polling error: {e}")
            time.sleep(15)

if __name__ == '__main__':
    # Start bot polling in a separate thread
    polling_thread = threading.Thread(target=bot_polling)
    polling_thread.daemon = True  # This makes the thread exit when main program exits
    polling_thread.start()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
