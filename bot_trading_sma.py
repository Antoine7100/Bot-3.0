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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Configuration du serveur Flask
app = Flask(__name__)

# Configuration du fichier de log
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_fetch_ohlcv(symbol='DOGE/USDT', timeframe='1m'):
    try:
        exchange = ccxt.bybit({'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_API_SECRET')})
        logging.info(f"🔍 Test de récupération des données OHLCV pour {symbol} avec la période {timeframe}")
        data = exchange.fetch_ohlcv(symbol, timeframe)
        if data and len(data) > 0:
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            logging.info(f"✅ Données récupérées pour {symbol} :\n{df.tail()}")
            print(df.tail())
        else:
            logging.warning(f"⚠️ Aucune donnée OHLCV récupérée pour {symbol}")
    except Exception as e:
        logging.error(f"❗ Erreur lors de la récupération des données OHLCV pour {symbol} : {e}")
        print(f"❗ Erreur : {e}")

# Test direct de la récupération des données OHLCV
test_fetch_ohlcv()

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
    def reset_daily_loss(self):
        self.daily_loss = 0
        self.current_day = time.strftime('%Y-%m-%d')
        logging.info("🔄 Réinitialisation de la perte journalière.")

    def update_daily_loss(self, loss):
        self.daily_loss += loss
        if self.daily_loss >= self.daily_loss_limit:
            logging.warning("🚫 Limite de perte journalière atteinte, arrêt des trades pour aujourd'hui.")
            notifier.send_message("🚫 Limite de perte journalière atteinte, arrêt des trades.", '❗')
            self.stop_bot()
            return False
        return True

