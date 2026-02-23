import requests
import time
import os
from datetime import datetime

# ==============================
# CONFIG
# ==============================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://api.binance.com/api/v3"
INTERVAL = "5m"
LIMIT = 25
COOLDOWN = 1800  # 30 minutes
SLEEP_BETWEEN_SYMBOLS = 0.2
SCAN_INTERVAL = 300  # 5 minutes

sent_coins = {}
signal_counter = {}

# ==============================
# TELEGRAM
# ==============================

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

# ==============================
# GET SYMBOLS (SAFE VERSION)
# ==============================

def get_symbols():
    try:
        response = requests.get(f"{BASE_URL}/exchangeInfo", timeout=10)
        data = response.json()

        if "symbols" not in data:
            print("Error fetching symbols:", data)
            return []

        symbols = [
            s["symbol"] for s in data["symbols"]
            if s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
            and not s["symbol"].endswith("UPUSDT")
            and not s["symbol"].endswith("DOWNUSDT")
        ]

        return symbols

    except Exception as e:
        print("Exception in get_symbols:", e)
        return []

# ==============================
# CHECK LIQUIDITY
# ==============================

def check_liquidity(symbol):
    try:
        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "limit": LIMIT
        }

        response = requests.get(f"{BASE_URL}/klines", params=params, timeout=10)
        data = response.json()

        if not isinstance(data, list) or len(data) < LIMIT:
            return None

        volumes = [float(c[5]) for c in data]
        closes = [float(c[4]) for c in data]

        last_volume = volumes[-1]
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])

        price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100

        # شرط دخول سيولة
        if last_volume > avg_volume * 2 and abs(price_change) >= 1.2:
            direction = "🟢 BULLISH" if price_change > 0 else "🔴 BEARISH"
            return last_volume, price_change, closes[-1], direction

        return None

    except Exception as e:
        print(f"Error checking {symbol}:", e)
        return None

# ==============================
# SCANNER LOOP
# ==============================

def scanner():
    print("Bot Started...")

    while True:
        symbols = get_symbols()

        if not symbols:
            print("No symbols fetched. Retrying in 60 sec...")
            time.sleep(60)
            continue

        print(f"Scanning {len(symbols)} symbols...")

        for symbol in symbols:
            result = check_liquidity(symbol)

            if result:
                last_volume, price_change, price, direction = result
                now = time.time()

                if symbol in sent_coins:
                    if now - sent_coins[symbol] < COOLDOWN:
                        continue

                sent_coins[symbol] = now

                if symbol not in signal_counter:
                    signal_counter[symbol] = 1
                else:
                    signal_counter[symbol] += 1

                signal_number = signal_counter[symbol]

                message = f"""
👑 <b>SOURCE BOT</b> 👑

💲 <b>#{symbol}</b>
🔔 <b>SIGNAL #{signal_number}</b>

💵 Price: ${round(price,6)}
📈 Change (5m): {round(price_change,2)}%
📊 Volume Spike: x{round(last_volume,2)}
{direction}

────────────────────
🌍 NEWS: No events found
⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC
"""

                send_message(message)

            time.sleep(SLEEP_BETWEEN_SYMBOLS)

        print("Scan complete. Sleeping...")
        time.sleep(SCAN_INTERVAL)


# ==============================
# START
# ==============================

if __name__ == "__main__":
    scanner()
