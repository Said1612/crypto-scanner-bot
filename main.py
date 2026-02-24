import requests
import time

# =====================================
# TELEGRAM CONFIG
# =====================================

TELEGRAM_TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

# =====================================
# TELEGRAM FUNCTION
# =====================================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram response:", response.text)
    except Exception as e:
        print("Telegram Error:", e)

# =====================================
# TEST LOOP
# =====================================

if __name__ == "__main__":
    print("Bot started...")
    send_telegram("🚀 BOT STARTED SUCCESSFULLY")

    while True:
        time.sleep(60)
        print("Bot running...")
