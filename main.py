# -*- coding: utf-8 -*-
# SNIPER BOT - MEXC IMPROVED (SMART SIGNALS)

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

logging.info("🚀 SNIPER BOT STARTED (MEXC IMPROVED)")

SYMBOL = "BTCUSDT"
INTERVAL = "1m"

# === IMPROVED THRESHOLDS ===
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

def get_market_data():
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=5"
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

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

# === SEND START MESSAGE ===
send_telegram("✅ BOT STARTED SUCCESSFULLY")

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

        if sniper_entry(data) and signals_sent < MAX_SIGNALS_PER_DAY:
            signals_sent += 1

            strength = int((data["tps"]*100 + data["vdelta"]*100 + data["vol_ratio"]*100)/3)

            message = (
                f"👁️ WATCH ALERT\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔍 {SYMBOL} — نشاط متصاعد\n"
                f"💵 السعر: {data['price']}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚡ TPS: {data['tps']}\n"
                f"📊 VDelta: {round(data['vdelta']*100,2)}%\n"
                f"📊 Volume Ratio: {data['vol_ratio']}\n"
                f"💰 ATS: {data['ats_now']}$\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💪 القوة: {strength}/100\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🃏 فرصة محتملة — راقب الدخول"
            )

            logging.info(message)
            send_telegram(message)

        time.sleep(5)

    except Exception as e:
        logging.error(f"❌ LOOP ERROR: {e}")
        time.sleep(10)
