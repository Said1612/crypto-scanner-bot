import requests
import time
import os

print("=== BOT IS RUNNING ===", flush=True)

# ==============================
# TELEGRAM CONFIG
# ==============================

BOT_TOKEN = os.environ.get("7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ")
CHAT_ID = os.environ.get("1658477428")

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram config missing", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram sent:", response.status_code, flush=True)
    except Exception as e:
        print("Telegram Error:", e, flush=True)

# ==============================
# MEXC KLINES (4H)
# ==============================

def get_klines(symbol, interval="4h", limit=50):
    url = "https://api.mexc.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if not isinstance(data, list):
            print("MEXC API Error:", data, flush=True)
            return None

        return data

    except Exception as e:
        print("Request Error:", e, flush=True)
        return None

# ==============================
# LIQUIDITY LOGIC
# ==============================

last_signal = {}

def major_liquidity(symbol):
    klines = get_klines(symbol)

    if klines is None or len(klines) < 20:
        print(f"Not enough data for {symbol}", flush=True)
        return None

    try:
        volumes = [float(k[5]) for k in klines]
        closes = [float(k[4]) for k in klines]

        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
        current_volume = volumes[-1]

        print(f"{symbol} Current Vol: {current_volume} | Avg Vol: {avg_volume}", flush=True)

        if current_volume > avg_volume * 2:

            if closes[-1] > closes[-2]:
                return "IN"

            elif closes[-1] < closes[-2]:
                return "OUT"

        return None

    except Exception as e:
        print("Liquidity Error:", e, flush=True)
        return None

# ==============================
# MAIN LOOP
# ==============================

if __name__ == "__main__":

    print("MEXC BOT STARTED SUCCESSFULLY", flush=True)

    while True:
        try:
            print("Checking BTC & ETH 4H liquidity on MEXC...", flush=True)

            for major in ["BTCUSDT", "ETHUSDT"]:

                result = major_liquidity(major)

                if result and last_signal.get(major) != result:

                    if result == "IN":
                        send_telegram(f"🟢 {major} 4H Liquidity IN (MEXC)")

                    elif result == "OUT":
                        send_telegram(f"🔴 {major} 4H Liquidity OUT (MEXC)")

                    last_signal[major] = result

            time.sleep(300)

        except Exception as e:
            print("MAIN LOOP ERROR:", e, flush=True)
            time.sleep(60)
