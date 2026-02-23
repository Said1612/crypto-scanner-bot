import os
import requests
import time
import sys

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Missing TELEGRAM_TOKEN or CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        print("✅ Message sent:", r.status_code)
    except Exception as e:
        print("❌ Telegram error:", e)

def run_bot():
    print("🚀 Bot started")
    while True:
        send_message("🤖 Bot is running...")
        time.sleep(3600)  # 1 hour

if name == "main":
    try:
        run_bot()
    except Exception as e:
        print("🔥 Fatal error:", e)
        sys.exit(1)
