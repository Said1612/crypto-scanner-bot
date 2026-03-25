# -*- coding: utf-8 -*-
# SNIPER BOT - PUBLIC BINANCE + TELEGRAM

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

logging.info("🚀 SNIPER BOT STARTED (NO API KEY MODE)")

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

# === GET DATA FROM BINANCE PUBLIC API ===
def get_market_data():
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=3"
    response = requests.get(url)
    data = response.json()

    last = data[-1]
    prev = data[-2]

    volume_now = float(last[5])
    volume_prev = float(prev[5])

    open_price = float(last[1])
    close_price = float(last[4])

    # TPS
    tps = clean(close_price / open_price)

    # Volume delta
    vdelta = clean((volume_now - volume_prev) / volume_prev if volume_prev != 0 else 0)

    # Volume ratio
    vol_ratio = clean(volume_now / volume_prev if volume_prev != 0 else 1)

    # ATS
    ats_now = clean(volume_now * close_price)
    ats_prev = clean(volume_prev * float(prev[4]))

    return {
        "tps": tps,
        "vdelta": vdelta,
        "vol_ratio": vol_ratio,
        "ats_now": ats_now,
        "ats_prev": ats_prev
    }

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
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
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
        logging.error(f"❌ ERROR: {e}")
        time.sleep(10)
