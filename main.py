import os
import requests
import time

# Replace these with your actual bot token and chat ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Or directly: "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = os.getenv("CHAT_ID")  # Or directly: "11658477428"

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    requests.post(url, data=payload)

def run_bot():
    while True:
        send_message("🚀 Bot is running...")
        time.sleep(3600)  # Wait 1 hour

if __name__ == "__main__":
    run_bot()
