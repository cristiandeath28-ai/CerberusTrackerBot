import telebot
import json
import os
import requests
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
from telebot import types

# ========== CONFIGURACIÓN ==========
TOKEN = "8629922490:AAF5RjcD2d2jTqvphL9IWs14myHC11xdV98"
USDT_WALLET = "HqBcGykafiC7VBCmat6xFY5TSU4Djmek2qmgiVyiT7ZA"
PRICE_MONTHLY = 5  # Precio en USDT
DATA_FILE = "users_data.json"
MAX_WALLETS_PER_USER = 10  # Límite de wallets por usuario

# ========== INICIALIZAR ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== BASE DE DATOS ==========
def load_data():
    """Carga los datos desde archivo JSON"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"users": {}}

def save_data(data):
    """Guarda los datos en archivo JSON"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ========== VERIFICACIÓN DE PAGOS ==========
def verificar_pago_usdt(txid):
    """Verifica si un TXID envió USDT/USDC a tu wallet"""
    try:
        # Usar Solscan API
        url = f"https://public-api.solscan.io/transaction/{txid}"
        r = requests.get(url, timeout=15)
        
        if r.status_code == 200:
            tx_data = r.json()
            transfers = tx_data.get("transfers", [])
            for transfer in transfers:
                destination = transfer.get("destination", "")
                if destination == USDT_WALLET:
                    mint = transfer.get("mint", "")
                    # USDT en Solana
                    if "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB" in mint:
                        amount = transfer.get("amount", 0) / 1e6
                        if amount >= PRICE_MONTHLY - 0.5:
                            return True
                    # USDC en Solana  
                    if "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" in mint:
                        amount = transfer.get("amount", 0) / 1e6
                        if amount >= PRICE_MONTHLY - 0.5:
                            return True
        return False
    except Exception as e:
        print(f"Error verificando pago: {e}")
        return False

