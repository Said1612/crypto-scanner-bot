import requests
import time

# ==============================
# TELEGRAM CONFIG
# ==============================

TELEGRAM_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

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

        # فقط أزواج USDT
        usdt_pairs = [c for c in data if c["symbol"].endswith("USDT")]

        # ترتيب حسب أعلى حجم تداول
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

            # شرط تجريبي بسيط
            if change > 3 and volume > 1000000:
                signals.append(f"{symbol} | {change:.2f}%")

        if signals:
            message = "🔥 MEXC SIGNALS 🔥\n\n" + "\n".join(signals[:5])
            send_telegram(message)

    except Exception as e:
        print("Scan Error:", e)


# ==============================
# LOOP
# ==============================

print("Starting Container...", flush=True)

while True:
    scan_market()
    time.sleep(60)
