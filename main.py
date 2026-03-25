# -*- coding: utf-8 -*-
# SNIPER BOT - MEXC VERSION (FREE + NO GEO BLOCK)

import time
import logging
import sys
from datetime import datetime
import requests

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.info("🚀 SNIPER BOT STARTED (MEXC VERSION)")

# === CONFIG ===
SYMBOL = "BTCUSDT"
INTERVAL = "1m"

TPS_MIN = 1.08
VDELTA_MIN = 0.52
VOL_RATIO_MIN = 1.4
MAX_SIGNALS_PER_DAY = 10

signals_sent = 0
current_day = datetime.utcnow().date()

# === TELEGRAM ===
TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN"
CHAT_ID = "PUT_YOUR_CHAT_ID"

# === FORMAT ===
def clean(n):
    return round(float(n), 2)

# === GET DATA FROM MEXC PUBLIC API ===
def get_market_data():
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=3"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        data = response.json()

        if not isinstance(data, list) or len(data) < 3:
            raise Exception(f"Bad response: {data}")

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
            "ats_prev": ats_prev
        }

    except Exception as e:
        logging.error(f"DATA ERROR: {e}")
        return None

# === LOGIC ===
def sniper_entry(data):
    return (
        data["tps"] >= TPS_MIN and
        data["vdelta"] >= VDELTA_MIN and
        data["vol_ratio"] >= VOL_RATIO_MIN and
        data["ats_now"] > data["ats_prev"]
    )

# === TELEGRAM SEND ===
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)

        if response.status_code != 200:
            logging.error(f"Telegram HTTP Error: {response.status_code} | {response.text}")

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

        if data is None:
            time.sleep(10)
            continue

        logging.info(f"DATA → TPS:{data['tps']} | VΔ:{data['vdelta']} | VOL:{data['vol_ratio']}")

        if sniper_entry(data):
            if signals_sent < MAX_SIGNALS_PER_DAY:
                signals_sent += 1

                message = (
                    f"🔥 SIGNAL #{signals_sent}\n"
                    f"Symbol: {SYMBOL}\n"
                    f"TPS: {data['tps']}\n"
                    f"VΔ: {data['vdelta']}\n"
                    f"VOL: {data['vol_ratio']}"
                )

                logging.info(message)
                send_telegram(message)

        time.sleep(5)

    except Exception as e:
        logging.error(f"❌ LOOP ERROR: {e}")
        time.sleep(10)
