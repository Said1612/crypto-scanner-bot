import os
import json
import time
import requests
from datetime import datetime

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

EXCLUDED = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

tracked = {}
top_20_symbols = {}

MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/price"
MEXC_24H = "https://api.mexc.com/api/v3/ticker/24hr"

# ================= TELEGRAM =================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

# ================= TOP 20 SYMBOLS =================
def get_top_symbols():
    global top_20_symbols
    print("Fetching Top 20 symbols...")

    data = requests.get(MEXC_24H, timeout=10).json()
    candidates = []

    for s in data:
        symbol = s["symbol"]

        if (
            symbol.endswith("USDT")
            and symbol not in EXCLUDED
            and not any(x in symbol for x in ["3L", "3S", "BULL", "BEAR"])
        ):
            vol = float(s["quoteVolume"])
            change = abs(float(s["priceChangePercent"]))

            if 800_000 < vol < 20_000_000 and change < 8:
                candidates.append((symbol, vol))

    candidates.sort(key=lambda x: -x[1])
    top_20_symbols = {s[0]: None for s in candidates[:20]}

    print("Tracking:", list(top_20_symbols.keys()))

# ================= SIGNAL HANDLER =================
def handle_signal(symbol, price):
    score = 80

    if symbol in tracked:
        entry = tracked[symbol]["entry"]
        level = tracked[symbol]["level"]

        change = (price - entry) / entry * 100

        if level == 1 and change >= 2:
            send_telegram(
                f"🚀 SIGNAL #2\n💰 {symbol}\n📈 +{change:.2f}%\n💵 {price}"
            )
            tracked[symbol]["level"] = 2

        elif level == 2 and change >= 4:
            send_telegram(
                f"🔥 SIGNAL #3\n💰 {symbol}\n📈 +{change:.2f}%\n💵 {price}"
            )
            tracked[symbol]["level"] = 3

        return

    if score < 70:
        return

    send_telegram(
        f"👑 SOURCE BOT\n💰 {symbol}\n🔔 SIGNAL #1\n💵 {price}\n📊 Score: {score}"
    )

    tracked[symbol] = {
        "entry": price,
        "level": 1
    }

# ================= MAIN LOOP =================
def run_bot():
    get_top_symbols()

    while True:
        try:
            prices = requests.get(MEXC_TICKER, timeout=10).json()

            for item in prices:
                symbol = item["symbol"]
                if symbol in top_20_symbols:
                    price = float(item["price"])
                    handle_signal(symbol, price)

            time.sleep(10)

        except Exception as e:
            print("Loop Error:", e)
            time.sleep(5)

# ================= ENTRY =================
if __name__ == "__main__":
    while True:
        try:
            run_bot()
        except Exception as e:
            print("Bot crashed:", e)
            time.sleep(30)
