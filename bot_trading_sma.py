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
from datetime import datetime

# Chargement de la config
with open("config.json") as f:
    config = json.load(f)

# Chargement des stats
if os.path.exists("stats.json"):
    with open("stats.json") as sf:
        saved_stats = json.load(sf)
else:
    saved_stats = {"win_count": 0, "loss_count": 0}

# Configuration logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.silent_notifications = set()

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
            logging.warning(f"Erreur Telegram ignorée : {e}")

    def send_menu(self):
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "▶️ Démarrer", "callback_data": "/start"},
                    {"text": "⏹️ Arrêter", "callback_data": "/stop"}
                ],
                [
                    {"text": "📊 Statut", "callback_data": "/status"},
                    {"text": "💵 +5 USDT", "callback_data": "/increase"},
                    {"text": "💸 -5 USDT", "callback_data": "/decrease"}
                ],
                [
                    {"text": "📂 Positions", "callback_data": "/positions"},
                    {"text": "📈 Stats", "callback_data": "/stats"}
                ],
                [
                    {"text": "🔁 Sync", "callback_data": "/sync"},
                    {"text": "❌ Fermer positions", "callback_data": "/closeall"}
                ]
            ]
        }
        self.send_message("🛠️ Menu de contrôle du bot", '🧠', reply_markup=keyboard)

class BotTrader:
    def __init__(self):
        self.exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_API_SECRET'),
            'options': {'createMarketBuyOrderRequiresPrice': False}
        })
        self.symbols = [s for s in config["symbols"] if not s.startswith("ADA")]
        self.trade_amount = config["stake_amount"]
        self.tp_percentage = 0.012
        self.sl_percentage = 0.008
        self.trailing_percentage = 0.003
        self.trades_file = config["trades_file"]
        self.is_running = False
        self.notifier = TelegramNotifier()
        self.positions = []
        self.win_count = saved_stats.get("win_count", 0)
        self.loss_count = saved_stats.get("loss_count", 0)

    def save_stats(self):
        with open("stats.json", "w") as f:
            json.dump({"win_count": self.win_count, "loss_count": self.loss_count}, f)

    def sync_with_exchange(self):
        try:
            open_positions = self.exchange.fetch_positions()
            synced = 0
            self.positions = []

            for pos in open_positions:
                size = float(pos['info'].get('size', 0))
                entry_price = float(pos['info'].get('entryPrice', 0))
                if size == 0 or entry_price == 0:
                    continue  # Ignore les positions sans taille ou sans prix d'entrée

                symbol = pos['symbol'].replace("USDT", "/USDT")
                side = 'buy' if pos['info']['side'].lower() == 'buy' else 'sell'
                amount = size

                tp = entry_price * (1 + self.tp_percentage) if side == 'buy' else entry_price * (1 - self.tp_percentage)
                sl = entry_price * (1 - self.sl_percentage) if side == 'buy' else entry_price * (1 + self.sl_percentage)

                self.positions.append({
                    'symbol': symbol,
                    'side': side,
                    'entry': entry_price,
                    'tp': tp,
                    'sl': sl,
                    'amount': amount
                })
                synced += 1

            self.notifier.send_message(f"🔄 Synchronisation terminée. {synced} positions valides récupérées depuis Bybit.")
        except Exception as e:
            logging.error(f"Erreur sync_with_exchange : {e}")
            self.notifier.send_message("❌ Erreur lors de la synchronisation avec Bybit.")

    def start_bot(self):
        if not self.is_running:
            self.is_running = True
            self.sync_with_exchange()
            self.notifier.send_message("🚦 Bot Smart Scalper lancé", '🟢')
            Thread(target=self.run_bot, daemon=True).start()
            Thread(target=self.monitor_positions, daemon=True).start()
        else:
            self.notifier.send_message("⚠️ Le bot est déjà en marche.")

    def enter_trade(self, symbol, side='buy'):
        if any(p['symbol'] == symbol and p['side'] == side for p in self.positions):
            if symbol not in self.notifier.silent_notifications:
                self.notifier.send_message(f"⚠️ ❌ Trade déjà ouvert pour {symbol} ({side})")
                self.notifier.silent_notifications.add(symbol)
            return

        try:
            price = self.exchange.fetch_ticker(symbol)['last']
            adjusted_amount = max(5 / price, self.trade_amount)
            order_value = price * adjusted_amount

            if order_value < 5:
                return

            self.exchange.create_order(symbol, 'market', side, adjusted_amount)

            tp = price * (1 + self.tp_percentage) if side == 'buy' else price * (1 - self.tp_percentage)
            sl = price * (1 - self.sl_percentage) if side == 'buy' else price * (1 + self.sl_percentage)

            self.positions.append({
                'symbol': symbol,
                'side': side,
                'entry': price,
                'tp': tp,
                'sl': sl,
                'amount': adjusted_amount
            })

            self.notifier.send_message(f"🛒 Nouvelle position {side.upper()} sur {symbol} à {price:.4f}", '🟢')

        except Exception as e:
            logging.error(f"Erreur lors de l'entrée en position pour {symbol} : {e}")
            

