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
def positions():
    return jsonify(positions)

# Fonction pour envoyer les positions via Telegram
def send_positions_telegram():
    if positions:
        message = "Positions ouvertes sur Bybit :\n"
        for pos in positions:
            message += (f"Symbole: {pos['symbol']}\nType: {pos['side']}\nQuantité: {pos['amount']}\nPrix: {pos['price']} USDT\n\n")
        send_telegram_message(message)
    else:
        send_telegram_message("Aucune position ouverte actuellement.")

# Configuration du bot
exchange = ccxt.bybit({'apiKey': os.getenv('API_KEY'), 'secret': os.getenv('API_SECRET')})
symbols = ['DOGE/USDT', 'ADA/USDT']
timeframe = '1m'

# Paramètres de la stratégie
short_window = 10
long_window = 100
leverage = 5
risk_percentage = 0.01

# Gestion des risques dynamiques
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

# Fonction de prise de position
def place_order(symbol, side, amount):
    try:
        print(f"Placing {side} order for {amount} {symbol}")
        order = exchange.create_order(symbol, 'market', side, amount)
        price = order['price'] if 'price' in order else 'N/A'
        trades.append({'symbol': symbol, 'side': side, 'amount': amount, 'price': price})
        positions.append({'symbol': symbol, 'side': side, 'amount': amount, 'price': price})
        global nb_trades, gains_pertes
        nb_trades += 1
        pnl = amount * float(price) * (1 if side == 'buy' else -1)
        gains_pertes += pnl
        message = (f"Ordre {side.upper()} exécuté pour {symbol}\nMontant: {amount}\nPrix: {price}\nPnL estimé: {pnl} USDT\nTotal PnL: {gains_pertes} USDT")
        send_telegram_message(message)
        return order
    except Exception as e:
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
                time.sleep(30)
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

