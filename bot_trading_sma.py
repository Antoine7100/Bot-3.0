import ccxt
import pandas as pd
import numpy as np
import time
from threading import Thread
from flask import Flask
import os
import requests

# Configuration du serveur Flask
app = Flask(__name__)

# Configuration Telegram
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        requests.post(url, data=payload)
        print(f"Message Telegram envoyé : {message}")
    except Exception as e:
        print(f"Erreur lors de l'envoi du message Telegram : {e}")

# Route par défaut pour le service Web
@app.route('/')
def home():
    return 'Bot de Trading SMA 10/100 - En cours de fonctionnement!'

# Configuration
exchange = ccxt.bybit({
    'apiKey': os.getenv('API_KEY'),
    'secret': os.getenv('API_SECRET')
})
symbols = ['DOGE/USDT', 'ADA/USDT']
timeframe = '1m'

# Paramètres de la stratégie
short_window = 10
long_window = 100
leverage = 5

# Paramètres de la stratégie en grille
grid_spacing = 0.005
num_grids = 5

# Gestion des risques
stop_loss_multiplier = 2

# Calcul des moyennes mobiles
def calculate_sma(data):
    data['SMA10'] = data['close'].rolling(window=short_window).mean()
    data['SMA100'] = data['close'].rolling(window=long_window).mean()
    return data

# Fonction pour récupérer les données OHLC
def get_ohlcv(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return calculate_sma(df)
    except Exception as e:
        print(f"Erreur lors de la récupération des données : {e}")
        send_telegram_message(f"Erreur lors de la récupération des données : {e}")
        return None

# Fonction de prise de position
def place_order(symbol, side, amount):
    try:
        print(f"Placing {side} order for {amount} {symbol}")
        order = exchange.create_order(symbol, 'market', side, amount)
        send_telegram_message(f"Ordre {side} placé pour {amount} {symbol}")
        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        send_telegram_message(f"Erreur lors de la prise d'ordre : {e}")
        return None

# Fonction de trading en arrière-plan
def run_bot():
    while True:
        for symbol in symbols:
            try:
                data = get_ohlcv(symbol)
                if data is None:
                    continue

                last_price = data['close'].iloc[-1]
                sma10 = data['SMA10'].iloc[-1]
                sma100 = data['SMA100'].iloc[-1]

                # Vérification des signaux d'achat/vente
                if sma10 > sma100:
                    print(f"Signal d'achat détecté pour {symbol}")
                    send_telegram_message(f"Signal d'achat détecté pour {symbol}")
                    place_order(symbol, 'buy', 15 / len(symbols))
                elif sma10 < sma100:
                    print(f"Signal de vente détecté pour {symbol}")
                    send_telegram_message(f"Signal de vente détecté pour {symbol}")
                    place_order(symbol, 'sell', 15 / len(symbols))

                time.sleep(30)
            except Exception as e:
                print(f"Erreur pendant la boucle de trading : {e}")
                send_telegram_message(f"Erreur pendant la boucle de trading : {e}")
                time.sleep(5)

# Lancer le bot dans un thread
bot_thread = Thread(target=run_bot)
bot_thread.start()

# Démarrer le serveur Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)



