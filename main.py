import requests
import time
from datetime import datetime

# ========= CONFIGURATION =========
TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

MIN_VOLUME_USDT = 5_000_000      # Minimum 24h volume (USDT)
MIN_PRICE_CHANGE = 2             # Minimum % price change
TOP_RESULTS = 10                 # Number of coins to send
SLEEP_TIME = 300                 # Scan interval in seconds (300 = 5 minutes)

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"

sent_cache = set()


# ========= SEND TELEGRAM MESSAGE =========
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)


# ========= FETCH BINANCE SPOT DATA =========
def fetch_spot_market_data():
    try:
        response = requests.get(BINANCE_TICKER_URL, timeout=15)
        return response.json()
    except Exception as e:
        print("Binance API Error:", e)
        return []


# ========= MARKET SCANNER =========
def scan_market():
    global sent_cache

    market_data = fetch_spot_market_data()
    filtered_coins = []

    for coin in market_data:
        symbol = coin.get("symbol", "")

        # Only Spot USDT pairs
        if not symbol.endswith("USDT"):
            continue

        try:
            volume = float(coin["quoteVolume"])
            price_change = float(coin["priceChangePercent"])
            last_price = float(coin["lastPrice"])

            # Liquidity filter
            if volume >= MIN_VOLUME_USDT and abs(price_change) >= MIN_PRICE_CHANGE:
                strength_score = volume * abs(price_change)

                filtered_coins.append({
                    "symbol": symbol,
                    "price": last_price,
                    "volume": volume,
                    "change": price_change,
                    "score": strength_score
                })

        except Exception:
            continue

    # Sort by strength score
    filtered_coins.sort(key=lambda x: x["score"], reverse=True)
    top_coins = filtered_coins[:TOP_RESULTS]

    if not top_coins:
        print("No strong coins found.")
        return

    # Build Telegram message
    message = "🚨 *Smart Liquidity Report (Spot)* 🚨\n"
    message += f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"

    new_signals = []

    for coin in top_coins:
        unique_key = f"{coin['symbol']}_{round(coin['change'],1)}"

        # Anti-duplicate system
        if unique_key in sent_cache:
            continue

        sent_cache.add(unique_key)
        new_signals.append(coin)

        direction = "🟢 LONG" if coin["change"] > 0 else "🔴 SHORT"

        message += (
            f"*{coin['symbol']}*\n"
            f"Price: {coin['price']}\n"
            f"24h Change: {round(coin['change'],2)}%\n"
            f"Volume: {round(coin['volume']/1_000_000,2)}M USDT\n"
            f"Signal: {direction}\n\n"
        )

    if new_signals:
        send_telegram_message(message)
        print("New signals sent.")
    else:
        print("No new signals.")


# ========= MAIN LOOP =========
if __name__ == "__main__":
    print("Smart Liquidity Engine v4.0 Started...")

    while True:
        try:
            scan_market()
            print("Scan cycle completed.")
            time.sleep(SLEEP_TIME)

        except Exception as e:
            print("Main Loop Error:", e)
            time.sleep(60)
