import requests
import pandas as pd
import time
import ta
from datetime import datetime

# ==========================================
# 🔐 TELEGRAM SETTINGS
# ==========================================

TELEGRAM_BOT_TOKEN = "your_token"
TELEGRAM_CHAT_ID = "your_chat_id"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

# ==========================================
# ⚙️ CONFIG
# ==========================================

INTERVAL = "15m"
LIMIT = 50
CHECK_EVERY = 60  # 60 للاختبار - غيّرها إلى 900 لاحقاً
MIN_VOLUME_MULTIPLIER = 1.5
REQUEST_DELAY = 0.2

sent_signals = {}

# ==========================================
# 🟢 GET BINANCE SYMBOLS
# ==========================================

def get_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    data = requests.get(url).json()
    symbols = [
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and not s["symbol"].endswith("UPUSDT")
        and not s["symbol"].endswith("DOWNUSDT")
    ]
    return symbols

# ==========================================
# 📊 GET KLINES
# ==========================================

def get_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT
    }
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data)
    df = df.iloc[:, :6]
    df.columns = ["time", "open", "high", "low", "close", "volume"]
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# ==========================================
# 🚀 CHECK SIGNAL
# ==========================================

def check_signal(symbol):
    df = get_klines(symbol)

    if len(df) < 30:
        return

    df["ema"] = ta.trend.ema_indicator(df["close"], window=20)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    avg_volume = df["volume"].rolling(20).mean().iloc[-1]

    breakout = last["close"] > df["high"].rolling(15).max().iloc[-2]
    volume_spike = last["volume"] > avg_volume * MIN_VOLUME_MULTIPLIER
    above_ema = last["close"] > last["ema"]
    green_candle = last["close"] > prev["close"]

    if breakout and volume_spike and above_ema and green_candle:

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if symbol not in sent_signals:
            message = f"""🔥 ULTRA BEAST SIGNAL 🔥

Symbol: {symbol}
Timeframe: {INTERVAL}
Time: {now}

Breakout + Volume Spike
"""

            send_telegram_message(message)
            sent_signals[symbol] = now
            print(f"Signal sent: {symbol}")

# ==========================================
# 🔁 MAIN LOOP
# ==========================================

def main():
    print("🔥 Ultra Beast Running...")
    symbols = get_symbols()

    while True:
        for symbol in symbols:
            try:
                check_signal(symbol)
                time.sleep(REQUEST_DELAY)
            except Exception as e:
                print("Error:", e)

        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
