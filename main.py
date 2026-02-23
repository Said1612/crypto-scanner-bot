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
timeframes = ["15m", "1h", "4h", "1d"]
volume_multiplier = 2.2
price_break_percent = 1.2

sent_signals = set()

# =============================
# TELEGRAM
# =============================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

# =============================
# GET ALL USDT PAIRS
# =============================
def get_all_usdt_symbols():
    url = "https://api1.binance.com/api/v3/exchangeInfo"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json()

    symbols = []
    for s in data["symbols"]:
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
            symbols.append(s["symbol"])

    return symbols

# =============================
# GET KLINES
# =============================
def get_klines(symbol, interval):
    url = f"https://api1.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=40"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    return response.json()

# =============================
# ANALYSIS
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

        signal_key = f"{symbol}_{interval}"

        # دخول سيولة
        if last_volume > avg_volume * volume_multiplier and price_change > price_break_percent:
            if signal_key not in sent_signals:
                sent_signals.add(signal_key)
               return f"""🟢🟢🟢 LIQUIDITY ENTRY 🟢🟢🟢

Symbol: {symbol}
Timeframe: {interval}

Strong Volume Inflow Detected
Breakout Confirmed 🚀
"""

        # خروج سيولة
        if last_volume > avg_volume * volume_multiplier and price_change < -price_break_percent:
            if signal_key not in sent_signals:
                sent_signals.add(signal_key)
              return f"""🔴🔴🔴 LIQUIDITY EXIT 🔴🔴🔴

Symbol: {symbol}
Timeframe: {interval}

Strong Sell Pressure
Liquidity Outflow Detected
"""
        return None

    except:
        return None

# =============================
# MAIN LOOP
# =============================
def main():
    print("Bot Started Successfully 🚀")
    send_telegram("🚀 Smart Liquidity Scanner Started")

    symbols = get_all_usdt_symbols()
    print(f"Scanning {len(symbols)} USDT pairs")

    while True:
        for symbol in symbols:
            for tf in timeframes:
                signal = analyze(symbol, tf)
                if signal:
                    print(signal)
                    send_telegram(signal)

                time.sleep(0.15)  # حماية من rate limit

        time.sleep(60)

# =============================
# START
# =============================
if __name__ == "__main__":
    main()
