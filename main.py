import requests
import os
import time
from datetime import datetime, timedelta
import statistics

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TIMEFRAME = "15m"
COOLDOWN_MINUTES = 60
SLEEP_BETWEEN_SYMBOLS = 0.05
CYCLE_SLEEP = 180

last_alert_time = {}

EXCLUDED = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

# ================= TELEGRAM =================

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ================= MEXC SYMBOLS =================

def get_symbols():
    """
    Get ALL USDT pairs (not top volume)
    """
    url = "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        data = requests.get(url, timeout=10).json()

        symbols = [
            s["symbol"]
            for s in data
            if s["symbol"].endswith("USDT")
            and not any(x in s["symbol"] for x in ["3L", "3S", "BULL", "BEAR"])
            and s["symbol"] not in EXCLUDED
            and float(s["quoteVolume"]) > 300000   # سيولة مقبولة
            and float(s["quoteVolume"]) < 20000000 # ليست عملات ضخمة
        ]

        print(f"Scanning {len(symbols)} symbols...")
        return symbols

    except Exception as e:
        print("Error fetching symbols:", e)
        return []

# ================= INDICATORS =================

def calculate_rsi(closes, period=14):
    gains = []
    losses = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger_width(closes, period=20):
    sma = sum(closes[-period:]) / period
    std = statistics.stdev(closes[-period:])
    upper = sma + (2 * std)
    lower = sma - (2 * std)
    width = ((upper - lower) / sma) * 100
    return width

# ================= CORE LOGIC =================

def check_symbol(symbol):

    klines = get_klines(symbol, TIMEFRAME)
    if not klines or len(klines) < 30:
        return

    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]

    # Range Compression
    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])
    range_percent = ((recent_high - recent_low) / recent_low) * 100

    # RSI
    rsi = calculate_rsi(closes)

    # Bollinger
    bb_width = bollinger_width(closes)

    # Volume build
    gradual = volumes[-3] < volumes[-2] < volumes[-1]

    avg_volume = sum(volumes[-20:-1]) / 19
    volume_percent = (volumes[-1] / avg_volume) * 100

    # Cooldown
    now = datetime.utcnow()
    if symbol in last_alert_time:
        if now - last_alert_time[symbol] < timedelta(minutes=COOLDOWN_MINUTES):
            return

    # ================= CONDITIONS =================

    if (
        range_percent < 7
        and 40 < rsi < 65
        and bb_width < 8
        and gradual
        and volume_percent > 130
    ):

        message = f"""
🚀 ACCUMULATION ZONE DETECTED

Symbol: {symbol}
TF: {TIMEFRAME}

Range: {range_percent:.2f}%
RSI: {rsi:.1f}
BB Width: {bb_width:.2f}
Volume: {volume_percent:.1f}%

🔥 Potential Pre-Breakout Structure
"""

        send_telegram(message)
        last_alert_time[symbol] = now

# ================= MEXC KLINES =================

def get_klines(symbol, interval="15m", limit=50):
    url = "https://api.mexc.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        return requests.get(url, params=params, timeout=10).json()
    except:
        return None

# ================= MAIN LOOP =================

def main():
    symbols = get_symbols()
    for symbol in symbols:
        check_symbol(symbol)
        time.sleep(SLEEP_BETWEEN_SYMBOLS)

if __name__ == "__main__":
    while True:
        main()
        print("Cycle finished. Sleeping...")
        time.sleep(CYCLE_SLEEP)
