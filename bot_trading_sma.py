import ccxt
import pandas as pd
import time

# Configuration
exchange = ccxt.bybit({'apiKey': 'YOUR_API_KEY', 'secret': 'YOUR_API_SECRET'})
symbols = ['DOGE/USDT', 'ADA/USDT']
timeframe = '1m'

# Paramètres de la stratégie
short_window = 10
long_window = 100
leverage = 5

# Gestion des risques
stop_loss_multiplier = 2  # Basé sur l'ATR

# Fonction pour récupérer les données OHLC
def get_ohlcv():
    bars = exchange.fetch_ohlcv(symbol, timeframe)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# Calcul des moyennes mobiles
def calculate_sma(data):
    data['SMA10'] = data['close'].rolling(window=short_window).mean()
    data['SMA100'] = data['close'].rolling(window=long_window).mean()
    return data

# Fonction de prise de position
def place_order(symbol, side, amount):
    try:
        print(f"Placing {side} order for {amount} {symbol}")
        order = exchange.create_order(symbol, 'market', side, amount)
        return order
            except Exception as e:
        print(f"Error placing order: {e}")
        return None

# Boucle de trading
while True:
    for symbol in symbols:
        try:
        try:
                    data = get_ohlcv()()
                    data = calculate_sma(data)

        # Signaux d'achat/vente
                    if data['SMA10'].iloc[-1] > data['SMA100'].iloc[-1]:
                            print("Signal d'achat détecté")
                            place_order(symbol, 'buy', 15 / len(symbols))

                    elif data['SMA10'].iloc[-1] < data['SMA100'].iloc[-1]:
                            print("Signal de vente détecté")
                            place_order(symbol, 'sell', 15 / len(symbols))

                    time.sleep(30)  # Attendre 1 minute avant la prochaine itération
    except Exception as e:
                    print(f"Erreur pendant la boucle de trading : {e}")
                    time.sleep(5)


