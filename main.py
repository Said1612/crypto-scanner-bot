import requests
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://api.binance.com/api/v3"
INTERVAL = "5m"
LIMIT = 50
COOLDOWN = 1800
SCAN_INTERVAL = 300

sent_coins = {}
signal_counter = {}

# ================= TELEGRAM =================

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=10)
    except:
        pass

# ================= INDICATORS =================

def calculate_rsi(closes, period=14):
    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(closes, period=20):
    multiplier = 2 / (period + 1)
    ema = closes[0]

    for price in closes:
        ema = (price - ema) * multiplier + ema

    return ema

# ================= SYMBOLS =================

def get_symbols():
    try:
        r = requests.get(f"{BASE_URL}/exchangeInfo", timeout=10)
        data = r.json()

        if "symbols" not in data:
            return []

        return [
            s["symbol"] for s in data["symbols"]
            if s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
            and not s["symbol"].endswith("UPUSDT")
            and not s["symbol"].endswith("DOWNUSDT")
        ]
    except:
        return []

# ================= CHECK =================

def check_liquidity(symbol):
    try:
        # 24h volume filter
        ticker = requests.get(f"{BASE_URL}/ticker/24hr?symbol={symbol}", timeout=10).json()
        if float(ticker["quoteVolume"]) < 5_000_000:
            return None

        params = {"symbol": symbol, "interval": INTERVAL, "limit": LIMIT}
        data = requests.get(f"{BASE_URL}/klines", params=params, timeout=10).json()

        if not isinstance(data, list) or len(data) < LIMIT:
            return None

        volumes = [float(c[5]) for c in data]
        closes = [float(c[4]) for c in data]

        last_volume = volumes[-1]
        avg_volume = sum(volumes[-21:-1]) / 20

        price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100

        rsi = calculate_rsi(closes)
        ema20 = calculate_ema(closes)

        if (
            last_volume > avg_volume * 2.5 and
            price_change > 1.5 and
            45 < rsi < 75 and
            closes[-1] > ema20
        ):
            strength = "🚀 STRONG SIGNAL" if price_change > 2.5 else "⚡ NORMAL SIGNAL"

            return closes[-1], price_change, rsi, strength

        return None

    except:
        return None

# ================= SCANNER =================

def scanner():
    print("Smart Liquidity Engine v2 Started...")

    while True:
        symbols = get_symbols()

        for symbol in symbols:
            result = check_liquidity(symbol)

            if result:
                price, change, rsi, strength = result
                now = time.time()

                if symbol in sent_coins and now - sent_coins[symbol] < COOLDOWN:
                    continue

                sent_coins[symbol] = now
                signal_counter[symbol] = signal_counter.get(symbol, 0) + 1

                message = f"""
👑 <b>SOURCE BOT PRO</b> 👑

💲 <b>#{symbol}</b>
🔔 SIGNAL #{signal_counter[symbol]}

💵 Price: ${round(price,6)}
📈 5m Change: {round(change,2)}%
📊 RSI: {round(rsi,1)}

{strength}

────────────────────
⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC
"""

                send_message(message)

            time.sleep(0.15)

        print("Cycle complete...")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    scanner()
