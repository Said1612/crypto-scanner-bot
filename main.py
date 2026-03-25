# -*- coding: utf-8 -*-
# SNIPER BOT - TELEGRAM FORCE FIX

import time
import logging
import sys
from datetime import datetime
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.info("🚀 BOT STARTED")

SYMBOL = "BTCUSDT"
INTERVAL = "1m"

TPS_MIN = 1.001
VDELTA_MIN = 0.25
VOL_RATIO_MIN = 1.2
MAX_SIGNALS_PER_DAY = 20

signals_sent = 0
current_day = datetime.utcnow().date()

TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN"
CHAT_ID = "PUT_YOUR_CHAT_ID"

def clean(n):
    return round(float(n), 4)

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg
        }, timeout=10)

        logging.info(f"TELEGRAM STATUS: {r.status_code}")
        logging.info(f"TELEGRAM RESPONSE: {r.text}")

    except Exception as e:
        logging.error(f"Telegram Error: {e}")

# 🔥 إرسال رسالة مباشرة عند التشغيل
send_telegram("✅ BOT STARTED - IF YOU SEE THIS TELEGRAM WORKS")

def get_market_data():
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=3"
        response = requests.get(url, timeout=10)

        data = response.json()

        last = data[-1]
        prev = data[-2]

        volume_now = float(last[5])
        volume_prev = float(prev[5])

        open_price = float(last[1])
        close_price = float(last[4])

        tps = clean(close_price / open_price)
        vdelta = clean((volume_now - volume_prev) / volume_prev) if volume_prev != 0 else 0
        vol_ratio = clean(volume_now / volume_prev) if volume_prev != 0 else 1

        ats_now = clean(volume_now * close_price)
        ats_prev = clean(volume_prev * float(prev[4]))

        return {
            "tps": tps,
            "vdelta": vdelta,
            "vol_ratio": vol_ratio,
            "ats_now": ats_now,
            "ats_prev": ats_prev,
            "price": close_price
        }

    except Exception as e:
        logging.error(f"DATA ERROR: {e}")
        return None

def sniper_entry(data):
    return (
        data["tps"] >= TPS_MIN and
        data["vdelta"] >= VDELTA_MIN and
        data["vol_ratio"] >= VOL_RATIO_MIN and
        data["ats_now"] > data["ats_prev"]
    )

while True:
    try:
        data = get_market_data()

        if data is None:
            time.sleep(10)
            continue

        logging.info(f"DATA → TPS:{data['tps']} | VΔ:{data['vdelta']} | VOL:{data['vol_ratio']}")

        # 🔥 إرسال رسالة كل 60 ثانية للتأكد
        if int(time.time()) % 60 == 0:
            send_telegram(f"📡 BOT RUNNING | PRICE: {data['price']}")

        if sniper_entry(data):
            message = f"🔥 SIGNAL {SYMBOL} | PRICE {data['price']}"
            send_telegram(message)

        time.sleep(5)

    except Exception as e:
        logging.error(f"❌ LOOP ERROR: {e}")
        time.sleep(10)
