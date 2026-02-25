import requests
import pandas as pd
import time
from datetime import datetime
from binance.client import Client

# ==============================
# API SETTINGS
# ==============================

API_KEY = "PUT_YOUR_API_KEY"
API_SECRET = "PUT_YOUR_SECRET_KEY"

TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "PUT_YOUR_CHAT_ID"

client = Client(API_KEY, API_SECRET)

TIMEFRAMES = ["15m", "1h", "4h"]
TOP_COINS_LIMIT = 20
VOLUME_THRESHOLD = 150  # نسبة قوة السيولة

last_signals = {}

# ==============================
# TELEGRAM FUNCTION
# ==============================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    requests.get(url, params=params)

# ==============================
# GET TOP 20 COINS BY VOLUME
# ==============================

def get_top_20_symbols():
    tickers = client.futures_ticker()
    usdt_pairs = [t for t in tickers if t['symbol'].endswith("USDT")]

    sorted_pairs = sorted(
        usdt_pairs,
        key=lambda x: float(x['quoteVolume']),
        reverse=True
    )

    return [s['symbol'] for s in sorted_pairs[:TOP_COINS_LIMIT]]

# ==============================
# GET DATA
# ==============================

def get_klines(symbol, interval):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=100)
    df = pd.DataFrame(klines, columns=[
        "time","open","high","low","close","volume",
        "c1","c2","c3","c4","c5","c6"
    ])

    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# ==============================
# CHECK LIQUIDITY BREAKOUT
# ==============================

def check_signal(df):
    avg_volume = df["volume"].rolling(20).mean().iloc[-2]
    last_volume = df["volume"].iloc[-1]

    volume_strength = (last_volume / avg_volume) * 100

    high_break = df["high"].iloc[-1] > df["high"].rolling(20).max().iloc[-2]
    low_break = df["low"].iloc[-1] < df["low"].rolling(20).min().iloc[-2]

    if volume_strength > VOLUME_THRESHOLD:
        if high_break:
            return "LONG", volume_strength
        elif low_break:
            return "SHORT", volume_strength

    return None, volume_strength

# ==============================
# MAIN BOT
# ==============================

def run_bot():
    print("Scanning market...")
    symbols = get_top_20_symbols()

    for symbol in symbols:
        for tf in TIMEFRAMES:
            try:
                df = get_klines(symbol, tf)
                signal, strength = check_signal(df)

                if signal:
                    key = f"{symbol}_{tf}"

                    # إذا تكررت الإشارة = سيولة جديدة
                    repeated = ""
                    if key in last_signals:
                        repeated = "🚨 NEW LIQUIDITY ADDED 🚨\n"

                    last_signals[key] = datetime.now()

                    message = f"""
🔥 ULTRABEAST SIGNAL 🔥

Symbol: {symbol}
Timeframe: {tf}
Direction: {signal}

Liquidity قوة السيولة: {strength:.2f}%

{repeated}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

                    print(message)
                    send_telegram(message)

            except Exception as e:
                print(f"Error {symbol} {tf}:", e)

# ==============================
# LOOP
# ==============================

while True:
    run_bot()
    time.sleep(300)  # كل 5 دقائق