# ========== MONITOREO DE WALLETS ==========
def get_solana_price():
    """Obtiene precio de SOL en USD desde CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        r = requests.get(url, timeout=5)
        data = r.json()
        return data.get("solana", {}).get("usd", 180)
    except:
        return 180  # fallback

def check_wallet_balance(address, retry=2):
    """Obtiene el balance SOL de una wallet con reintentos"""
    for intento in range(retry):
        try:
            url = "https://api.mainnet-beta.solana.com"
            headers = {"Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [address]
            }
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if r.status_code == 200:
                result = r.json().get("result")
                if result and "value" in result:
                    return result["value"] / 1e9  # Convertir lamports a SOL
        except:
            time.sleep(1)
    return None

def monitor_loop():
    """Bucle principal de monitoreo - ejecuta cada 5 minutos"""
    print("🔄 Monitor de wallets iniciado...")
    
    while True:
        try:
            data = load_data()
            sol_price = get_solana_price()
            current_time = datetime.now()
            today_str = current_time.strftime("%Y-%m-%d")
            
            for user_id, user_data in data["users"].items():
                # Verificar suscripción activa
                expira_str = user_data.get("suscripcion_hasta")
                if not expira_str:
                    continue
                
                expira = datetime.fromisoformat(expira_str)
                if expira < current_time:
                    continue  # Suscripción vencida
                
                # Monitorear cada wallet del usuario
                wallets = user_data.get("wallets", [])
                for wallet in wallets:
                    address = wallet.get("address")
                    if not address:
                        continue
                    
                    balance_sol = check_wallet_balance(address)
                    
                    if balance_sol is not None and balance_sol > 1:  # Alerta si > 1 SOL
                        balance_usd = balance_sol * sol_price
                        last_alert = wallet.get("last_alert", "")
                        
                        # Enviar alerta solo una vez por día
                        if last_alert != today_str:
                            msg = (
                                f"🚨 *ALERTA CERBERUS* 🚨\n\n"
                                f"📍 *Wallet:* {wallet.get('name', address[:8])}\n"
                                f"💰 *Balance:* {balance_sol:.4f} SOL\n"
                                f"💵 *Valor:* ~${balance_usd:,.0f} USD\n"
                                f"⏰ *Alerta:* Balance superior a 1 SOL\n\n"
                                f"🔗 [Ver en Solscan](https://solscan.io/account/{address})"
                            )
                            
                            try:
                                bot.send_message(int(user_id), msg, parse_mode="Markdown")
                                # Marcar alerta como enviada
                                wallet["last_alert"] = today_str
                                save_data(data)
                                print(f"✅ Alerta enviada a {user_id} por wallet {address[:10]}...")
                            except Exception as e:
                                print(f"Error enviando alerta a {user_id}: {e}")
            
        except Exception as e:
            print(f"Error en monitor_loop: {e}")
        
        # Esperar 5 minutos antes del siguiente ciclo
        time.sleep(300)

# Iniciar hilo de monitoreo al arrancar
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

# ========== MENÚ PRINCIPAL CON BOTONES ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    data = load_data()
    
    if user_id not in data["users"]:
        data["users"][user_id] = {"wallets": [], "suscripcion_hasta": None}
        save_data(data)
    
    # Crear botones del menú principal
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_comprar = types.InlineKeyboardButton("💰 Comprar Suscripción", callback_data="buy")
    btn_wallets = types.InlineKeyboardButton("📋 Mis Wallets", callback_data="my_wallets")
    btn_status = types.InlineKeyboardButton("📊 Mi Estado", callback_data="my_status")
    btn_help = types.InlineKeyboardButton("❓ Ayuda", callback_data="help")
    markup.add(btn_comprar, btn_wallets, btn_status, btn_help)
    
    bot.reply_to(message,
        f"🔒 *CERBERUS TRACKER* 🔒\n\n"
        f"🐺 Monitoreo anónimo de wallets Solana.\n\n"
        f"💰 *Precio:* {PRICE_MONTHLY} USDT/mes\n"
        f"⚡ *Alerta:* Balance > 1 SOL (automática)\n"
        f"📊 *Límite:* {MAX_WALLETS_PER_USER} wallets por usuario\n\n"
        f"Selecciona una opción:",
        reply_markup=markup,
        parse_mode="Markdown")

# ========== COMANDOS TEXTO ==========
@bot.message_handler(commands=['help'])
def help_command(message):
    help_msg = (
        "❓ *COMANDOS CERBERUS*\n\n"
        "/start - Menú principal\n"
        "/add [dirección] [nombre] - Agregar wallet\n"
        "/list - Ver tus wallets\n"
        "/remove [nombre] - Eliminar wallet\n"
        "/pagar [TXID] - Verificar pago USDT\n"
        "/status - Ver estado de suscripción\n"
        "/privacy - Política de privacidad\n"
        "/delete_my_data - Eliminar todos tus datos\n\n"
        f"💰 *Precio:* {PRICE_MONTHLY} USDT/mes\n"
        f"⚡ *Alerta:* Balance > 1 SOL\n"
        f"📊 *Límite:* {MAX_WALLETS_PER_USER} wallets\n\n"
        "📌 *Ejemplo:*\n"
        "/add 7vBc6nQ1XZv3... ballena"
    )
    bot.reply_to(message, help_msg, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data["users"].get(user_id, {})
    expira = user_data.get("suscripcion_hasta")
    wallets_count = len(user_data.get("wallets", []))
    
    if expira and datetime.fromisoformat(expira) > datetime.now():
        dias = (datetime.fromisoformat(expira) - datetime.now()).days
        msg = f"✅ *Suscripción ACTIVA*\n📅 Vence en {dias} días\n📊 {wallets_count}/{MAX_WALLETS_PER_USER} wallets"
    else:
        msg = f"❌ *Suscripción INACTIVA*\n💰 Precio: {PRICE_MONTHLY} USDT/mes\nUsa /pagar o el menú 'Comprar'"
    
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['add'])
def add_wallet(message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data["users"].get(user_id, {})
    expira = user_data.get("suscripcion_hasta")
    
    # Verificar suscripción activa
    if not expira or datetime.fromisoformat(expira) < datetime.now():
        bot.reply_to(message, f"❌ *Necesitas suscripción activa*\n💰 {PRICE_MONTHLY} USDT/mes", parse_mode="Markdown")
        return
    
    # Verificar límite de wallets
    if len(user_data.get("wallets", [])) >= MAX_WALLETS_PER_USER:
        bot.reply_to(message, f"❌ *Límite alcanzado* (máximo {MAX_WALLETS_PER_USER} wallets)", parse_mode="Markdown")
        return
    
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ *Formato incorrecto*\n\nUsa: `/add [dirección] [nombre]`\nEjemplo: `/add 7vBc6nQ1XZv3... ballena`", parse_mode="Markdown")
        return
    
    direccion = partes[1]
    nombre = partes[2] if len(partes) > 2 else direccion[:8]
    
    # Validación básica de dirección Solana
    if len(direccion) < 32 or len(direccion) > 44:
        bot.reply_to(message, "❌ *Dirección inválida*\nDebe tener entre 32 y 44 caracteres", parse_mode="Markdown")
        return
    
    # Verificar si ya existe
    for w in user_data.get("wallets", []):
        if w["address"] == direccion:
            bot.reply_to(message, "❌ *Ya tienes esta wallet agregada*", parse_mode="Markdown")
            return
    
    data["users"][user_id]["wallets"].append({
        "address": direccion,
        "name": nombre,
        "added_date": datetime.now().isoformat()
    })
    save_data(data)
    bot.reply_to(message, f"✅ *Wallet agregada*\n📌 {nombre}\n🔗 `{direccion[:10]}...{direccion[-6:]}`", parse_mode="Markdown")

@bot.message_handler(commands=['list'])
def list_wallets(message):
    user_id = str(message.from_user.id)
    data = load_data()
    wallets = data["users"].get(user_id, {}).get("wallets", [])
    
    if not wallets:
        bot.reply_to(message, "📋 *No tienes wallets agregadas*\nUsa /add para comenzar", parse_mode="Markdown")
        return
    
    msg = "📋 *Tus wallets vigiladas:*\n\n"
    for i, w in enumerate(wallets, 1):
        msg += f"{i}. *{w['name']}*\n   `{w['address'][:10]}...{w['address'][-6:]}`\n\n"
    
    msg += f"\n📊 {len(wallets)}/{MAX_WALLETS_PER_USER} wallets"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_wallet(message):
    user_id = str(message.from_user.id)
    partes = message.text.split()
    
    if len(partes) < 2:
        bot.reply_to(message, "❌ *Formato incorrecto*\nUsa: `/remove [nombre]`", parse_mode="Markdown")
        return
    
    busqueda = partes[1].lower()
    data = load_data()
    original = data["users"].get(user_id, {}).get("wallets", [])
    nuevas = [w for w in original if busqueda not in w["name"].lower()]
    
    if len(nuevas) < len(original):
        data["users"][user_id]["wallets"] = nuevas
        save_data(data)
        bot.reply_to(message, "✅ *Wallet eliminada correctamente*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ *No se encontró ninguna wallet con ese nombre*", parse_mode="Markdown")

@bot.message_handler(commands=['pagar'])
def pagar(message):
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "❌ *Formato incorrecto*\nUsa: `/pagar [TXID]`\n\nEl TXID es el hash de la transacción en Solscan", parse_mode="Markdown")
        return
    
    txid = partes[1]
    user_id = str(message.from_user.id)
    
    msg = bot.reply_to(message, "🔍 *Verificando transacción...*\nEsto puede tomar unos segundos", parse_mode="Markdown")
    
    if verificar_pago_usdt(txid):
        data = load_data()
        fecha_actual = datetime.now()
        fecha_existente = data["users"][user_id].get("suscripcion_hasta")
        
        # Renovación acumulativa
        if fecha_existente and datetime.fromisoformat(fecha_existente) > fecha_actual:
            nueva_fecha = datetime.fromisoformat(fecha_existente) + timedelta(days=30)
        else:
            nueva_fecha = fecha_actual + timedelta(days=30)
        
        data["users"][user_id]["suscripcion_hasta"] = nueva_fecha.isoformat()
        save_data(data)
        
        bot.edit_message_text(
            f"✅ *¡PAGO CONFIRMADO!*\n\n"
            f"💰 Monto: {PRICE_MONTHLY} USDT\n"
            f"📅 Suscripción activa hasta: {nueva_fecha.strftime('%d/%m/%Y')}\n"
            f"🔗 TXID: `{txid[:16]}...`\n\n"
            f"🤖 Ahora puedes agregar wallets con /add",
            msg.chat.id,
            msg.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            f"❌ *PAGO NO VERIFICADO*\n\n"
            f"No se encontró una transacción válida de {PRICE_MONTHLY} USDT a esta wallet:\n"
            f"`{USDT_WALLET[:16]}...`\n\n"
            f"📌 *Posibles causas:*\n"
            f"• El TXID es incorrecto\n"
            f"• La transacción aún no se confirma (espera 1-2 min)\n"
            f"• Enviaste a otra red (debe ser Solana SPL)\n\n"
            f"🔍 [Verificar en Solscan](https://solscan.io/tx/{txid})",
            msg.chat.id,
            msg.message_id,
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['privacy'])
def privacy(message):
    texto = """
