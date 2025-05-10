### Code complet et optimisé du bot de trading avec toutes les fonctionnalités

import ccxt
import pandas as pd
import numpy as np
import time
from threading import Thread
from flask import Flask, jsonify
import os
import requests
import json
import logging

# Configuration du serveur Flask
app = Flask(__name__)

# Configuration du fichier de log
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')

    def send_message(self, message, emoji='💬'):
        try:
            cool_message = f"{emoji} {message}"
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            data = json.dumps({'chat_id': self.chat_id, 'text': cool_message})
            response = requests.post(url, headers=headers, data=data)
            if response.status_code == 200:
                logging.info(f"Message envoyé : {cool_message}")
            else:
                logging.error(f"Erreur d'envoi Telegram : {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Erreur d'envoi Telegram : {e}")

    def send_order_notification(self, symbol, side, amount, price, pnl):
        emoji = '🚀' if side == 'buy' else '🔻'
        message = (f"{emoji} Ordre {side.upper()} exécuté pour {symbol}\n"
                   f"💰 Montant: {amount}\n"
                   f"📈 Prix: {price} USDT\n"
                   f"📊 PnL: {pnl} USDT")
        self.send_message(message, emoji)

notifier = TelegramNotifier()


class TradeManager:
    def __init__(self):
        self.positions = []
        self.trades = []
        self.gains_pertes = 0
        self.nb_trades = 0
        self.positions_file = 'positions.json'
        self.trades_file = 'trades.json'
        self.load_data()

    def load_data(self):
        try:
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r') as f:
                    self.positions = json.load(f)
            if os.path.exists(self.trades_file):
                with open(self.trades_file, 'r') as f:
                    self.trades = json.load(f)
        except Exception as e:
            logging.error(f"Erreur lors du chargement des données : {e}")

    def save_data(self):
        try:
            with open(self.positions_file, 'w') as f:
                json.dump(self.positions, f)
            with open(self.trades_file, 'w') as f:
                json.dump(self.trades, f)
        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde des données : {e}")

    def log_trade(self, symbol, side, amount, price, pnl):
        try:
            trade_entry = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'pnl': pnl
            }
            with open('trades_log.json', 'a') as f:
                json.dump(trade_entry, f)
                f.write('\n')
            logging.info(f'Trade enregistré : {trade_entry}')
        except Exception as e:
            logging.error(f'Erreur lors de la journalisation du trade : {e}')


trade_manager = TradeManager()

class BotTrader:
    def __init__(self):
        self.exchange = ccxt.bybit({'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_API_SECRET')})
        self.symbols = ['DOGE/USDT', 'ADA/USDT']
        self.timeframe = '5m'
        self.tp_percentage = 0.02
        self.sl_percentage = 0.01
        self.daily_loss_limit = 100  # Limite de perte journalière en USDT
        self.daily_loss = 0
        self.current_day = time.strftime('%Y-%m-%d')

    def reset_daily_loss(self):
        self.daily_loss = 0
        self.current_day = time.strftime('%Y-%m-%d')
        logging.info("🔄 Réinitialisation de la perte journalière.")

    def update_daily_loss(self, loss):
        self.daily_loss += loss
        if self.daily_loss >= self.daily_loss_limit:
            logging.warning("🚫 Limite de perte journalière atteinte, arrêt des trades pour aujourd'hui.")
            notifier.send_message("🚫 Limite de perte journalière atteinte, arrêt des trades.", '❗')
            return False
        return True

    def calculate_tp_sl(self, entry_price):
        tp = entry_price * (1 + self.tp_percentage)
        sl = entry_price * (1 - self.sl_percentage)
        return tp, sl

    def monitor_positions(self):
        while True:
            if time.strftime('%Y-%m-%d') != self.current_day:
                self.reset_daily_loss()
            for pos in trade_manager.positions[:]:
                try:
                    current_price = self.exchange.fetch_ticker(pos['symbol'])['last']
                    if current_price >= pos['tp']:
                        notifier.send_message(f"🎯 TP atteint pour {pos['symbol']} à {current_price} USDT")
                        trade_manager.positions.remove(pos)
                        trade_manager.save_data()
                    elif current_price <= pos['sl']:
                        loss = pos['entry_price'] - current_price
                        if self.update_daily_loss(loss):
                            notifier.send_message(f"🔻 SL atteint pour {pos['symbol']} à {current_price} USDT")
                            trade_manager.positions.remove(pos)
                            trade_manager.save_data()
                        else:
                            notifier.send_message(f"❗ Stop trading atteint pour la journée : perte de {self.daily_loss} USDT", '🚫')
                except Exception as e:
                    logging.error(f"Erreur lors de la vérification TP/SL : {e}")
            time.sleep(30)

    def place_order(self, symbol, side, amount):
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance['free'].get('USDT', 0)
            order_amount = min(amount, usdt_balance * 0.5)

            if order_amount <= 0:
                notifier.send_message(f"🚫 Solde insuffisant pour passer un ordre sur {symbol}", '⚠️')
                return None

            order = self.exchange.create_order(symbol, 'market', side, order_amount)
            entry_price = order['price'] if 'price' in order else self.exchange.fetch_ticker(symbol)['last']
            tp, sl = self.calculate_tp_sl(entry_price)
            trade_manager.positions.append({'symbol': symbol, 'side': side, 'amount': order_amount, 'entry_price': entry_price, 'tp': tp, 'sl': sl})
            trade_manager.save_data()
            notifier.send_order_notification(symbol, side, order_amount, entry_price, 0)
            logging.info(f"Ordre {side} pour {symbol} exécuté avec {order_amount} USDT à {entry_price}, TP: {tp}, SL: {sl}")
            return order
        except Exception as e:
            notifier.send_message(f"❌ Erreur lors de la prise d'ordre : {e}")
            logging.error(f"Erreur lors de la prise d'ordre : {e}")


    def run_bot(self):
        while True:
            for symbol in self.symbols:
                try:
                    data = self.exchange.fetch_ohlcv(symbol, self.timeframe)
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    sma10 = df['close'].rolling(window=10).mean().iloc[-1]
                    sma100 = df['close'].rolling(window=100).mean().iloc[-1]
                   Croisement vérifié pour DOGE/USDT: SMA10=0.0725, SMA100=0.0718
                    if sma10 > sma100:
                        notifier.send_message(f"🚀 Croisement haussier détecté pour {symbol}", '📈')
                        self.place_order(symbol, 'buy', 15)
                        trade_manager.log_trade(symbol, 'buy', 15, sma10, 0)
                    elif sma10 < sma100:
                        notifier.send_message(f"🔻 Croisement baissier détecté pour {symbol}", '📉')
                        self.place_order(symbol, 'sell', 15)
                        trade_manager.log_trade(symbol, 'sell', 15, sma100, 0)
                except Exception as e:
                    logging.error(f"Erreur dans la boucle de trading pour {symbol} : {e}")
                time.sleep(30)

bot = BotTrader()

# Lancer le bot dans un thread
def start_trading():
    trader_thread = Thread(target=bot.run_bot)
    trader_thread.daemon = True
    trader_thread.start()
    monitor_thread = Thread(target=bot.monitor_positions)
    monitor_thread.daemon = True
    monitor_thread.start()
    notifier.send_message("🚦 Bot de trading démarré avec succès !", '✅')

@app.route('/')
def home():
    return 'Bot de trading opérationnel!'

if __name__ == '__main__':
    start_trading()
    app.run(host='0.0.0.0', port=8080)

    app.run(host='0.0.0.0', port=8080)
