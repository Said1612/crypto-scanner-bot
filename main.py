import requests
import time

# ==============================
# TELEGRAM CONFIG
# ==============================

TELEGRAM_TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQE"
CHAT_ID = "1658477428"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)


# ==============================
# MEXC SCANNER
# ==============================

def scan_market():
    try:
        print("Scanning market...", flush=True)

        url = "https://api.mexc.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()

        usdt_pairs = [c for c in data if c["symbol"].endswith("USDT")]

        sorted_coins = sorted(
            usdt_pairs,
            key=lambda x: float(x["quoteVolume"]),
            reverse=True
        )

        top_15 = sorted_coins[:15]

        signals = []

        for coin in top_15:
            symbol = coin["symbol"]
            change = float(coin["priceChangePercent"])
            volume = float(coin["quoteVolume"])

            if abs(change) > 1:
                signals.append(f"{symbol} | {change:.2f}%")

        if signals:
            message = "🔥 MEXC SIGNALS 🔥\n\n" + "\n".join(signals[:5])
            send_telegram(message)

    except Exception as e:
        print("Scan Error:", e)


# ==============================
# START
# ==============================

print("Starting Container...", flush=True)
send_telegram("🚀 BOT STARTED SUCCESSFULLY")

while True:
    scan_market()
    time.sleep(60)
