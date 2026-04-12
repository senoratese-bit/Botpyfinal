import json
import os
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8442204653:AAHwUFaMToLVyuaUIxoQn8vd64kyCUVZytg"
ADMIN_IDS = [6706047006, 5595239245]

app = Flask(__name__)
CORS(app)

application = Application.builder().token(BOT_TOKEN).build()
bot = application.bot

BALANCE_FILE = 'balances.json'

def load_balances():
    try:
        with open(BALANCE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_balances(balances):
    with open(BALANCE_FILE, 'w') as f:
        json.dump(balances, f)

balances = load_balances()
initialized = False

async def init_app():
    global initialized
    if not initialized:
        await application.initialize()
        initialized = True

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.web_app_data:
        return
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get('type') == 'admin_deposit':
            if update.effective_user.id not in ADMIN_IDS:
                await update.message.reply_text("Access denied")
                return
            user_id = str(data.get('targetId'))
            amount = int(data.get('amount', 0))
            balances[user_id] = balances.get(user_id, 0) + amount
            save_balances(balances)
            await update.message.reply_text(f"Done: {amount} to {user_id}")
            try:
                await bot.send_message(chat_id=user_id, text=f"Balance updated: {amount}")
            except:
                pass
    except Exception as e:
        print(f"Error: {e}")

application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        async def process():
            await init_app()
            await application.process_update(update)
        asyncio.run(process())
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/api/balance/<user_id>')
def get_balance(user_id):
    return jsonify({"balance": balances.get(str(user_id), 0)})

@app.route('/api/balance/update', methods=['POST', 'OPTIONS'])
def update_balance():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        user_id = str(data.get('userId'))
        new_balance = int(data.get('balance', 0))
        balances[user_id] = new_balance
        save_balances(balances)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/admin/deposit', methods=['POST', 'OPTIONS'])
def admin_deposit():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        admin_id = data.get('adminId')
        target_id = str(data.get('targetId'))
        amount = int(data.get('amount', 0))
        if admin_id not in ADMIN_IDS:
            return jsonify({"status": "error"}), 403
        balances[target_id] = balances.get(target_id, 0) + amount
        save_balances(balances)
        async def notify():
            try:
                await bot.send_message(chat_id=target_id, text=f"Balance: {amount}")
            except:
                pass
        asyncio.run(notify())
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error"}), 500

@app.route('/')
def home():
    return "OK", 200

async def setup_webhook():
    await init_app()
    host = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if host:
        await bot.set_webhook(f"https://{host}/webhook")

if __name__ == '__main__':
    asyncio.run(setup_webhook())
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
