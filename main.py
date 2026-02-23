import requests
import time
from datetime import datetime

# ========= CONFIG =========
TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

MIN_VOLUME_USDT = 5_000_000
MIN_PRICE_CHANGE = 2
TOP_RESULTS = 10
SLEEP_TIME = 300

BINANCE_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"

sent_cache = set()


# ========= TELEGRAM =========
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)


# ========= FETCH DATA =========
def fetch_market_data():
    try:
        response = requests.get(BINANCE_URL, timeout=15)

        if response.status_code != 200:
            print("HTTP Error:", response.status_code)
            return None

        data = response.json()

        # CRITICAL CHECK
        if type(data) is not list:
            print("API did not return list. Response:")
            print(data)
            return None

        return data

    except Exception as e:
        print("Connection Error:", e)
        return None


# ========= SCAN =========
def scan_market():
    global sent_cache

    market_data = fetch_market_data()

    # Stop immediately if bad data
    if market_data is None:
        print("Skipping cycle due to bad API response.")
        return

    strong_coins = []

    for coin in market_data:

        # Extra protection
        if type(coin) is not dict:
            continue

        symbol = coin["symbol"]

        if not symbol.endswith("USDT"):
            continue

        try:
            volume = float(coin["quoteVolume"])
            change = float(coin["priceChangePercent"])
            price = float(coin["lastPrice"])

            if volume >= MIN_VOLUME_USDT and abs(change) >= MIN_PRICE_CHANGE:
                score = volume * abs(change)

                strong_coins.append({
                    "symbol": symbol,
                    "price": price,
                    "volume": volume,
                    "change": change,
                    "score": score
                })

        except:
            continue

    if not strong_coins:
        print("No strong coins found.")
        return

    strong_coins.sort(key=lambda x: x["score"], reverse=True)
    top = strong_coins[:TOP_RESULTS]

    message = "SMART LIQUIDITY REPORT (SPOT)\n"
    message += datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC") + "\n\n"

    new_found = False

    for coin in top:
        key = f"{coin['symbol']}_{round(coin['change'],1)}"

        if key in sent_cache:
            continue

        sent_cache.add(key)
        new_found = True

        direction = "LONG" if coin["change"] > 0 else "SHORT"

        message += (
            f"{coin['symbol']}\n"
            f"Price: {coin['price']}\n"
            f"Change: {round(coin['change'],2)}%\n"
            f"Volume: {round(coin['volume']/1_000_000,2)}M\n"
            f"Signal: {direction}\n\n"
        )

    if new_found:
        send_telegram(message)
        print("Signals sent.")
    else:
        print("No new signals.")


# ========= MAIN =========
if __name__ == "__main__":
    print("Smart Liquidity Engine v6.0 Started...")

    while True:
        try:
            scan_market()
            print("Cycle completed.")
            time.sleep(SLEEP_TIME)

        except Exception as e:
            print("Main Loop Error:", e)
            time.sleep(60)
