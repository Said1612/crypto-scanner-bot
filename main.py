# -*- coding: utf-8 -*-
# SNIPER BOT - CLEAN & STABLE VERSION

import time
import random
import logging
from datetime import datetime

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logging.info("🚀 SNIPER BOT STARTED SUCCESSFULLY")

# === CONFIG ===
TPS_MIN = 1.08
VDELTA_MIN = 0.52
VOL_RATIO_MIN = 1.4
MAX_SIGNALS_PER_DAY = 10

signals_sent = 0
current_day = datetime.utcnow().date()

# === MOCK DATA (replace with real market data later) ===
def get_market_data():
    return {
        "tps": random.uniform(0.9, 1.3),
        "vdelta": random.uniform(0.4, 0.7),
        "vol_ratio": random.uniform(1.0, 2.0),
        "ats_now": random.uniform(100, 200),
        "ats_prev": random.uniform(90, 190)
    }

# === SNIPER LOGIC ===
def sniper_entry(data):
    return (
        data["tps"] >= TPS_MIN and
        data["vdelta"] >= VDELTA_MIN and
        data["vol_ratio"] >= VOL_RATIO_MIN and
        data["ats_now"] > data["ats_prev"]
    )

# === MAIN LOOP ===
while True:
    try:
        # Reset daily counter
        if datetime.utcnow().date() != current_day:
            signals_sent = 0
            current_day = datetime.utcnow().date()
            logging.info("🔄 Daily reset of signals counter")

        data = get_market_data()

        if sniper_entry(data):
            if signals_sent < MAX_SIGNALS_PER_DAY:
                signals_sent += 1
                logging.info(f"🔥 SIGNAL #{signals_sent} | DATA: {data}")
            else:
                logging.warning("⚠️ Max signals reached for today")

        time.sleep(5)

    except Exception as e:
        logging.error(f"❌ ERROR: {e}")
        time.sleep(10)
