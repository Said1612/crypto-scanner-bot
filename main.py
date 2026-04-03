# -*- coding: utf-8 -*-
# SNIPER BOT - STABLE VERSION (NO CRASH)

import time
import random

print("🚀 SNIPER BOT STARTED SUCCESSFULLY")

# === CONFIG ===
TPS_MIN = 1.08
VDELTA_MIN = 0.52
VOL_RATIO_MIN = 1.4

MAX_SIGNALS_PER_DAY = 10

signals_sent = 0

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
    if (
        data["tps"] >= TPS_MIN and
        data["vdelta"] >= VDELTA_MIN and
        data["vol_ratio"] >= VOL_RATIO_MIN and
        data["ats_now"] > data["ats_prev"]
    ):
        return True
    return False

# === MAIN LOOP (IMPORTANT FIX) ===
while True:
    try:
        data = get_market_data()

        if sniper_entry(data):
            if signals_sent < MAX_SIGNALS_PER_DAY:
                signals_sent += 1
                print(f"🔥 SIGNAL #{signals_sent} | DATA: {data}")

        time.sleep(5)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(10)
