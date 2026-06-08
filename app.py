import telebot
import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ========== CONFIGURACIÓN ==========
TOKEN = "8629922490:AAF5RjcD2d2jTqvphL9IWs14myHC11xdV98"
USDT_WALLET = "HqBcGykafiC7VBCmat6xFY5TSU4Djmek2qmgiVyiT7ZA"
PRICE_MONTHLY = 8

DATA_FILE = "users_data.json"

# ========== INICIALIZAR BOT Y FLASK ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Variable para controlar el webhook
WEBHOOK_URL = None

# ========== BASE DE DATOS ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"users": {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ========== COMANDOS DEL BOT ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    data = load_data()
    
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "wallets": [],
            "suscripcion_hasta": None
        }
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
        f"/status - Ver suscripción\n"
        f"/help - Ayuda",
        parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message,
        f"❓ *AYUDA*\n\n"
        f"1. Envía {PRICE_MONTHLY} USDT a `{USDT_WALLET}`\n"
        f"2. Copia el TXID de la transacción\n"
        f"3. Usa /pagar [TXID]\n"
        f"4. Usa /add [dirección] para agregar wallets\n\n"
        f"🔍 Ver TXID en: https://solscan.io",
        parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status(message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data["users"].get(user_id, {})
    expira = user_data.get("suscripcion_hasta")
    
    if expira:
        fecha_expira = datetime.fromisoformat(expira)
        if fecha_expira > datetime.now():
            dias = (fecha_expira - datetime.now()).days
            bot.reply_to(message, f"✅ *Suscripción ACTIVA*\n📅 Vence en {dias} días", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"❌ *Suscripción EXPIRADA*\n💰 Renueva por {PRICE_MONTHLY} USDT", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ *Sin suscripción*\n💰 Paga {PRICE_MONTHLY} USDT a `{USDT_WALLET}`", parse_mode="Markdown")

@bot.message_handler(commands=['add'])
def add_wallet(message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data["users"].get(user_id, {})
    expira = user_data.get("suscripcion_hasta")
    
    if not expira or datetime.fromisoformat(expira) < datetime.now():
        bot.reply_to(message, f"❌ *Necesitas suscripción activa*\n💰 Paga {PRICE_MONTHLY} USDT a `{USDT_WALLET}`", parse_mode="Markdown")
        return
    
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /add [dirección_de_wallet]\nEjemplo: /add 7vBc6nZgQZqrBcRfC7tF3vVwQxZqUqRqQqRqQqR", parse_mode="Markdown")
        return
    
    direccion = partes[1]
    nombre = partes[2] if len(partes) > 2 else direccion[:8]
    
    if len(direccion) < 32 or len(direccion) > 44:
        bot.reply_to(message, "❌ Dirección inválida", parse_mode="Markdown")
        return
    
    data["users"][user_id]["wallets"].append({
        "address": direccion,
        "name": nombre,
        "fecha": datetime.now().isoformat()
    })
    save_data(data)
    
    bot.reply_to(message, f"✅ *Wallet agregada*\n📌 {nombre}\n🔗 `{direccion[:10]}...{direccion[-6:]}`", parse_mode="Markdown")

@bot.message_handler(commands=['list'])
def list_wallets(message):
    user_id = str(message.from_user.id)
    data = load_data()
    wallets = data["users"].get(user_id, {}).get("wallets", [])
    
    if not wallets:
        bot.reply_to(message, "📋 *No tienes wallets*\nUsa /add para agregar", parse_mode="Markdown")
        return
    
    mensaje = "📋 *Tus wallets:*\n\n"
    for i, w in enumerate(wallets, 1):
        mensaje += f"{i}. *{w['name']}*\n   `{w['address'][:10]}...{w['address'][-6:]}`\n\n"
    
    bot.reply_to(message, mensaje, parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_wallet(message):
    user_id = str(message.from_user.id)
    partes = message.text.split()
    
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /remove [nombre_o_dirección]", parse_mode="Markdown")
        return
    
    busqueda = partes[1].lower()
    data = load_data()
    original = data["users"].get(user_id, {}).get("wallets", [])
    
    nuevas = [w for w in original if busqueda not in w["address"].lower() and busqueda not in w["name"].lower()]
    
    if len(nuevas) < len(original):
        data["users"][user_id]["wallets"] = nuevas
        save_data(data)
        bot.reply_to(message, "✅ *Wallet eliminada*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ *No se encontró*", parse_mode="Markdown")

@bot.message_handler(commands=['pagar'])
def pagar(message):
    import requests
    
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ Usa: /pagar [TXID]", parse_mode="Markdown")
        return
    
    txid = partes[1]
    user_id = str(message.from_user.id)
    
    msg = bot.reply_to(message, "🔍 *Verificando transacción...*", parse_mode="Markdown")
    
    try:
        url = f"https://public-api.solscan.io/transaction/{txid}"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            datos = response.json()
            tx_info = str(datos).lower()
            
            if USDT_WALLET.lower() in tx_info:
                data = load_data()
                fecha_expiracion = datetime.now() + timedelta(days=30)
                
                if user_id not in data["users"]:
                    data["users"][user_id] = {"wallets": [], "suscripcion_hasta": None}
                
                data["users"][user_id]["suscripcion_hasta"] = fecha_expiracion.isoformat()
                save_data(data)
                
                bot.edit_message_text(
                    f"✅ *¡PAGO CONFIRMADO!*\n\n"
                    f"📅 Suscripción activa hasta: `{fecha_expiracion.strftime('%d/%m/%Y')}`",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
            else:
                bot.edit_message_text(
                    f"❌ *Transacción no válida*\nNo se recibió pago a tu dirección.",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
        else:
            bot.edit_message_text(
                f"❌ *No se pudo verificar*\nVerifica en https://solscan.io/tx/{txid}",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ *Error:* {str(e)[:100]}",
            chat_id=msg.chat.id,
            message_id=msg.message_id,
            parse_mode="Markdown"
        )

# ========== ENDPOINTS PARA RENDER ==========
@app.route('/')
def home():
    return "Bot funcionando ✅", 200

@app.route('/health')
def health():
    return "OK", 200

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

# ========== CONFIGURAR WEBHOOK ==========
def set_webhook():
    global WEBHOOK_URL
    # Render asigna la variable de entorno RENDER_EXTERNAL_URL
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook configurado: {webhook_url}")
    else:
        print("⚠️ No se detectó RENDER_EXTERNAL_URL, usando polling...")
        # Iniciar polling en un hilo separado
        threading.Thread(target=bot.infinity_polling, daemon=True).start()

# ========== INICIAR SERVIDOR ==========
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 BOT INICIADO EN MODO WEBHOOK")
    print(f"💰 Wallet: {USDT_WALLET}")
    print("=" * 50)
    
    # Configurar webhook
    set_webhook()
    
    # Iniciar servidor Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)