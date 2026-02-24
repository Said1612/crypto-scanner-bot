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
def scan_market():
    url = "https://api.mexc.com/api/v3/ticker/24hr"
    response = requests.get(url)
    data = response.json()

    strong_coins = []

    # ترتيب العملات حسب أعلى حجم تداول
    usdt_pairs = [c for c in data if c["symbol"].endswith("USDT")]

    sorted_coins = sorted(
        usdt_pairs,
        key=lambda x: float(x["quoteVolume"]),
        reverse=True
    )

    top_volume_coins = sorted_coins[:15]

    for coin in top_volume_coins:
        symbol = coin["symbol"]
        change = float(coin["priceChangePercent"])
        volume = float(coin["quoteVolume"])

        # فلترة سيولة حقيقية قبل الانفجار
        if 3 < change < 12 and volume > 2000000:
            strong_coins.append(
                f"🟢 STRONG LIQUIDITY\n"
                f"{symbol}\n"
                f"📈 Change: {round(change,2)}%\n"
                f"💰 Volume: {round(volume/1000000,2)}M\n"
            )

    if strong_coins:
        message = "\n".join(strong_coins)
        send_telegram(message)

    except Exception as e:
        print("Scan error:", e)

# =============================
# MAIN LOOP
# =============================
while True:
    scan_market()
    time.sleep(300)  # كل 5 دقائق
