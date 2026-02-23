import requests
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_URL = "https://api1.binance.com/api/v3"

CHECK_INTERVAL = 300
MIN_VOLUME = 5_000_000
MIN_CHANGE = 3

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram variables missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

def safe_request(url):
    try:
        r = requests.get(url, timeout=15)
        data = r.json()

        if isinstance(data, dict) and "code" in data:
            print("Binance API Error:", data)
            return None

        return data

    except Exception as e:
        print("Request Error:", e)
        return None

def analyze_market():
    tickers = safe_request(f"{BINANCE_URL}/ticker/24hr")

    if not isinstance(tickers, list):
        print("Invalid ticker data")
        return []

    strong = []

    for coin in tickers:
        try:
            symbol = coin["symbol"]
            volume = float(coin["quoteVolume"])
            change = float(coin["priceChangePercent"])

            if symbol.endswith("USDT") and volume > MIN_VOLUME and abs(change) > MIN_CHANGE:
                strong.append({
                    "symbol": symbol,
                    "volume": volume,
                    "change": change
                })

        except Exception:
            continue

    return sorted(strong, key=lambda x: x["volume"], reverse=True)[:10]

def format_report(coins):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    message = f"🚀 *Smart Liquidity Report (SPOT)*\n"
    message += f"📅 {now}\n\n"

    if not coins:
        message += "No strong liquidity coins found."
        return message

    for c in coins:
        direction = "🟢 LONG" if c["change"] > 0 else "🔴 SHORT"

        message += (
            f"*{c['symbol']}*\n"
            f"Volume: {round(c['volume']/1_000_000,2)}M USDT\n"
            f"24h Change: {round(c['change'],2)}%\n"
            f"Signal: {direction}\n\n"
        )

    return message

def main():
    print("Smart Liquidity Engine v3.1 Started...")

    while True:
        try:
            coins = analyze_market()

            if coins:
                report = format_report(coins)
                send_telegram(report)

            print("Cycle complete...")
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Fatal Error:", e)
            time.sleep(60)

if __name__ == "__main__":
    main()
