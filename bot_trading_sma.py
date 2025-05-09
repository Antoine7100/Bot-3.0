import ccxt
import pandas as pd
import numpy as np
import time
from threading import Thread
from flask import Flask
import os

# Configuration du serveur Flask
app = Flask(__name__)

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
grid_spacing = 0.005  # Espace entre les ordres de grille
num_grids = 5  # Nombre de niveaux de grille

# Gestion des risques
stop_loss_multiplier = 2

# Indicateurs techniques
def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    data['RSI'] = rsi
    return data


def calculate_bollinger_bands(data, period=20, std_dev=2):
    data['SMA20'] = data['close'].rolling(window=period).mean()
    data['BB_Upper'] = data['SMA20'] + std_dev * data['close'].rolling(window=period).std()
    data['BB_Lower'] = data['SMA20'] - std_dev * data['close'].rolling(window=period).std()
    return data

# Fonction pour récupérer les données OHLC
def get_ohlcv(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Erreur lors de la récupération des données : {e}")
        return None

# Fonction de prise de position
def place_order(symbol, side, amount):
    try:
        print(f"Placing {side} order for {amount} {symbol}")
        order = exchange.create_order(symbol, 'market', side, amount)
        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

# Fonction de trading en arrière-plan
def run_bot():
    while True:
        for symbol in symbols:
            try:
                data = get_ohlcv(symbol)
                if data is None:
                    continue
                data = calculate_rsi(data)
                data = calculate_bollinger_bands(data)

                last_price = data['close'].iloc[-1]
                for i in range(-num_grids, num_grids + 1):
                    grid_price = last_price * (1 + i * grid_spacing)
                    side = 'buy' if i < 0 else 'sell'
                    print(f"Placing grid order at {grid_price} for {symbol}")
                    balance = exchange.fetch_balance()[symbol.split('/')[0]]['free']
                    order_amount = min(balance * 0.9, 15 / len(symbols))
                    place_order(symbol, side, order_amount)

                if data['RSI'].iloc[-1] < 30 and last_price < data['BB_Lower'].iloc[-1]:
                    print(f"Signal d'achat détecté pour {symbol}")
                    place_order(symbol, 'buy', 15 / len(symbols))
                elif data['RSI'].iloc[-1] > 70 and last_price > data['BB_Upper'].iloc[-1]:
                    print(f"Signal de vente détecté pour {symbol}")
                    place_order(symbol, 'sell', 15 / len(symbols))

                time.sleep(30)
            except Exception as e:
                print(f"Erreur pendant la boucle de trading : {e}")
                time.sleep(5)

# Lancer le bot dans un thread
bot_thread = Thread(target=run_bot)
bot_thread.start()

# Démarrer le serveur Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)


