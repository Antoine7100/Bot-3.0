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
        self.silent_notifications = set()  # Symboles déjà notifiés pour trade ouvert

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
                ],
                [
                    {"text": "Fermer positions", "callback_data": "/closeall"}
                ],
                [
                    {"text": "🔄 Sync", "callback_data": "/sync"}
                ],
                [
                    {"text": "📊 Stats", "callback_data": "/stats"}
                ]
            ]
        }
        self.send_message("🛠️ Menu de contrôle du bot", '🕜', reply_markup=keyboard)

class BotTrader:
    def __init__(self):
        self.exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_API_SECRET'),
            'options': {'createMarketBuyOrderRequiresPrice': False}
        })
        self.symbols = config["symbols"]
        self.trade_amount = config["stake_amount"]
        self.tp_percentage = 0.012
        self.sl_percentage = 0.008
        self.trailing_percentage = 0.003  # 0.3% trailing stop
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
            # Récupère les vraies positions ouvertes sur Bybit
            open_positions = self.exchange.fetch_positions()
            open_symbols = set(
                pos['info']['symbol'] for pos in open_positions if float(pos['info']['size']) > 0
            )

            before = len(self.positions)
            self.positions = [p for p in self.positions if p['symbol'].replace("/", "") in open_symbols]
            after = len(self.positions)

            self.notifier.send_message(f"🔁 Sync terminée. Avant: {before}, Après: {after}")
        except Exception as e:
            logging.error(f"Erreur de synchronisation : {e}")
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

    def start_bot(self):
        if not self.is_running:
            logging.info("✅ start_bot() appelé")
            self.is_running = True
            self.notifier.send_message("🚦 Le bot a bien été lancé et commence à analyser les marchés.", '🟢')
            Thread(target=self.run_bot, daemon=True).start()
            Thread(target=self.monitor_positions, daemon=True).start()
        else:
            self.notifier.send_message("⚠️ Le bot est déjà en marche.")
    
    def enter_trade(self, symbol, side='buy'):
        try:
            price = self.exchange.fetch_ticker(symbol)['last']
            adjusted_amount = max(5 / price, self.trade_amount)
            order_value = price * adjusted_amount

            if order_value < 5:
                return

            tp = price * (1 + self.tp_percentage) if side == 'buy' else price * (1 - self.tp_percentage)
            sl = price * (1 - self.sl_percentage) if side == 'buy' else price * (1 + self.sl_percentage)

            order = self.exchange.create_order(symbol, 'market', side, adjusted_amount)

            if order:
                self.positions.append({
                    'symbol': symbol,
                    'side': side,
                    'entry': price,
                    'tp': tp,
                    'sl': sl,
                    'amount': adjusted_amount
                })
                self.notifier.send_message(f"📈 {side.upper()} {symbol} à {price:.4f} | TP: {tp:.4f}, SL: {sl:.4f}", '💥')
            else:
                self.notifier.send_message(f"⚠️ Échec ouverture position pour {symbol} (aucune réponse de Bybit)", "❗")

        except Exception as e:
            logging.error(f"Erreur d'ouverture de trade {symbol} : {e}")
            self.notifier.send_message(f"❌ Erreur d'ouverture de trade pour {symbol} : {e}", '⚠️')

    def stop_bot(self):
        self.is_running = False
        self.notifier.send_message("🔝 Bot arrêté", '🔴')

    def close_all_positions(self):
        if not self.positions:
            self.notifier.send_message("❗Aucune position à fermer.")
            return

        for pos in self.positions[:]:
            try:
                price = self.exchange.fetch_ticker(pos['symbol'])['last']
                adjusted_amount = max(5 / price, pos['amount'])
                order_value = price * adjusted_amount

                if order_value < 5:
                    logging.warning(f"❌ Fermeture ignorée : {pos['symbol']}, montant trop faible ({order_value:.2f} USDT)")
                    self.notifier.send_message(f"❌ Montant trop faible pour clôturer {pos['symbol']} ({order_value:.2f} USDT).", "⚠️")
                    continue

                closing_side = 'sell' if pos['side'] == 'buy' else 'buy'
                self.exchange.create_order(pos['symbol'], 'market', closing_side, adjusted_amount)
                self.positions.remove(pos)
                self.notifier.send_message(f"🔒 Fermeture manuelle de {pos['symbol']} ({pos['side']})")
            except Exception as e:
                logging.error(f"❌ Erreur fermeture {pos['symbol']} : {e}")
                self.notifier.send_message(f"❌ Erreur fermeture {pos['symbol']} : {e}", '⚠️')

    def run_bot(self):
        while self.is_running:
            for symbol in self.symbols:
                try:
                    data = self.exchange.fetch_ohlcv(symbol, '1m', limit=30)
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                    df['ema5'] = df['close'].ewm(span=5).mean()
                    df['ema20'] = df['close'].ewm(span=20).mean()
                    df['high_break'] = df['high'].rolling(window=10).max()
                    df['low_break'] = df['low'].rolling(window=10).min()
                    delta = df['close'].diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = -delta.where(delta < 0, 0).rolling(14).mean()
                    rs = gain / loss
                    df['rsi'] = 100 - (100 / (1 + rs))

                    price = df['close'].iloc[-1]
                    high_break = df['high_break'].iloc[-2]
                    low_break = df['low_break'].iloc[-2]
                    ema5 = df['ema5'].iloc[-1]
                    ema20 = df['ema20'].iloc[-1]
                    rsi = df['rsi'].iloc[-1]
                    volume = df['volume'].iloc[-1]
                    avg_volume = df['volume'].mean()

                    if price > high_break and ema5 > ema20 and rsi > 60 and volume > avg_volume * 1.2:
                        self.enter_trade(symbol, 'buy')
                    elif price < low_break and ema5 < ema20 and rsi < 40 and volume > avg_volume * 1.2:
                        self.enter_trade(symbol, 'sell')
                except Exception as e:
                    logging.error(f"Erreur run_bot pour {symbol} : {e}")
            time.sleep(10)



    def monitor_positions(self):
        while self.is_running:
            for pos in self.positions[:]:
                try:
                    last_price = self.exchange.fetch_ticker(pos['symbol'])['last']

                    if pos['side'] == 'buy' and last_price > pos['entry']:
                        new_sl = last_price * (1 - self.trailing_percentage)
                        if new_sl > pos['sl']:
                            pos['sl'] = new_sl
                    elif pos['side'] == 'sell' and last_price < pos['entry']:
                        new_sl = last_price * (1 + self.trailing_percentage)
                        if new_sl < pos['sl']:
                            pos['sl'] = new_sl

                    if (pos['side'] == 'buy' and last_price >= pos['tp']) or \
                       (pos['side'] == 'sell' and last_price <= pos['tp']):
                        msg = f"✅ TP atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.win_count += 1
                        self.save_stats()
                        close = True
                    elif (pos['side'] == 'buy' and last_price <= pos['sl']) or \
                         (pos['side'] == 'sell' and last_price >= pos['sl']):
                        msg = f"⛔ SL atteint pour {pos['symbol']} à {last_price:.4f}"
                        self.loss_count += 1
                        self.save_stats()
                        close = True
                    else:
                        close = False

                    if close:
                        side = 'sell' if pos['side'] == 'buy' else 'buy'
                        self.exchange.create_order(pos['symbol'], 'market', side, pos['amount'])
                        self.positions.remove(pos)
                        self.notifier.send_message(msg, '📤')
                except Exception as e:
                    logging.error(f"Erreur monitor pour {pos['symbol']} : {e}")
            time.sleep(15)


    def place_order(self, symbol, side, amount):
        try:
            price = self.exchange.fetch_ticker(symbol)['last']
            order_value = price * amount
            min_order_usdt = 5

            if order_value < min_order_usdt:
                logging.warning(f"❌ Ordre ignoré : {symbol}, montant trop faible ({order_value:.2f} USDT)")
                return

            logging.info(f"📤 Envoi ordre {side.upper()} sur {symbol} avec {amount} USDT")
            order = self.exchange.create_order(symbol, 'market', side, amount)
            logging.info(f"✅ Réponse de Bybit : {order}")

            price = order.get('price', price)
            tp = price * (1 + self.tp_percentage) if side == 'buy' else price * (1 - self.tp_percentage)
            sl = price * (1 - self.sl_percentage) if side == 'buy' else price * (1 + self.sl_percentage)

            self.positions.append({'symbol': symbol, 'side': side, 'tp': tp, 'sl': sl})
            with open(self.trades_file, 'a') as f:
                json.dump({"symbol": symbol, "side": side, "price": price, "tp": tp, "sl": sl}, f)
                f.write("\n")

            self.notifier.send_message(
                f"✅ Nouvelle position {side.upper()} sur {symbol} à {price:.4f}\n🎯 TP: {tp:.4f} / 🛑 SL: {sl:.4f}",
                emoji="📌"
            )

        except Exception as e:
            logging.error(f"❌ Erreur order {symbol} : {e}")
            self.notifier.send_message(f"❌ Erreur ordre {symbol} : {e}", emoji="⚠️")

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
                    f"📊 *Statistiques du bot* :\n"
                    f"✅ Trades gagnants : {self.win_count}\n"
                    f"❌ Trades perdants : {self.loss_count}\n"
                    f"📈 Taux de réussite : {success_rate:.2f}%"
                )
            else:
                msg = "📊 Aucune statistique disponible pour l’instant."
            self.notifier.send_message(msg, '📊')


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
