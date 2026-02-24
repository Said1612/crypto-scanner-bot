import requests
import time
import os

# =========================
# TELEGRAM SETTINGS
# =========================

TELEGRAM_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

# =========================
# SEND TELEGRAM FUNCTION
# =========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        print("Telegram send failed")

# =========================
# MEXC SCANNER
# =========================

def scan_market():
    try:
        print("Scanning market...", flush=True)

        url = "https://api.mexc.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()

        strong_coins = []

        # فلترة أزواج USDT فقط
        usdt_pairs = [c for c in data if c["symbol"].endswith("USDT")]

        # ترتيب حسب أعلى حجم تداول
        sorted_coins = sorted(
            usdt_pairs,
            key=lambda x: float(x["quoteVolume"]),
            reverse=True
        )

        # أفضل 15 عملة من حيث السيولة
        top_volume_coins = sorted_coins[:15]

        for coin in top_volume_coins:
            symbol = coin["symbol"]
            change = float(coin["priceChangePercent"])
            volume = float(coin["quoteVolume"])

            # فلتر السيولة الذكي
            if 3 < change < 12 and volume > 1000000:
                strong_coins.append(
                    f"🟢 STRONG LIQUIDITY\n"
                    f"{symbol}\n"
                    f"📈 Change: {round(change,2)}%\n"
                    f"💰 Volume: {round(volume/1000000,2)}M\n"
                )

        if strong_coins:
            message = "🔥 ULTRA LIQUIDITY DETECTED 🔥\n\n"
            message += "\n".join(strong_coins[:5])
            send_telegram(message)

    except Exception as e:
        print("Error in scan_market:", e)

# =========================
# LOOP
# =========================

if __name__ == "__main__":
    while True:
        scan_market()
        time.sleep(300)  # كل 5 دقائق
