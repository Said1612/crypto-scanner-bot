import requests
import os
import time
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TIMEFRAME = "15m"
COOLDOWN_MINUTES = 60

last_alert_time = {}

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
    except:
        pass


# ================= DATA FETCH =================

def get_symbols():
    url = "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        # USDT pairs فقط
        usdt_pairs = [
            s for s in data
            if s["symbol"].endswith("USDT")
            and not any(x in s["symbol"] for x in ["3L", "3S", "BULL", "BEAR"])
        ]

        # ترتيب حسب حجم التداول
        sorted_pairs = sorted(
            usdt_pairs,
            key=lambda x: float(x["quoteVolume"]),
            reverse=True
        )

        top_20 = [s["symbol"] for s in sorted_pairs[:20]]

        print("Top 20 symbols:", top_20)

        return top_20

    except Exception as e:
        print("Error fetching symbols:", e)
        return []

        symbols = [
            s["symbol"] for s in data["symbols"]
            if s["quoteAsset"] == "USDT"
            and s["status"] == "1"   # 1 = trading on MEXC
        ]

        return symbols

    except Exception as e:
        print("Error fetching symbols:", e)
        return []

# ================= CORE LOGIC =================

def check_symbol(symbol):

    klines = get_klines(symbol, TIMEFRAME)
    if not klines or len(klines) < 30:
        return

    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]

    # ===== Range Compression =====
    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])
    range_percent = ((recent_high - recent_low) / recent_low) * 100

    # ===== Price Change (must be < 5%) =====
    price_change = abs((closes[-1] - closes[-2]) / closes[-2]) * 100
    if price_change == 0:
        return

    # ===== Volume Strength =====
    avg_volume = sum(volumes[-20:-1]) / 19
    volume_percent = (volumes[-1] / avg_volume) * 100

    # ===== Liquidity Efficiency =====
    efficiency = volume_percent / price_change

    # ===== Gradual Volume Build =====
    gradual = volumes[-3] < volumes[-2] < volumes[-1]

    # ===== Cooldown =====
    now = datetime.utcnow()
    if symbol in last_alert_time:
        if now - last_alert_time[symbol] < timedelta(minutes=COOLDOWN_MINUTES):
            return

    # ================= FINAL CONDITIONS =================

    if (
        range_percent < 6
        and price_change < 5
        and volume_percent > 180
        and efficiency > 60
        and gradual
    ):

        # Strength Rating
        strength = "Normal"
        if efficiency > 100:
            strength = "Strong"
        if efficiency > 180:
            strength = "Whale Accumulation"

        message = f"""
🧠 *SMART LIQUIDITY ACCUMULATION*

Symbol: `{symbol}`
TF: {TIMEFRAME}

Range: {range_percent:.2f}%
Price Move: {price_change:.2f}%
Liquidity: {volume_percent:.1f}%
Efficiency: {efficiency:.1f}

Strength: {strength}

⚠ Pre-Breakout Build Detected
"""

        send_telegram(message)
        last_alert_time[symbol] = now


# ================= MAIN LOOP =================

def main():
    symbols = get_symbols()
    print(f"Scanning {len(symbols)} symbols...")

    for symbol in symbols:
        check_symbol(symbol)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
