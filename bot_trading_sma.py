import ccxt
import pandas as pd
import time
import logging
import os
import requests
import json
from threading import Thread
from flask import Flask, request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Configuration logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')

    def send_message(self, message, emoji='💬', reply_markup=None):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"{emoji} {message}"
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            headers = {'Content-Type': 'application/json'}
            requests.post(url, headers=headers, data=json.dumps(payload))
        except Exception as e:
            logging.error(f"Erreur envoi Telegram : {e}")

    def send_menu(self):
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Démarrer", "callback_data": "/start"},
                    {"text": "Arrêter", "callback_data": "/stop"}
                ],
                [
                    {"text": "Statut", "callback_data": "/status"},
                    {"text": "Montant +5 USDT", "callback_data": "/increase"},
                    {"text": "Montant -5 USDT", "callback_data": "/decrease"}
                ]
            ]
        }
        self.send_message("🛠️ Menu de contrôle du bot", '📋', reply_markup=keyboard)

class BotTrader:
    def __init__(self):
        self.exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_API_SECRET')
        })
        self.symbols = ['DOGE/USDT', 'ADA/USDT']
        self.trade_amount = 5
        self.is_running = False
        self.notifier = TelegramNotifier()
        self.tp_percentage = 0.02
        self.sl_percentage = 0.01
        self.positions = []
        self.trades_file = 'trades_log.json'

    def start_bot(self):
        if not self.is_running:
            self.is_running = True
            self.notifier.send_message("🚦 Bot démarré", '🟢')
            Thread(target=self.run_bot, daemon=True).start()
            Thread(target=self.monitor_positions, daemon=True).start()

    def stop_bot(self):
        self.is_running = False
        self.notifier.send_message("🛑 Bot arrêté", '🔴')

    def run_bot(self):
        logging.info("🚀 Bot actif")
        while self.is_running:
            for symbol in self.symbols:
                try:
                    data = self.exchange.fetch_ohlcv(symbol, '1m')
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    if len(df) < 20:
                        continue

                    sma3 = df['close'].rolling(window=3).mean().iloc[-1]
                    sma20 = df['close'].rolling(window=20).mean().iloc[-1]
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=5).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=5).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]

                    if pd.isna(sma3) or pd.isna(sma20) or pd.isna(current_rsi):
                        continue

                    self.log_signal_check(symbol, sma3, sma20, current_rsi)

                    if sma3 > sma20 and current_rsi < 70:
                        self.notifier.send_message(f"🚀 Achat {symbol} SMA3={sma3:.4f}, RSI={current_rsi:.2f}", '📈')
                        self.place_order(symbol, 'buy', self.trade_amount)
                    elif sma3 < sma20 and current_rsi > 30:
                        self.notifier.send_message(f"🔻 Vente {symbol} SMA3={sma3:.4f}, RSI={current_rsi:.2f}", '📉')
                        self.place_order(symbol, 'sell', self.trade_amount)

                except Exception as e:
                    logging.error(f"Erreur run_bot pour {symbol} : {e}")
            time.sleep(5)

    def monitor_positions(self):
        while True:
            time.sleep(15)
            for pos in self.positions[:]:
                try:
                    last_price = self.exchange.fetch_ticker(pos['symbol'])['last']
                    if (pos['side'] == 'buy' and last_price >= pos['tp']) or (pos['side'] == 'sell' and last_price <= pos['tp']):
                        self.notifier.send_message(f"🎯 TP atteint pour {pos['symbol']} à {last_price}", '🎉')
                        self.positions.remove(pos)
                        # Clôturer la position
                        closing_side = 'sell' if pos['side'] == 'buy' else 'buy'
                        self.exchange.create_order(pos['symbol'], 'market', closing_side, self.trade_amount)
                    elif (pos['side'] == 'buy' and last_price <= pos['sl']) or (pos['side'] == 'sell' and last_price >= pos['sl']):
                        self.notifier.send_message(f"🔻 SL atteint pour {pos['symbol']} à {last_price}", '❌')
                        self.positions.remove(pos)
                        # Clôturer la position
                        closing_side = 'sell' if pos['side'] == 'buy' else 'buy'
                        self.exchange.create_order(pos['symbol'], 'market', closing_side, self.trade_amount)
                except Exception as e:
                    logging.error(f"Erreur monitor {pos['symbol']} : {e}")

    def place_order(self, symbol, side, amount):
        try:
            order = self.exchange.create_order(symbol, 'market', side, amount)
            price = order['price'] if 'price' in order else self.exchange.fetch_ticker(symbol)['last']
            tp = price * (1 + self.tp_percentage) if side == 'buy' else price * (1 - self.tp_percentage)
            sl = price * (1 - self.sl_percentage) if side == 'buy' else price * (1 + self.sl_percentage)
            self.positions.append({'symbol': symbol, 'side': side, 'tp': tp, 'sl': sl})
            with open(self.trades_file, 'a') as f:
                json.dump({"symbol": symbol, "side": side, "price": price, "tp": tp, "sl": sl}, f)
                f.write("\n")
        except Exception as e:
            logging.error(f"Erreur order {symbol} : {e}")

    def log_signal_check(self, symbol, sma3, sma20, rsi):
        logging.info(f"🔍 Signal check {symbol}: SMA3={sma3}, SMA20={sma20}, RSI={rsi}")

    def handle_telegram_command(self, command):
        if command == '/start':
            self.start_bot()
        elif command == '/stop':
            self.stop_bot()
        elif command == '/status':
            status = "✅ En marche" if self.is_running else "❌ Arrêté"
            self.notifier.send_message(f"Statut du bot : {status}", 'ℹ️')
        elif command == '/increase':
            self.trade_amount += 5
            self.notifier.send_message(f"💵 Montant mis à jour : {self.trade_amount} USDT")
        elif command == '/decrease':
            self.trade_amount = max(1, self.trade_amount - 5)
            self.notifier.send_message(f"💸 Montant mis à jour : {self.trade_amount} USDT")
        elif command == '/menu':
            self.notifier.send_menu()
        else:
            self.notifier.send_message("Commande non reconnue.", '❗')

bot = BotTrader()

@app.route('/')
def status():
    return "Bot de trading opérationnel"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    data = request.json
    if 'message' in data and 'text' in data['message']:
        command = data['message']['text']
        bot.handle_telegram_command(command)
    elif 'callback_query' in data:
        command = data['callback_query']['data']
        bot.handle_telegram_command(command)
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
