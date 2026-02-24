import requests
import time
import os

# ==============================
# TELEGRAM CONFIG
# ==============================

BOT_TOKEN = os.environ.get("7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ")
CHAT_ID = os.environ.get("1658477428")

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram config missing")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

# ==============================
# BINANCE DATA
# ==============================

def get_klines(symbol, interval="4h", limit=50):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        # حماية إذا Binance رجع خطأ
        if not isinstance(data, list):
            print("Binance API Error:", data)
            return None

        return data

    except Exception as e:
        print("Request Error:", e)
        return None

# ==============================
# LIQUIDITY LOGIC
# ==============================

def major_liquidity(symbol):
    klines = get_klines(symbol)

    if klines is None or len(klines) < 10:
        return None

    try:
        volumes = [float(k[5]) for k in klines if len(k) > 5]
        closes = [float(k[4]) for k in klines if len(k) > 4]

        if len(volumes) < 10 or len(closes) < 2:
            return None

        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
        current_volume = volumes[-1]

        if current_volume > avg_volume * 1.8:

            if closes[-1] > closes[-2]:
                return "IN"

            elif closes[-1] < closes[-2]:
                return "OUT"

        return None

    except Exception as e:
        print("Liquidity Calculation Error:", e)
        return None

# ==============================
# MAIN LOOP
# ==============================

if __name__ == "__main__":

    print("BOT STARTED SUCCESSFULLY")

    while True:
        try:
            print("Checking BTC & ETH 4H liquidity...")

            for major in ["BTCUSDT", "ETHUSDT"]:
                result = major_liquidity(major)

                if result == "IN":
                    send_telegram(f"🟢 {major} 4H Liquidity IN")

                elif result == "OUT":
                    send_telegram(f"🔴 {major} 4H Liquidity OUT")

            time.sleep(300)

        except Exception as e:
            print("MAIN LOOP ERROR:", e)
            time.sleep(60)
