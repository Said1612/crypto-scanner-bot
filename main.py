import requests
import numpy as np
import time
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================

TELEGRAM_TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

BASE_URL = "https://api.binance.com/api/v3/klines"
EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"

timeframes = ["15m", "1h", "4h", "1d"]

weights = {
    "15m": 1,
    "1h": 2,
    "4h": 3,
    "1d": 4
}

last_sent = {}

# =========================
# TELEGRAM
# =========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)

# =========================
# BINANCE DATA
# =========================

def get_symbols():
    data = requests.get(EXCHANGE_INFO).json()
    symbols = []

    for s in data["symbols"]:
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
            symbols.append(s["symbol"])

    return symbols


def get_klines(symbol, interval):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": 50
    }
    response = requests.get(BASE_URL, params=params)
    return response.json()

# =========================
# BTC TREND FILTER
# =========================

def get_btc_trend():

    data_4h = get_klines("BTCUSDT", "4h")
    data_1d = get_klines("BTCUSDT", "1d")

    closes_4h = np.array([float(k[4]) for k in data_4h])
    closes_1d = np.array([float(k[4]) for k in data_1d])

    ema50_4h = closes_4h[-50:].mean()
    ema50_1d = closes_1d[-50:].mean()

    current_4h = closes_4h[-1]
    current_1d = closes_1d[-1]

    if current_4h > ema50_4h and current_1d > ema50_1d:
        return "BULLISH"
    elif current_4h < ema50_4h and current_1d < ema50_1d:
        return "BEARISH"
    else:
        return "NEUTRAL"

# =========================
# SCORE CALCULATION
# =========================

def calculate_score(volume_ratio, tf_score, price_change):

    score = 0

    score += min(volume_ratio * 10, 40)
    score += tf_score * 5
    score += min(abs(price_change) * 3, 30)

    return min(int(score), 100)

# =========================
# MAIN SCANNER
# =========================

def scan_market():

    symbols = get_symbols()
    trend = get_btc_trend()

    signals = []

    for symbol in symbols:

        green_score = 0
        red_score = 0
        tf_status = {}

        for tf in timeframes:

            data = get_klines(symbol, tf)
            closes = np.array([float(k[4]) for k in data])
            volumes = np.array([float(k[5]) for k in data])

            avg_volume = volumes[-20:].mean()
            current_volume = volumes[-1]

            change = ((closes[-1] - closes[-2]) / closes[-2]) * 100
            volume_ratio = current_volume / avg_volume

            if volume_ratio > 1.7 and change > 0:
                green_score += weights[tf]
                tf_status[tf] = "🟢"

            elif volume_ratio > 1.7 and change < 0:
                red_score += weights[tf]
                tf_status[tf] = "🔴"

            else:
                tf_status[tf] = "⚪"

        # PRE-LIQUIDITY
        if tf_status["15m"] == "🟢" and green_score <= 3 and trend != "BEARISH":
            score = calculate_score(volume_ratio, green_score, change)
            signals.append(("🟡 PRE-LIQUIDITY", symbol, score, tf_status))

        # CONFIRMED INFLOW
        elif green_score >= 5 and trend != "BEARISH":
            score = calculate_score(volume_ratio, green_score, change)
            signals.append(("🟢 CONFIRMED INFLOW", symbol, score, tf_status))

        # CONFIRMED OUTFLOW
        elif red_score >= 5 and trend != "BULLISH":
            score = calculate_score(volume_ratio, red_score, change)
            signals.append(("🔴 CONFIRMED OUTFLOW", symbol, score, tf_status))

    # Sort strongest first
    signals.sort(key=lambda x: x[2], reverse=True)
    top5 = signals[:5]

    now = datetime.utcnow()

    if top5:

        message = "🚨 SMART LIQUIDITY REPORT (SPOT)\n\n"

        for label, symbol, score, tf_status in top5:

            # Prevent repeat within 6 hours
            if symbol in last_sent:
                if now - last_sent[symbol] < timedelta(hours=6):
                    continue

            last_sent[symbol] = now

            message += f"""
{label}
{symbol}
Score: {score}/100

15m: {tf_status['15m']}
1h : {tf_status['1h']}
4h : {tf_status['4h']}
1d : {tf_status['1d']}
-------------------------
"""

        send_telegram(message)

# =========================
# LOOP
# =========================

while True:
    try:
        scan_market()
        time.sleep(300)  # scan every 5 minutes
    except Exception as e:
        print("Error:", e)
        time.sleep(60)
