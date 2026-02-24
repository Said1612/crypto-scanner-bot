print("ULTRA BEAST FILE LOADED", flush=True)

import requests
import time
import os

print("=== MEXC ULTRA BEAST ACTIVATED ===", flush=True)

# =============================
# ENV VARIABLES (IMPORTANT)
# =============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# =============================
# TELEGRAM FUNCTION
# =============================
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        print("Telegram response:", response.status_code)
    except Exception as e:
        print("Telegram error:", e)

# =============================
# TEST MESSAGE ON START
# =============================
send_telegram("🔥 ULTRA BEAST IS ONLINE 🔥")

# =============================
# MEXC SCANNER
# =============================
def scan_market():
    try:
        print("Ultra scanning market...", flush=True)

        url = "https://api.mexc.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()

        strong_coins = []

        for coin in data:
            symbol = coin["symbol"]

            if not symbol.endswith("USDT"):
                continue

            change = float(coin["priceChangePercent"])
            volume = float(coin["quoteVolume"])

            # 🔥 فلتر الانفجار
            if change > 5 and volume > 1000000:
                strong_coins.append(
                    f"{symbol} | 🚀 {round(change,2)}% | 💰 Vol: {round(volume/1000000,2)}M"
                )

        if strong_coins:
            message = "🔥 ULTRA BREAKOUT DETECTED 🔥\n\n" + "\n".join(strong_coins[:10])
            send_telegram(message)

    except Exception as e:
        print("Scan error:", e)

# =============================
# MAIN LOOP
# =============================
while True:
    scan_market()
    time.sleep(300)  # كل 5 دقائق
