import json
import os
import asyncio
import aiohttp
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8636300409:AAFy2XvQOvm_UVyzwuFG4N1fv0tZgTMk97Y"
ADMIN_IDS = [6706047006, 5595239245]

app = Flask(__name__)
CORS(app)

application = Application.builder().token(BOT_TOKEN).build()
bot = application.bot

# ========== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ==========
BALANCE_FILE = 'balances.json'
USER_DATA_FILE = 'user_data.json'

def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f)

balances = load_json(BALANCE_FILE)
user_data = load_json(USER_DATA_FILE)

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
initialized = False

async def init_app():
    global initialized
    if not initialized:
        await application.initialize()
        initialized = True
        print("✅ Application initialized")

async def notify_admins_about_win(user_name: str, user_id: int, case_name: str, prize_name: str, prize_price: int):
    """Отправляет уведомление всем админам о выигрыше"""
    message = f"🏆 {user_name} (ID: {user_id}) выиграл {prize_name} ({prize_price} ₽) из кейса {case_name}!"
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {"chat_id": admin_id, "text": message}
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    if not result.get("ok"):
                        print(f"❌ Ошибка отправки админу {admin_id}: {result}")
            except Exception as e:
                print(f"❌ Ошибка отправки админу {admin_id}: {e}")

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
            save_json(BALANCE_FILE, balances)
            await update.message.reply_text(f"Done: {amount} to {user_id}")
            try:
                await bot.send_message(chat_id=user_id, text=f"Balance updated: {amount}")
            except:
                pass
    except Exception as e:
        print(f"Error: {e}")

application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

# ========== ВЕБХУК ==========
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

# ========== API БАЛАНСА ==========
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
        save_json(BALANCE_FILE, balances)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ========== API ДАННЫХ ПОЛЬЗОВАТЕЛЯ (КЕЙСЫ, ИНВЕНТАРЬ) ==========
@app.route('/api/user/data/<user_id>')
def get_user_data(user_id):
    data = user_data.get(str(user_id), {
        'ownedCases': {},
        'inventory': [],
        'nextId': 1
    })
    return jsonify(data)

@app.route('/api/user/data/update', methods=['POST', 'OPTIONS'])
def update_user_data():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        user_id = str(data.get('userId'))
        user_data[user_id] = {
            'ownedCases': data.get('ownedCases', {}),
            'inventory': data.get('inventory', []),
            'nextId': data.get('nextId', 1)
        }
        save_json(USER_DATA_FILE, user_data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ========== API АДМИН-ПАНЕЛИ ==========
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
        save_json(BALANCE_FILE, balances)
        async def notify():
            try:
                await bot.send_message(chat_id=target_id, text=f"Balance updated: {amount}")
            except:
                pass
        asyncio.run(notify())
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error"}), 500

# ========== API УВЕДОМЛЕНИЙ О ВЫИГРЫШЕ ==========
@app.route('/api/notify/win', methods=['POST', 'OPTIONS'])
def notify_win():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        user_name = data.get('userName', 'Гость')
        user_id = data.get('userId')
        case_name = data.get('caseName', 'Неизвестно')
        prize_name = data.get('prize', 'Неизвестно')
        prize_price = data.get('totalWin', 0)
        
        async def notify():
            await notify_admins_about_win(user_name, user_id, case_name, prize_name, prize_price)
        asyncio.run(notify())
        
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/')
def home():
    return "OK", 200

async def setup_webhook():
    await init_app()
    host = os.environ.get('RENDER_EXTERNAL_HOSTNAME') or os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if host:
        if not host.startswith('http'):
            host = f"https://{host}"
        await bot.set_webhook(f"{host}/webhook")
        print(f"✅ Webhook set to {host}/webhook")
    else:
        print("⚠️ No host found, webhook not set")

if __name__ == '__main__':
    asyncio.run(setup_webhook())
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
