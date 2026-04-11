import json
import os
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8442204653:AAHwUFaMToLVyuaUIxoQn8vd64kyCUVZytg"
ADMIN_ID = 6706047006

app = Flask(__name__)
CORS(app)  # ← РАЗРЕШАЕМ ЗАПРОСЫ С ДРУГИХ ДОМЕНОВ

application = Application.builder().token(BOT_TOKEN).build()
bot = application.bot

# ========== ЗАГРУЗКА И СОХРАНЕНИЕ БАЛАНСОВ ==========
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
# ==================================================

initialized = False

async def init_app():
    global initialized
    if not initialized:
        await application.initialize()
        initialized = True
        print("✅ Application initialized")

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.web_app_data:
        return
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get('type') == 'admin_deposit':
            if update.effective_user.id != ADMIN_ID:
                await update.message.reply_text("⛔ Доступ запрещён")
                return
            user_id = str(data.get('targetId'))
            amount = int(data.get('amount', 0))
            balances[user_id] = balances.get(user_id, 0) + amount
            save_balances(balances)
            await update.message.reply_text(f"✅ Начислено {amount} ₽ пользователю {user_id}")
            try:
                await bot.send_message(chat_id=user_id, text=f"🎉 Ваш баланс пополнен на {amount} ₽!")
            except:
                pass
    except Exception as e:
        print(f"Ошибка WebAppData: {e}")

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
    balance = balances.get(str(user_id), 0)
    return jsonify({"balance": balance})

@app.route('/api/balance/<user_id>/set/<int:amount>')
def set_balance(user_id, amount):
    balances[str(user_id)] = amount
    save_balances(balances)
    return jsonify({"status": "ok", "balance": amount})

@app.route('/api/admin/deposit', methods=['POST', 'OPTIONS'])
def admin_deposit():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        admin_id = data.get('adminId')
        target_id = str(data.get('targetId'))
        amount = int(data.get('amount', 0))
        
        if admin_id != ADMIN_ID:
            return jsonify({"status": "error", "error": "Access denied"}), 403
        
        balances[target_id] = balances.get(target_id, 0) + amount
        save_balances(balances)
        
        async def notify():
            try:
                if amount > 0:
                    await bot.send_message(chat_id=target_id, text=f"🎉 Ваш баланс пополнен на {amount} ₽!")
                else:
                    await bot.send_message(chat_id=target_id, text=f"💸 С вашего баланса снято {-amount} ₽.")
            except:
                pass
        asyncio.run(notify())
        
        return jsonify({"status": "ok", "balance": balances[target_id]})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/')
def home():
    return "✅ Bot is running", 200

async def setup_webhook():
    await init_app()
    host = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if host:
        await bot.set_webhook(f"https://{host}/webhook")
        print(f"✅ Webhook set to https://{host}/webhook")

if __name__ == '__main__':
    asyncio.run(setup_webhook())
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
