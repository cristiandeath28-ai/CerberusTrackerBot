import telebot
import json
import os
import threading
from datetime import datetime, timedelta
from flask import Flask, request

# ========== CONFIGURACIÓN ==========
TOKEN = "8629922490:AAF5RjcD2d2jTqvphL9IWs14myHC11xdV98"
USDT_WALLET = "HqBcGykafiC7VBCmat6xFY5TSU4Djmek2qmgiVyiT7ZA"
PRICE_MONTHLY = 8

DATA_FILE = "users_data.json"

# ========== INICIALIZAR ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== BASE DE DATOS ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"users": {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ========== COMANDOS ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    data = load_data()
    
    if user_id not in data["users"]:
        data["users"][user_id] = {"wallets": [], "suscripcion_hasta": None}
        save_data(data)
    
    bot.reply_to(message, 
        f"🚀 *WALLET TRACKER BOT*\n\n"
        f"💰 Precio: {PRICE_MONTHLY} USDT/mes\n"
        f"🔗 Pagar a: `{USDT_WALLET}`\n\n"
        f"📌 Comandos:\n"
        f"/start - Este mensaje\n"
        f"/add [dirección] - Agregar wallet\n"
        f"/list - Ver wallets\n"
        f"/remove [dirección] - Eliminar wallet\n"
        f"/pagar [TXID] - Verificar pago\n"
        f"/status - Ver suscripción",
        parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status(message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data["users"].get(user_id, {})
    expira = user_data.get("suscripcion_hasta")
    
    if expira and datetime.fromisoformat(expira) > datetime.now():
        dias = (datetime.fromisoformat(expira) - datetime.now()).days
        bot.reply_to(message, f"✅ *Activa*\n📅 Vence en {dias} días", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ *Sin suscripción*\n💰 Paga {PRICE_MONTHLY} USDT a `{USDT_WALLET}`", parse_mode="Markdown")

@bot.message_handler(commands=['add'])
def add_wallet(message):
    user_id = str(message.from_user.id)
    data = load_data()
    expira = data["users"].get(user_id, {}).get("suscripcion_hasta")
    
    if not expira or datetime.fromisoformat(expira) < datetime.now():
        bot.reply_to(message, f"❌ *Necesitas suscripción*\n💰 Paga {PRICE_MONTHLY} USDT", parse_mode="Markdown")
        return
    
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /add [dirección]")
        return
    
    direccion = partes[1]
    nombre = partes[2] if len(partes) > 2 else direccion[:8]
    
    data["users"][user_id]["wallets"].append({"address": direccion, "name": nombre})
    save_data(data)
    bot.reply_to(message, f"✅ Wallet {nombre} agregada")

@bot.message_handler(commands=['list'])
def list_wallets(message):
    user_id = str(message.from_user.id)
    wallets = load_data()["users"].get(user_id, {}).get("wallets", [])
    
    if not wallets:
        bot.reply_to(message, "📋 No hay wallets")
        return
    
    msg = "📋 *Tus wallets:*\n"
    for i, w in enumerate(wallets, 1):
        msg += f"{i}. {w['name']}\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_wallet(message):
    user_id = str(message.from_user.id)
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /remove [nombre]")
        return
    
    busqueda = partes[1].lower()
    data = load_data()
    original = data["users"].get(user_id, {}).get("wallets", [])
    nuevas = [w for w in original if busqueda not in w["name"].lower()]
    
    if len(nuevas) < len(original):
        data["users"][user_id]["wallets"] = nuevas
        save_data(data)
        bot.reply_to(message, "✅ Wallet eliminada")
    else:
        bot.reply_to(message, "❌ No encontrada")

@bot.message_handler(commands=['pagar'])
def pagar(message):
    import requests
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /pagar [TXID]")
        return
    
    txid = partes[1]
    user_id = str(message.from_user.id)
    
    msg = bot.reply_to(message, "🔍 Verificando...")
    
    try:
        url = f"https://public-api.solscan.io/transaction/{txid}"
        r = requests.get(url, timeout=10)
        
        if r.status_code == 200 and USDT_WALLET.lower() in str(r.json()).lower():
            data = load_data()
            fecha = datetime.now() + timedelta(days=30)
            data["users"][user_id]["suscripcion_hasta"] = fecha.isoformat()
            save_data(data)
            bot.edit_message_text(f"✅ Pago confirmado. Activa hasta {fecha.strftime('%d/%m/%Y')}", msg.chat.id, msg.message_id)
        else:
            bot.edit_message_text(f"❌ TXID no válido", msg.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)[:50]}", msg.chat.id, msg.message_id)

# ========== WEBHOOK PARA RENDER ==========
@app.route('/')
def home():
    return "Bot funcionando ✅", 200

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    return '', 403

# ========== INICIAR ==========
if __name__ == "__main__":
    # Configurar webhook automáticamente en Render
    webhook_url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if webhook_url:
        bot.remove_webhook()
        bot.set_webhook(url=f"{webhook_url}/webhook/{TOKEN}")
        print(f"✅ Webhook: {webhook_url}")
    
    print("🤖 Bot iniciado")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)