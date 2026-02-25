import requests
import time
from datetime import datetime

# ================= SETTINGS =================

TIMEFRAMES = ["15m", "1h", "4h"]
TOP_COINS = 20
CHECK_EVERY = 180
VOLUME_THRESHOLD = 170  # قوة السيولة %

last_signals = {}

# ===========================================

def get_top_symbols():
    url = "https://api.mexc.com/api/v3/ticker/24hr"

    try:
        data = requests.get(url, timeout=10).json()

        usdt_pairs = [
            s for s in data
            if s["symbol"].endswith("USDT")
        ]

        sorted_pairs = sorted(
            usdt_pairs,
            key=lambda x: float(x["quoteVolume"]),
            reverse=True
        )

        top = [s["symbol"] for s in sorted_pairs[:TOP_COINS]]

        print(f"🔥 Scanning Top {TOP_COINS} High Liquidity Coins")
        return top

    except Exception as e:
        print("Symbol load error:", e)
        return []


def get_klines(symbol, timeframe):
    url = "https://api.mexc.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": timeframe,
        "limit": 100
    }

    try:
        data = requests.get(url, params=params, timeout=10).json()

        if not isinstance(data, list):
            return None

        return data

    except:
        return None


def check_signal(symbol, timeframe):

    klines = get_klines(symbol, timeframe)
    if not klines or len(klines) < 30:
        return

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    last_close = closes[-1]
    last_volume = volumes[-1]

    avg_volume = sum(volumes[-21:-1]) / 20
    liquidity_strength = (last_volume / avg_volume) * 100

    highest_20 = max(highs[-21:-1])
    lowest_20 = min(lows[-21:-1])

    direction = None

    if liquidity_strength > VOLUME_THRESHOLD:
        if last_close > highest_20:
            direction = "LONG"
        elif last_close < lowest_20:
            direction = "SHORT"

    if direction:

        key = f"{symbol}_{timeframe}"
        repeated = ""

        if key in last_signals:
            repeated = "🚨 NEW LIQUIDITY ENTERED 🚨\n"

        last_signals[key] = datetime.now()

        print(f"""
🔥 ULTRA BEAST SIGNAL 🔥
Symbol: {symbol}
Timeframe: {timeframe}
Direction: {direction}
Liquidity Strength: {liquidity_strength:.1f}%
{repeated}
Time: {datetime.now()}
""")


def main():
    print("🚀 ULTRA BEAST MEXC MODE ACTIVE")

    send_telegram("🚀 BOT RESTARTED SUCCESSFULLY")  # ← أضف هذا السطر فقط

    while True:
        symbols = get_top_symbols()

        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    check_signal(symbol, tf)
                    time.sleep(0.15)
                except Exception as e:
                    print("Error:", e)

        print("⏳ Waiting next cycle...\n")
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
