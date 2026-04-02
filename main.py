# -*- coding: utf-8 -*-
"""
WOLF LIQUIDITY SNIPER BOT v1.1 - FIXED & OPTIMIZED (WOLF FLOW)
اقتناص السيولة قبل الانفجار - مبني على بيانات WOLF TRADING
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone
from collections import deque

# الإعدادات - ضع TOKEN و CHAT_ID
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير WOLF (محسنة من main-2.py)
MIN_VOLUME_24H = 100000
MIN_24H_CHANGE = -8.0
MAX_24H_CHANGE = 15.0
MAX_PRICE_POS = 0.60
MIN_FLOW_RATIO = 3.0
MAX_FLOW_RATIO = 1000.0
MIN_NET_FLOW_USD = 10000
MAX_1H_MOVE = 25.0
MIN_VOL_ACCEL = 1.5

BLACKLIST = set(["JTOUSDT", "SIGNUSDT", "OPENUSDT"])  # قابل للتوسع

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("WOLF_BOT")

state = {"date": "", "count": 0, "sent_coins": deque(maxlen=200), "source": "BINANCE", "first_run": True}
active_trades = {}

def send_telegram(msg):
    if "ضع_" in TOKEN: return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

def get_api(source, endpoint, params=None):
    base_urls = {
        "BINANCE": ["https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com"],
        "MEXC": ["https://api.mexc.com"]
    }
    for base in base_urls.get(source, []):
        try:
            r = requests.get(f"{base}/api/v3/{endpoint}", params=params, timeout=10)
            if r.status_code == 200: return r.json()
            if r.status_code == 429: time.sleep(1)
        except: continue
    return None

def calc_ema(prices, period):
    if len(prices) < period: return prices[-1] if prices else 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]: ema = p * k + ema * (1 - k)
    return ema

def format_duration(seconds):
    h, m = divmod(int(seconds), 3600)
    m = m // 60
    return f"{h}h {m}m" if h else f"{m}m"

def track_profits():
    if not active_trades: return
    data = get_api(state["source"], "ticker/24hr")
    if not data: return
    prices = {t["symbol"]: float(t["lastPrice"]) for t in data}

    for sym in list(active_trades):
        if sym not in prices: continue
        curr = prices[sym]
        entry = active_trades[sym]["entry"]
        gain = (curr - entry) / entry * 100

        if gain > active_trades[sym].setdefault("max_gain", 0):
            active_trades[sym]["max_gain"] = gain

        for ms in [2, 5, 10, 15, 25, 50]:
            if gain >= ms and ms not in active_trades[sym].setdefault("milestones", []):
                active_trades[sym]["milestones"].append(ms)
                dur = format_duration(time.time() - active_trades[sym]["time"])
                msg = (
                    f"🔥 *{sym[:-4]} +{ms}% milestone reached*\
"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%`\
"
                    f"💰 Price now: `${curr:.8g}`\
"
                    f"🏁 Entry: `${entry:.8g}`\
"
                    f"⏱️ Achieved in: `{dur}`"
                )
                send_telegram(msg)

        if time.time() - active_trades[sym]["time"] > 86400:
            del active_trades[sym]

def analyze_flow(sym, source):
    try:
        klines = get_api(source, "klines", {"symbol": sym, "interval": "5m", "limit": 50})
        if not klines or len(klines) < 20: return None

        closes = [float(c[4]) for c in klines[-20:]]
        openss = [float(c[1]) for c in klines[-20:]]
        vols = [float(c[5]) for c in klines[-20:]]

        ema5, ema10, ema20 = calc_ema(closes, 5), calc_ema(closes, 10), calc_ema(closes, 20)
        if not (closes[-1] > ema5 > ema10 > ema20): return "TREND_DOWN"

        avg_vol = sum(vols[-10:]) / 10 or 1
        vol_accel = vols[-1] / avg_vol

        in_f, out_f = 0, 0
        for o, c, v in zip(openss[-5:], closes[-5:], vols[-5:]):
            val = v * c
            if c > o: in_f += val
            else: out_f += val
        ratio = in_f / (out_f or 1)

        if