class BotTrader:
    def __init__(self):
        self.exchange = ccxt.bybit({'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_API_SECRET')})
        self.symbols = ['DOGE/USDT', 'ADA/USDT']
        self.timeframe = '5m'
        self.tp_percentage = 0.02
        self.sl_percentage = 0.01
        self.trade_amount = 5
        self.is_running = False
        self.daily_loss_limit = 100
        self.daily_loss = 0
        self.current_day = time.strftime('%Y-%m-%d')
        self.notifier = TelegramNotifier()
        self.check_api_connection()

    def check_api_connection(self):
        try:
            balance = self.exchange.fetch_balance()
            logging.info("✅ API Bybit connectée avec succès.")
        except Exception as e:
            logging.error(f"❗ Erreur de connexion API Bybit : {e}")
            self.notifier.send_message("❗ Erreur de connexion API Bybit", '⚠️')

    def log_signal_check(self, symbol, sma10, sma100, rsi):
        logging.info(f"🔍 Vérification du signal pour {symbol} : SMA10={sma10}, SMA100={sma100}, RSI={rsi}")

        
    def start_bot(self):
        self.is_running = True
        notifier.send_message("🚦 Bot démarré via Telegram.", '✅')

    def stop_bot(self):
        self.is_running = False
        notifier.send_message("🛑 Bot arrêté via Telegram.", '❌')

    def change_trade_amount(self, amount):
        self.trade_amount = amount
        notifier.send_message(f"🔧 Montant de trade mis à jour : {amount} USDT", '⚙️')

    def get_status(self):
        status = "✅ En marche" if self.is_running else "❌ Arrêté"
        return f"Bot status: {status}, Montant de trade: {self.trade_amount} USDT"

    def get_open_trades(self):
        try:
            open_trades = trade_manager.positions
            if not open_trades:
                return "📂 Aucun trade en cours."
            trade_list = "📊 Trades en cours :\n"
            for trade in open_trades:
                trade_list += f"- {trade['symbol']} | {trade['side']} | Montant: {trade['amount']} USDT | Prix: {trade['entry_price']}\n"
            return trade_list
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des trades en cours : {e}")
            return "❗ Erreur lors de la récupération des trades."

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
                            self.stop_bot()
                except Exception as e:
                    logging.error(f"Erreur lors de la vérification TP/SL : {e}")
            time.sleep(30)

    def place_order(self, symbol, side, amount):
        try:
            order = self.exchange.create_order(symbol, 'market', side, amount)
            entry_price = order['price'] if 'price' in order else self.exchange.fetch_ticker(symbol)['last']
            tp, sl = self.calculate_tp_sl(entry_price)
            trade_manager.positions.append({'symbol': symbol, 'side': side, 'amount': amount, 'entry_price': entry_price, 'tp': tp, 'sl': sl})
            trade_manager.save_data()
            notifier.send_message(f"✅ Ordre {side} exécuté pour {symbol} avec {amount} USDT | TP: {tp} | SL: {sl}", '📈' if side == 'buy' else '📉')
            logging.info(f"✅ Ordre {side} exécuté pour {symbol} avec montant {amount} USDT, TP: {tp}, SL: {sl}")
            return order
        except Exception as e:
            logging.error(f"❗ Erreur lors du passage d'ordre pour {symbol}: {e}")
            notifier.send_message(f"❗ Erreur lors du passage d'ordre pour {symbol}: {e}", '⚠️')
            return None

 def run_bot(self):
        while self.is_running:
            for symbol in self.symbols:
                try:
                    data = self.exchange.fetch_ohlcv(symbol, self.timeframe)
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    sma10 = df['close'].rolling(window=10).mean().iloc[-1]
                    sma100 = df['close'].rolling(window=100).mean().iloc[-1]

                    # Calcul du RSI sur 14 périodes
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]

                    self.log_signal_check(symbol, sma10, sma100, current_rsi)

                    logging.info(f"✅ SMA10: {sma10}, SMA100: {sma100}, RSI: {current_rsi}")

                    # Stratégie agressive SMA + RSI
                    if sma10 > sma100 and current_rsi < 50:
                        logging.info(f"🚀 Signal agressif d'achat pour {symbol}: SMA10={sma10}, SMA100={sma100}, RSI={current_rsi}")
                        notifier.send_message(f"🚀 Signal d'achat pour {symbol}", '📈')
                        self.place_order(symbol, 'buy', self.trade_amount)
                    elif sma10 < sma100 and current_rsi > 50:
                        logging.info(f"🔻 Signal agressif de vente pour {symbol}: SMA10={sma10}, SMA100={sma100}, RSI={current_rsi}")
                        notifier.send_message(f"🔻 Signal de vente pour {symbol}", '📉')
                        self.place_order(symbol, 'sell', self.trade_amount)
                    else:
                        logging.info(f"🔍 Aucun signal détecté pour {symbol}: SMA10={sma10}, SMA100={sma100}, RSI={current_rsi}")

                except Exception as e:
                    logging.error(f"Erreur lors de la récupération des données pour {symbol} : {e}")
                    self.notifier.send_message(f"⚠️ Erreur lors de la récupération des données pour {symbol}", '❗')
                time.sleep(30)


    def send_menu(self):
        keyboard = [[
            InlineKeyboardButton("Démarrer", callback_data='/start'),
            InlineKeyboardButton("Arrêter", callback_data='/stop')
        ], [
            InlineKeyboardButton("Statut", callback_data='/status'),
            InlineKeyboardButton("Trades en cours", callback_data='/trades')
        ], [
            InlineKeyboardButton("Montant 5 USDT", callback_data='/set_amount 5'),
            InlineKeyboardButton("Montant 10 USDT", callback_data='/set_amount 10')
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        notifier.send_message("🛠️ Menu de contrôle", reply_markup=reply_markup)

    def telegram_control(self, message):
        try:
            if message == '/menu':
                self.send_menu()
            elif message == '/start':
                self.start_bot()
            elif message == '/stop':
                self.stop_bot()
            elif message == '/trades':
                open_trades = self.get_open_trades()
                notifier.send_message(open_trades)
            elif message.startswith('/set_amount '):
                amount = int(message.split(' ')[1])
                self.change_trade_amount(amount)
            elif message == '/status':
                status = self.get_status()
                notifier.send_message(status)
            else:
                notifier.send_message("Commande non reconnue. Utilisez /menu pour voir les options.", '❗')
        except Exception as e:
            logging.error(f"Erreur de traitement de la commande Telegram : {e}")

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
