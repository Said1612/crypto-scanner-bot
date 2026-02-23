import requests
import time
import statistics
from datetime import datetime

# =============================
# TELEGRAM CONFIG
# =============================
TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

# =============================
# SETTINGS
# =============================
timeframes = ["15m", "1h", "4h", "1d"]
volume_multiplier = 2.0
price_break_percent = 1.0

sent_signals = set()
last_update_day = None
top_symbols = []

# =============================
# TELEGRAM
# =============================
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, data=payload, timeout=10)
    except:
        pass

# =============================
# GET TOP 10 USDT PAIRS (BY VOLUME)
# =============================
def get_top_10_symbols():
    try:
        url = "https://api1.binance.com/api/v3/ticker/24hr"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return []

        data = response.json()

        usdt_pairs = [s for s in data if s["symbol"].endswith("USDT")]

        sorted_pairs = sorted(
            usdt_pairs,
            key=lambda x: float(x["quoteVolume"]),
            reverse=True
        )

        top10 = [s["symbol"] for s in sorted_pairs[:10]]

        return top10

    except:
        return []

# =============================
# GET KLINES
# =============================
def get_klines(symbol, interval):
    try:
        url = f"https://api1.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=40"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json()

        if isinstance(data, dict):
            return None

        return data

    except:
        return None

# =============================
# ANALYSIS
# =============================
def analyze(symbol, interval):
    try:
        data = get_klines(symbol, interval)

        if not data or len(data) < 10:
            return None

        closes = [float(c[4]) for c in data]
        volumes = [float(c[5]) for c in data]

        last_close = closes[-1]
        prev_close = closes[-2]
        last_volume = volumes[-1]
        avg_volume = statistics.mean(volumes[:-1])

        price_change = ((last_close - prev_close) / prev_close) * 100

        signal_key = f"{symbol}_{interval}"

        # 🟢 دخول سيولة
        if last_volume > avg_volume * volume_multiplier and price_change > price_break_percent:
            if signal_key not in sent_signals:
                sent_signals.add(signal_key)
                return f"""🟢🟢🟢 LIQUIDITY ENTRY 🟢🟢🟢

Symbol: {symbol}
Timeframe: {interval}
Price Change: {price_change:.2f}%

Strong Volume Inflow 🚀
"""

        # 🔴 خروج سيولة
        if last_volume > avg_volume * volume_multiplier and price_change < -price_break_percent:
            if signal_key not in sent_signals:
                sent_signals.add(signal_key)
                return f"""🔴🔴🔴 LIQUIDITY EXIT 🔴🔴🔴

Symbol: {symbol}
Timeframe: {interval}
Price Change: {price_change:.2f}%

Strong Sell Pressure
"""

        return None

    except:
        return None

# =============================
# MAIN LOOP
# =============================
def main():
    global last_update_day, top_symbols

    print("Bot Started Successfully 🚀")
    send_telegram("🚀 Smart Liquidity Bot Started")

    while True:
        current_day = datetime.utcnow().day

        # تحديث أفضل 10 عملات مرة واحدة يومياً
        if last_update_day != current_day:
            top_symbols = get_top_10_symbols()
            last_update_day = current_day
            sent_signals.clear()

            send_telegram(f"📊 Top 10 Coins Today:\n\n" + "\n".join(top_symbols))

        for symbol in top_symbols:
            for tf in timeframes:
                signal = analyze(symbol, tf)
                if signal:
                    print(signal)
                    send_telegram(signal)

                time.sleep(0.3)  # حماية من Rate Limit

        time.sleep(60)

# =============================
# START
# =============================
if __name__ == "__main__":
    main()