*POLÍTICA DE PRIVACIDAD - CERBERUS TRACKER*

📌 *Datos que recopilamos:*
- ID de Telegram
- Direcciones públicas de wallets Solana
- Nombres asignados a tus wallets
- Fechas de suscripción

📌 *Cómo usamos tus datos:*
- Exclusivamente para enviarte alertas de monitoreo
- No compartimos ni vendemos datos a terceros

📌 *Base legal (LOPDP Ecuador):*
- Consentimiento explícito al usar el bot
- Datos mínimos necesarios para el servicio

📌 *Tus derechos:*
- Acceder a tus datos: /list
- Eliminar tus datos: /delete_my_data
- Oponerte al tratamiento: Eliminando tus datos

📌 *Retención de datos:*
- Se eliminan automáticamente 30 días después de finalizar la suscripción
- O inmediatamente si usas /delete_my_data

📌 *Contacto:* @cerberusec

✅ *Al usar este bot, aceptas esta política.*
"""
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(commands=['delete_my_data'])
def delete_my_data(message):
    user_id = str(message.from_user.id)
    data = load_data()
    
    if user_id in data["users"]:
        del data["users"][user_id]
        save_data(data)
        bot.reply_to(message, "🗑️ *Tus datos han sido eliminados permanentemente*\n\nSi cambias de opinión, usa /start para comenzar de nuevo.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "ℹ️ No tenías datos registrados en nuestro sistema.", parse_mode="Markdown")

# ========== MANEJADOR DE BOTONES ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = str(call.from_user.id)
    
    if call.data == "buy":
        # Solo método USDT
        markup = types.InlineKeyboardMarkup()
        btn_usdt = types.InlineKeyboardButton("🪙 Pagar con USDT (Solana)", callback_data="pay_usdt")
        btn_back = types.InlineKeyboardButton("◀️ Volver", callback_data="back_to_start")
        markup.add(btn_usdt, btn_back)
        
        bot.edit_message_text(
            f"💵 *PAGO CON USDT*\n\n"
            f"💰 *Precio:* {PRICE_MONTHLY} USDT/mes\n"
            f"🔗 *Red:* Solana (SPL)\n\n"
            f"🪙 *Único método de pago disponible:*\n"
            f"USDT en la red Solana\n\n"
            f"Selecciona la opción para ver los detalles de pago:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    
    elif call.data == "pay_usdt":
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Volver a métodos", callback_data="buy")
        markup.add(btn_back)
        
        bot.edit_message_text(
            f"🪙 *PAGO CON USDT (Solana)*\n\n"
            f"💰 *Monto exacto:* {PRICE_MONTHLY} USDT\n"
            f"⚠️ *Importante:* Paga EXACTAMENTE {PRICE_MONTHLY} USDT\n"
            f"🔗 *Red:* Solana (SPL) - NO uses ERC20 o BEP20\n"
            f"📥 *Dirección:*\n`{USDT_WALLET}`\n\n"
            f"📌 *Instrucciones:*\n"
            f"1️⃣ Envía {PRICE_MONTHLY} USDT a la dirección\n"
            f"2️⃣ Usa SOLO la red Solana\n"
            f"3️⃣ Espera 1-2 minutos a la confirmación\n"
            f"4️⃣ Copia el TXID (hash de la transacción)\n"
            f"5️⃣ Envía `/pagar [TXID]` al bot\n\n"
            f"🔍 *Verificar wallet:*\n[Solscan](https://solscan.io/account/{USDT_WALLET})",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    
    elif call.data == "my_wallets":
        data = load_data()
        wallets = data["users"].get(user_id, {}).get("wallets", [])
        
        if not wallets:
            msg = "📋 *No tienes wallets agregadas*\n\nUsa /add para comenzar"
        else:
            msg = "📋 *Tus wallets vigiladas:*\n\n"
            for i, w in enumerate(wallets, 1):
                msg += f"{i}. *{w['name']}*\n   `{w['address'][:10]}...{w['address'][-6:]}`\n\n"
            msg += f"\n📊 {len(wallets)}/{MAX_WALLETS_PER_USER} wallets"
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Volver", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    
    elif call.data == "my_status":
        data = load_data()
        user_data = data["users"].get(user_id, {})
        expira = user_data.get("suscripcion_hasta")
        wallets_count = len(user_data.get("wallets", []))
        
        if expira and datetime.fromisoformat(expira) > datetime.now():
            dias = (datetime.fromisoformat(expira) - datetime.now()).days
            msg = f"✅ *SUSCRIPCIÓN ACTIVA*\n\n📅 Vence en {dias} días\n📊 {wallets_count}/{MAX_WALLETS_PER_USER} wallets\n💰 Precio: {PRICE_MONTHLY} USDT/mes"
        else:
            msg = f"❌ *SUSCRIPCIÓN INACTIVA*\n\n💰 Precio: {PRICE_MONTHLY} USDT/mes\n⚡ Alerta: Balance > 1 SOL\n\nUsa 'Comprar Suscripción' para activar"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_buy = types.InlineKeyboardButton("💰 Comprar ahora", callback_data="buy")
        btn_back = types.InlineKeyboardButton("◀️ Volver", callback_data="back_to_start")
        markup.add(btn_buy, btn_back)
        
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    
    elif call.data == "help":
        help_msg = (
            "❓ *AYUDA - CERBERUS TRACKER*\n\n"
            "*Comandos disponibles:*\n"
            "/start - Menú principal\n"
            "/add [dir] [nombre] - Agregar wallet\n"
            "/list - Ver tus wallets\n"
            "/remove [nombre] - Eliminar wallet\n"
            "/pagar [TXID] - Verificar pago USDT\n"
            "/status - Ver estado de suscripción\n"
            "/privacy - Política de privacidad\n"
            "/delete_my_data - Borrar todos tus datos\n\n"
            f"💰 *Precio:* {PRICE_MONTHLY} USDT/mes\n"
            f"⚡ *Alerta:* Balance > 1 SOL\n"
            f"📊 *Límite:* {MAX_WALLETS_PER_USER} wallets\n\n"
            "*Ejemplo rápido:*\n"
            "1. /pagar [TXID] - Activar suscripción\n"
            "2. /add 7vBc6n... ballena - Agregar wallet\n"
            "3. ¡Recibirás alertas automáticas!\n\n"
            "📌 *Soporte:* @cerberusec"
        )
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Volver", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.edit_message_text(
            help_msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    
    elif call.data == "back_to_start":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_comprar = types.InlineKeyboardButton("💰 Comprar Suscripción", callback_data="buy")
        btn_wallets = types.InlineKeyboardButton("📋 Mis Wallets", callback_data="my_wallets")
        btn_status = types.InlineKeyboardButton("📊 Mi Estado", callback_data="my_status")
        btn_help = types.InlineKeyboardButton("❓ Ayuda", callback_data="help")
        markup.add(btn_comprar, btn_wallets, btn_status, btn_help)
        
        bot.edit_message_text(
            f"🔒 *CERBERUS TRACKER* 🔒\n\n"
            f"🐺 Monitoreo anónimo de wallets Solana.\n\n"
            f"💰 *Precio:* {PRICE_MONTHLY} USDT/mes\n"
            f"⚡ *Alerta:* Balance > 1 SOL\n"
            f"📊 *Límite:* {MAX_WALLETS_PER_USER} wallets\n\n"
            f"Selecciona una opción:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )

# ========== WEBHOOK Y SERVIDOR ==========
@app.route('/')
def home():
    return "✅ CerberusTracker funcionando correctamente", 200

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
def webhook():
    """Recibe actualizaciones de Telegram"""
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            print(f"Error en webhook: {e}")
            return 'Error interno', 500
    return '', 403

# ========== INICIAR APLICACIÓN ==========
if __name__ == "__main__":
    # Configurar webhook si estamos en Render
    webhook_url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if webhook_url:
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{webhook_url}/webhook/{TOKEN}")
            print(f"✅ Webhook configurado: {webhook_url}")
        except Exception as e:
            print(f"Error configurando webhook: {e}")
    
    print("=" * 60)
    print("🔒 CERBERUS TRACKER - BOT DE MONITOREO 🔒")
    print("=" * 60)
    print(f"🤖 Bot iniciado correctamente")
    print(f"💰 Precio: {PRICE_MONTHLY} USDT/mes")
    print(f"🔗 Wallet receptora: {USDT_WALLET[:16]}...")
    print(f"📊 Máx wallets por usuario: {MAX_WALLETS_PER_USER}")
    print(f"⚡ Alerta: Balance > 1 SOL")
    print(f"🌐 Webhook: {'Configurado' if webhook_url else 'No configurado (modo polling)'}")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)