def monitor_positions(self):
    while self.is_running:
        try:
            for pos in self.positions[:]:
                last_price = self.exchange.fetch_ticker(pos['symbol'])['last']

                close = False
                msg = ""

                if pos['side'] == 'buy':
                    if last_price >= pos['tp']:
                        msg = f"✅ TP atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.win_count += 1
                        close = True
                    elif last_price <= pos['sl']:
                        msg = f"⛔ SL atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.loss_count += 1
                        close = True

                elif pos['side'] == 'sell':
                    if last_price <= pos['tp']:
                        msg = f"✅ TP atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.win_count += 1
                        close = True
                    elif last_price >= pos['sl']:
                        msg = f"⛔ SL atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.loss_count += 1
                        close = True

                if close:
                    opposite = 'sell' if pos['side'] == 'buy' else 'buy'
                    try:
                        self.exchange.create_order(pos['symbol'], 'market', opposite, pos['amount'])
                        self.positions.remove(pos)
                        self.notifier.send_message(msg, '📤')
                        self.save_stats()
                    except Exception as e:
                        logging.error(f"Erreur lors de la clôture de {pos['symbol']} : {e}")
        except Exception as e:
            logging.error(f"Erreur monitor_positions : {e}")
        time.sleep(15)

    def run_bot(self):
        self.is_running = True

        while self.is_running:
            for symbol in self.symbols:
                try:
                    if any(p['symbol'] == symbol for p in self.positions):
                        continue

                    df1 = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, '1m', limit=50), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df5 = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                    # Indicators
                    df1['ema5'] = df1['close'].ewm(span=5).mean()
                    df1['ema20'] = df1['close'].ewm(span=20).mean()
                    delta = df1['close'].diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = -delta.where(delta < 0, 0).rolling(14).mean()
                    rs = gain / loss
                    df1['rsi'] = 100 - (100 / (1 + rs))
                    df1['ema12'] = df1['close'].ewm(span=12).mean()
                    df1['ema26'] = df1['close'].ewm(span=26).mean()
                    df1['macd'] = df1['ema12'] - df1['ema26']
                    df1['signal'] = df1['macd'].ewm(span=9).mean()
                    df1['high_break'] = df1['high'].rolling(window=10).max()
                    df1['low_break'] = df1['low'].rolling(window=10).min()
                    ha_close = (df1['open'] + df1['high'] + df1['low'] + df1['close']) / 4
                    ha_open = (df1['open'].shift(1) + df1['close'].shift(1)) / 2
                    df1['ha_open'] = ha_open
                    df1['ha_close'] = ha_close

                    df5['ema5'] = df5['close'].ewm(span=5).mean()
                    df5['ema20'] = df5['close'].ewm(span=20).mean()

                    price = df1['close'].iloc[-1]
                    ema5 = df1['ema5'].iloc[-1]
                    ema20 = df1['ema20'].iloc[-1]
                    rsi = df1['rsi'].iloc[-1]
                    macd = df1['macd'].iloc[-1]
                    signal_macd = df1['signal'].iloc[-1]
                    ha_color = "green" if df1['ha_close'].iloc[-1] > df1['ha_open'].iloc[-1] else "red"
                    volume = df1['volume'].iloc[-1]
                    high_break = df1['high_break'].iloc[-2]
                    low_break = df1['low_break'].iloc[-2]
                    bullish_5m = df5['ema5'].iloc[-1] > df5['ema20'].iloc[-1]
                    bearish_5m = df5['ema5'].iloc[-1] < df5['ema20'].iloc[-1]

                    if (price > high_break and
                        ema5 > ema20 and
                        rsi > 55 and
                        macd > signal_macd and
                        ha_color == "green" and
                        bullish_5m and
                        volume > 100):
                        self.enter_trade(symbol, 'buy')

                    elif (price < low_break and
                          ema5 < ema20 and
                          rsi < 45 and
                          macd < signal_macd and
                          ha_color == "red" and
                          bearish_5m and
                          volume > 100):
                        self.enter_trade(symbol, 'sell')

                except Exception as e:
                    logging.error(f"Erreur run_bot pour {symbol} : {e}")
            time.sleep(12)
    def handle_telegram_command(self, command):
        if command == '/start':
            self.start_bot()

        elif command == '/stop':
            self.is_running = False
            self.notifier.send_message("⛔ Bot arrêté", '🔴')

        elif command == '/status':
            running = "✅ Actif" if self.is_running else "❌ Inactif"
            infos = f"Statut : {running}\nMontant par trade : {self.trade_amount} USDT\nPositions : {len(self.positions)}"
            self.notifier.send_message(infos, 'ℹ️')

        elif command == '/menu':
            self.notifier.send_menu()

        elif command == '/sync':
            self.sync_with_exchange()

        elif command == '/increase':
            self.trade_amount += 5
            self.notifier.send_message(f"💵 Nouveau montant : {self.trade_amount} USDT")

        elif command == '/decrease':
            self.trade_amount = max(5, self.trade_amount - 5)
            self.notifier.send_message(f"💸 Nouveau montant : {self.trade_amount} USDT")

        elif command == '/closeall':
            for pos in self.positions[:]:
                try:
                    side = 'sell' if pos['side'] == 'buy' else 'buy'
                    self.exchange.create_order(pos['symbol'], 'market', side, pos['amount'])
                    self.positions.remove(pos)
                    self.notifier.send_message(f"🔐 Fermeture forcée de {pos['symbol']}", '⚠️')
                except Exception as e:
                    logging.error(f"Erreur fermeture forcée {pos['symbol']} : {e}")

        elif command == '/stats':
            total = self.win_count + self.loss_count
            if total > 0:
                success_rate = (self.win_count / total) * 100
                msg = (
                    f"📊 Statistiques du bot :\n"
                    f"✅ Trades gagnants : {self.win_count}\n"
                    f"❌ Trades perdants : {self.loss_count}\n"
                    f"📈 Taux de réussite : {success_rate:.2f}%"
                )
            else:
                msg = "📊 Aucune statistique disponible pour l’instant."
            self.notifier.send_message(msg, '📊')

        elif command == '/positions':
            if not self.positions:
                self.notifier.send_message("📭 Aucune position ouverte pour l'instant.", '📌')
            else:
                msg = "📂 *Positions en cours* :\n"
                for pos in self.positions:
                    msg += (
                        f"🔹 {pos['symbol']} - {pos['side'].upper()}\n"
                        f"  🎯 Entrée : {pos['entry']:.4f}\n"
                        f"  📈 TP : {pos['tp']:.4f} | 🛑 SL : {pos['sl']:.4f}\n"
                        f"  💰 Montant : {pos['amount']:.3f}\n\n"
                    )
                self.notifier.send_message(msg, '📍')

        else:
            self.notifier.send_message("Commande non reconnue.", '❗')      
bot = BotTrader()

@app.route('/')
def status():
    logging.info("📱 Ping reçu (UptimeRobot)")
    return "Bot de trading opérationnel"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    data = request.json
    logging.info(f"📩 Reçu de Telegram : {json.dumps(data)}")

    if 'message' in data and 'text' in data['message']:
        command = data['message']['text']
        bot.handle_telegram_command(command)
    elif 'callback_query' in data:
        command = data['callback_query']['data']
        bot.handle_telegram_command(command)

    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
