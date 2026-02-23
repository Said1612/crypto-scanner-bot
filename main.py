import requests
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://api.binance.com/api/v3"
COOLDOWN = 1800  # 30 minutes
sent_coins = {}
signal_count = {}

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

def get_symbols():
    data = requests.get(f"{BASE_URL}/exchangeInfo").json()
    return [
        s["symbol"] for s in data["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    ]

def check_liquidity(symbol):
    params = {"symbol": symbol, "interval": "5m", "limit": 25}
    data = requests.get(f"{BASE_URL}/klines", params=params).json()

    if len(data) < 25:
        return None

    volumes = [float(c[5]) for c in data]
    closes = [float(c[4]) for c in data]

    last_volume = volumes[-1]
    avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
    price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100

    if last_volume > avg_volume * 2 and price_change >= 1.2:
        return last_volume, price_change, closes[-1]

    return None

def scanner():
    symbols = get_symbols()
    print(f"Scanning {len(symbols)} SPOT pairs...")

    while True:
        for symbol in symbols:
            try:
                result = check_liquidity(symbol)

                if result:
                    last_volume, price_change, price = result
                    now = time.time()

                    if symbol in sent_coins:
                        if now - sent_coins[symbol] < COOLDOWN:
                            continue

                    sent_coins[symbol] = now

                    if symbol not in signal_count:
                        signal_count[symbol] = 1
                    else:
                        signal_count[symbol] += 1

                    signal_number = signal_count[symbol]

                    message = f"""
👑 <b>SOURCE BOT</b> 👑

💲 <b>#{symbol}</b> 🔔 <b>SIGNAL #{signal_number}</b>

💵 Price: ${round(price,6)}
📈 Price Increase: {round(price_change,2)}%
📊 Volume Spike: x{round(last_volume,2)}

──────────────────
🌍 NEWS: No events found
⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC
"""

                    send_message(message)
                    time.sleep(0.5)

            except Exception as e:
                print("Error:", e)
                continue

        time.sleep(300)

if __name__ == "__main__":
    scanner()
