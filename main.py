import requests
import time
import statistics

# =============================
# TELEGRAM CONFIG
# =============================
TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

# =============================
# SETTINGS
# =============================
symbols = ["BTCUSDT", "ETHUSDT", "AGLDUSDT", "KITEUSDT"]
timeframes = ["15m", "1h", "4h", "1d"]

volume_multiplier = 2.5   # تضخيم السيولة
price_break_percent = 1.5 # نسبة كسر سعري %

# =============================
# TELEGRAM FUNCTION
# =============================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=payload)
    except:
        pass

# =============================
# BINANCE REQUEST
# =============================
def get_klines(symbol, interval):
    url = f"https://api1.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=50"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    return response.json()

# =============================
# ANALYSIS FUNCTION
# =============================
def analyze(symbol, interval):
    try:
        data = get_klines(symbol, interval)
        closes = [float(c[4]) for c in data]
        volumes = [float(c[5]) for c in data]

        last_close = closes[-1]
        prev_close = closes[-2]

        last_volume = volumes[-1]
        avg_volume = statistics.mean(volumes[:-1])

        price_change = ((last_close - prev_close) / prev_close) * 100

        # =============================
        # LIQUIDITY ENTRY (GREEN)
        # =============================
        if last_volume > avg_volume * volume_multiplier:
            if price_change > price_break_percent:
                return f"🟢 LIQUIDITY ENTRY\n{symbol} ({interval})\nVolume Spike + Price Break 🔥"

        # =============================
        # LIQUIDITY EXIT (RED)
        # =============================
        if last_volume > avg_volume * volume_multiplier:
            if price_change < -price_break_percent:
                return f"🔴 LIQUIDITY EXIT\n{symbol} ({interval})\nSell Pressure Detected"

        return None

    except Exception as e:
        return None

# =============================
# MAIN LOOP
# =============================
def main():
    print("Bot Started Successfully 🚀")
    send_telegram("🚀 Liquidity Bot Started")

    while True:
        for symbol in symbols:
            for tf in timeframes:
                signal = analyze(symbol, tf)
                if signal:
                    print(signal)
                    send_telegram(signal)

        time.sleep(60)  # يفحص كل دقيقة

# =============================
# START
# =============================
if __name__ == "__main__":
    main()
