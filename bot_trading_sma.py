import ccxt
import pandas as pd
import numpy as np
import time
from threading import Thread
from flask import Flask, jsonify
import os
import requests

# Configuration du serveur Flask
app = Flask(__name__)

# Configuration Telegram
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Variables globales pour le suivi
positions = []
trades = []
gains_pertes = 0
nb_trades = 0

# Charger les données depuis les fichiers
def load_data():
    global positions, trades, gains_pertes, nb_trades
    try:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, 'r') as f:
                positions = json.load(f)
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, 'r') as f:
                trades = json.load(f)
        print("Données chargées avec succès.")
    except Exception as e:
        print(f"Erreur lors du chargement des données : {e}")

# Sauvegarder les données dans les fichiers
def save_data():
    try:
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(positions, f)
        with open(TRADES_FILE, 'w') as f:
            json.dump(trades, f)
        print("Données sauvegardées avec succès.")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des données : {e}")

# Fonction pour envoyer un message Telegram
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
        requests.post(url, data=payload)
        print(f"Message Telegram envoyé : {message}")
    except Exception as e:
        print(f"Erreur lors de l'envoi du message Telegram : {e}")

# Fonction pour envoyer un résumé quotidien
def send_daily_summary():
    summary = f"Résumé quotidien des trades:\nNombre de trades: {nb_trades}\nGains/Pertes: {gains_pertes} USDT"
    send_telegram_message(summary)

# Planification du résumé quotidien toutes les 24 heures
def schedule_daily_summary():
    while True:
        time.sleep(86400)  # 24 heures
        send_daily_summary()

# Route par défaut
@app.route('/')
def home():
    return 'Bot de Trading SMA 10/100 - En cours de fonctionnement!'

# Route pour afficher les positions ouvertes
@app.route('/positions')
@app.route('/positions')
def get_positions():
    try:
        # Filtrer les positions pour ne conserver que les informations sérialisables
        serializable_positions = [{k: v for k, v in pos.items() if not callable(v)} for pos in positions]
        if serializable_positions:
            return jsonify(serializable_positions), 200
        else:
            return jsonify({"message": "Aucune position ouverte actuellement."}), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'affichage des positions : {str(e)}"}), 500


# Fonction pour envoyer les positions via Telegram
def send_positions_telegram():
    current_positions = fetch_positions()
    if current_positions:
        message = "📊 Positions ouvertes sur Bybit :\n"
        for pos in current_positions:
            message += (f"🔄 Symbole: {pos['symbol']}\n🪙 Type: {pos['side']}\n📏 Quantité: {pos['size']}\n💰 Prix d'entrée: {pos['entry_price']} USDT\n📈 PnL non réalisé: {pos['unrealised_pnl']} USDT\n\n")
        send_telegram_message(message)
    else:
        send_telegram_message("🚫 Aucune position ouverte actuellement.")

# Configuration du bot
exchange = ccxt.bybit({'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_API_SECRET')})
exchange.options['createMarketBuyOrderRequiresPrice'] = False

symbols = ['DOGE/USDT', 'ADA/USDT']
timeframe = '1m'

# Paramètres de la stratégie
short_window = 10
long_window = 100
leverage = 5
risk_percentage = 0.01

def calculate_position_size(balance):
    return max(balance * risk_percentage, 1)


# Fonction pour récupérer les données OHLC
def get_ohlcv(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        send_telegram_message(f"Erreur lors de la récupération des données : {e}")
        return None
        
# Fonction pour récupérer le solde disponible
def get_balance(asset):
    try:
        balance = exchange.fetch_balance()
        return balance['free'].get(asset, 0)
    except Exception as e:
        send_telegram_message(f"Erreur lors de la récupération du solde : {e}")
        return 0
        
# Fonction de prise de position avec vérification du solde
def place_order(symbol, side, amount):
    try:
        asset = symbol.split('/')[0]
        print(f"Placing {side} order for {amount} {symbol}")
        order = exchange.create_order(symbol, 'market', side, amount)
        price = order['price'] if 'price' in order else 'N/A'
        trades.append({'symbol': symbol, 'side': side, 'amount': amount, 'price': price})
        positions.append({'symbol': symbol, 'side': side, 'amount': amount, 'price': price})
        global nb_trades, gains_pertes
        nb_trades += 1
        pnl = amount * float(price) * (1 if side == 'buy' else -1)
        gains_pertes += pnl
        message = (f"🚀 Ordre {side.upper()} exécuté pour {symbol}\n"
                   f"✅ Montant: {amount}\n"
                   f"💵 Prix: {price}\n"
                   f"📊 PnL estimé: {pnl} USDT\n"
                   f"🔗 Total PnL: {gains_pertes} USDT")
        send_telegram_message(message)
        return order
    except Exception as e:
        send_telegram_message(f"❌ Erreur lors de la prise d'ordre : {e}")
        return None


# Fonction de trading en arrière-plan
def run_bot():
    while True:
        for symbol in symbols:
            try:
                data = get_ohlcv(symbol)
                if data is None:
                    continue
                sma10 = data['close'].rolling(window=short_window).mean().iloc[-1]
                sma100 = data['close'].rolling(window=long_window).mean().iloc[-1]
                previous_sma10 = data['close'].rolling(window=short_window).mean().iloc[-2]
                previous_sma100 = data['close'].rolling(window=long_window).mean().iloc[-2]
                if sma10 > sma100 and previous_sma10 <= previous_sma100:
                    print(f"Croisement haussier détecté pour {symbol}")
                    send_telegram_message(f"Croisement haussier détecté pour {symbol}")
                    place_order(symbol, 'buy', 15 / len(symbols))
                elif sma10 < sma100 and previous_sma10 >= previous_sma100:
                    print(f"Croisement baissier détecté pour {symbol}")
                    send_telegram_message(f"Croisement baissier détecté pour {symbol}")
                    place_order(symbol, 'sell', 15 / len(symbols))
                time.sleep(60)
            except Exception as e:
                send_telegram_message(f"Erreur pendant la boucle de trading : {e}")
                time.sleep(5)

# Lancer le bot dans un thread
bot_thread = Thread(target=run_bot)
bot_thread.start()

# Lancer le résumé quotidien dans un thread
summary_thread = Thread(target=schedule_daily_summary)
summary_thread.start()

# Démarrer le serveur Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

