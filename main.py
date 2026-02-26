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
CYCLE_SLEEP = 120

EXCLUDED = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

last_alert_time = {}
tracked = {}

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

# ================= API =================

def get_symbols():
    try:
        data = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10).json()
        symbols = [
            s["symbol"]
            for s in data
            if s["symbol"].endswith("USDT")
            and not any(x in s["symbol"] for x in ["3L", "3S", "BULL", "BEAR"])
            and s["symbol"] not in EXCLUDED
            and 300000 < float(s["quoteVolume"]) < 15000000
        ]
        print(f"Scanning {len(symbols)} symbols...")
        return symbols
    except:
        return []

def get_klines(symbol, limit=50):
    try:
        r = requests.get(
            "https://api.mexc.com/api/v3/klines",
            params={"symbol": symbol, "interval": TIMEFRAME, "limit": limit},
            timeout=10
        ).json()
        return r if isinstance(r, list) else None
    except:
        return None

# ================= INDICATORS =================

def rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bb_width(closes, period=20):
    sma = sum(closes[-period:]) / period
    std = statistics.stdev(closes[-period:])
    upper = sma + (2 * std)
    lower = sma - (2 * std)
    return ((upper - lower) / sma) * 100

# ================= SIGNAL SYSTEM =================

def check_followup(symbol, price):
    entry = tracked[symbol]["entry"]
    level = tracked[symbol]["level"]
    change = ((price - entry) / entry) * 100

    if level == 1 and change >= 2:
        msg = f"""
🚀 SIGNAL #2

💰 {symbol}
📈 Gain: +{change:.2f}%
💵 Price: {price}

🔥 Momentum Building
"""
        send_telegram(msg)
        tracked[symbol]["level"] = 2

    elif level == 2 and change >= 4:
        msg = f"""
🔥 SIGNAL #3

💰 {symbol}
📈 Gain: +{change:.2f}%
💵 Price: {price}

🚀 Breakout Confirmed
"""
        send_telegram(msg)
        tracked[symbol]["level"] = 3

def check_symbol(symbol):

    kl = get_klines(symbol)
    if not kl or len(kl) < 30:
        return

    closes = [float(k[4]) for k in kl]
    volumes = [float(k[5]) for k in kl]
    highs = [float(k[2]) for k in kl]
    lows = [float(k[3]) for k in kl]

    price = closes[-1]

    if symbol in tracked:
        check_followup(symbol, price)
        return

    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])
    range_pct = ((recent_high - recent_low) / recent_low) * 100

    r = rsi(closes)
    bb = bb_width(closes)

    gradual = volumes[-3] < volumes[-2] < volumes[-1]
    avg_vol = sum(volumes[-20:-1]) / 19
    vol_pct = (volumes[-1] / avg_vol) * 100

    now = datetime.utcnow()

    if symbol in last_alert_time:
        if now - last_alert_time[symbol] < timedelta(minutes=COOLDOWN_MINUTES):
            return

    if (
        range_pct < 4
        and 45 < r < 60
        and bb < 5
        and gradual
        and vol_pct > 180
    ):

        msg = f"""
👑 SOURCE BOT

💰 {symbol}
🔔 SIGNAL #1

💵 Price: {price}
📊 Volume Spike: {vol_pct:.1f}%
📉 Range: {range_pct:.2f}%
📈 RSI: {r:.1f}

⚡ Early Liquidity Detected
"""

        send_telegram(msg)

        tracked[symbol] = {
            "entry": price,
            "level": 1
        }

        last_alert_time[symbol] = now

# ================= LOOP =================

def main():
    symbols = get_symbols()
    for s in symbols:
        check_symbol(s)
        time.sleep(SLEEP_BETWEEN_SYMBOLS)

if __name__ == "__main__":
    while True:
        main()
        print("Cycle finished. Sleeping...")
        time.sleep(CYCLE_SLEEP)
