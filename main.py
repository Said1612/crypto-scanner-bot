# -*- coding: utf-8 -*-
import os, time, logging, requests
from datetime import datetime

# ═══════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not CHAT_ID:
    raise Exception("❌ TELEGRAM_TOKEN or CHAT_ID is missing!")

MEXC_BASE = "https://api.mexc.com/api/v3"

# ═══════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ═══════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════

def send(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)

        if r.status_code != 200:
            log.error("Telegram error: %s", r.text)

    except Exception as e:
        log.error("Send failed: %s", e)

# ═══════════════════════════════════════
# FETCH
# ═══════════════════════════════════════

def fetch_tickers():
    try:
        r = requests.get(f"{MEXC_BASE}/ticker/24hr", timeout=10)
        return r.json()
    except Exception as e:
        log.error("Fetch error: %s", e)
        return []

# ═══════════════════════════════════════
# SCAN
# ═══════════════════════════════════════

def scan():
    data = fetch_tickers()

    for coin in data:
        try:
            symbol = coin["symbol"]
            price = float(coin["lastPrice"])
            change = float(coin["priceChangePercent"])

            # مثال شرط بسيط (تقدر تبدلو)
            if change > 5:
                send(
                    f"🚀 *Signal Detected*\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"💰 Coin: `{symbol}`\n"
                    f"💵 Price: `{price}`\n"
                    f"📈 Change: `{change}%`\n"
                    f"⏰ {datetime.now()}"
                )

        except:
            continue

# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    send("✅ Bot Started")

    while True:
        try:
            scan()
            time.sleep(30)

        except Exception as e:
            log.error("Loop error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
