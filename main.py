# -*- coding: utf-8 -*-
# SNIPER BOT - CLEAN + TELEGRAM READY + NICE NUMBERS

import time
import random
import logging
import sys
from datetime import datetime

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.info("🚀 SNIPER BOT STARTED")

# === CONFIG ===
TPS_MIN = 1.08
VDELTA_MIN = 0.52
VOL_RATIO_MIN = 1.4
MAX_SIGNALS_PER_DAY = 10

signals_sent = 0
current_day = datetime.utcnow().date()

# === FORMAT FUNCTION (FIX FLOAT ISSUE) ===
def clean(n):
    return round(n, 2)

# === MOCK DATA (KEEP UNTIL API RESTORED) ===
def get_market_data():
    return {
        "tps": clean(random.uniform(0.9, 1.3)),
        "vdelta": clean(random.uniform(0.4, 0.7)),
        "vol_ratio": clean(random.uniform(1.0, 2.0)),
        "ats_now": clean(random.uniform(100, 200)),
        "ats_prev": clean(random.uniform(90, 190))
    }

# === LOGIC ===
def sniper_entry(data):
    return (
        data["tps"] >= TPS_MIN and
        data["vdelta"] >= VDELTA_MIN and
        data["vol_ratio"] >= VOL_RATIO_MIN and
        data["ats_now"] > data["ats_prev"]
    )

# === TELEGRAM (PUT YOUR DATA BACK HERE) ===
def send_telegram(msg):
    try:
        # ⚠️ رجع التوكن ديالك هنا
        # مثال:
        # import requests
        # TOKEN = "YOUR_TOKEN"
        # CHAT_ID = "YOUR_CHAT_ID"
        # url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        # requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        pass
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

# === LOOP ===
while True:
    try:
        if datetime.utcnow().date() != current_day:
            signals_sent = 0
            current_day = datetime.utcnow().date()
            logging.info("🔄 Reset signals")

        data = get_market_data()

        if sniper_entry(data):
            if signals_sent < MAX_SIGNALS_PER_DAY:
                signals_sent += 1

                message = f"🔥 SIGNAL #{signals_sent}\nTPS: {data['tps']} | VΔ: {data['vdelta']} | VOL: {data['vol_ratio']}"

                logging.info(message)
                send_telegram(message)

        time.sleep(5)

    except Exception as e:
        logging.error(f"❌ ERROR: {e}")
        time.sleep(10)
