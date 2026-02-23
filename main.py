import requests
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_SPOT_URL = "https://api.binance.com/api/v3"

CHECK_INTERVAL = 300  # 5 minutes
MIN_VOLUME = 5_000_000  # Minimum 24h USDT volume
MIN_CHANGE = 3  # Minimum % change

sent_coins = set()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

def get_spot_pairs():
    exchange_info = requests.get(f"{BINANCE_SPOT_URL}/exchangeInfo").json()
    symbols = []

    for s in exchange_info["symbols"]:
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
            symbols.append(s["symbol"])

    return symbols

def analyze_market():
    tickers = requests.get(f"{BINANCE_SPOT_URL}/ticker/24hr").json()
    strong_coins = []

    for coin in tickers:
        if coin["symbol"].endswith("USDT"):
            volume = float(coin["quoteVolume"])
            change = float(coin["priceChangePercent"])

            if volume > MIN_VOLUME and abs(change) > MIN_CHANGE:
                strong_coins.append({
                    "symbol": coin["symbol"],
                    "volume": volume,
                    "change": change
                })

    return sorted(strong_coins, key=lambda x: x["volume"], reverse=True)[:10]

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
    print("Smart Liquidity Engine v3 Started...")

    while True:
        try:
            coins = analyze_market()

            if coins:
                report = format_report(coins)
                send_telegram(report)

            print("Cycle complete...")
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Error:", e)
            time.sleep(60)

if __name__ == "__main__":
    main()
