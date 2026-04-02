# -*- coding: utf-8 -*-
"""
WOLF LIQUIDITY SNIPER v1.2 - PERFECTLY FIXED
نظام تتبع السيولة قبل الانفجار - مطابق لـ WOLF FLOW
"""

import os, sys, time, requests, logging
from datetime import datetime, timezone
from collections import deque

# =====================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
CHAT_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# إعدادات WOLF المحسنة
MIN_VOL_24H = 80000
MIN_CHG_24H = -10.0
MAX_CHG_24H = 18.0
MAX_PRICE_POS = 0.65
MIN_FLOW_RATIO = 2.8
MIN_NET_FLOW = 8000
MAX_1H_MOVE = 28.0
MIN_VOL_ACCEL = 1.4

BLACKLIST = {"JTOUSDT", "SIGNUSDT", "OPENUSDT", "UPUSDT", "DOWNUSDT"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger("WOLF")

state = {"date": "", "count": 0, "coins": deque(maxlen=150), "exchange": "BINANCE", "first": True}
trades = {}

def telegram(msg):
    if "ضع_" in TOKEN: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                     data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=8)
    except: pass

def api_call(source, endpoint, params=None):
    urls = {
        "BINANCE": ["https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com"],
        "MEXC": ["https://api.mexc.com"]
    }
    for base in urls.get(source, []):
        try:
            r = requests.get(f"{base}/api/v3/{endpoint}", params=params, timeout=8)
            if r.status_code == 200: return r.json()
        except: continue
    return None

def ema(prices, period):
    if len(prices) < period: return prices[-1] if prices else 0
    k = 2/(period+1)
    ema_val = sum(prices[:period])/period
    for p in prices[period:]: ema_val = p*k + ema_val*(1-k)
    return ema_val

def time_format(secs):
    h, m = divmod(int(secs), 3600); m //= 60
    return f"{h}h {m}m" if h else f"{m}m"

def track_gains():
    if not trades: return
    data = api_call(state["exchange"], "ticker/24hr")
    if not data: return
    
    prices = {t["symbol"]: float(t["lastPrice"]) for t in data}
    for sym in list(trades):
        if sym not in prices: continue
        curr = prices[sym]; entry = trades[sym]["entry"]
        gain = (curr-entry)/entry * 100
        
        if gain > trades[sym].get("max", 0):
            trades[sym]["max"] = gain
            
        for target in [2,5,10,15,25,50]:
            if gain >= target and target not in trades[sym].get("hits", []):
                trades[sym]["hits"] = trades[sym].get("hits", []) + [target]
                dur = time_format(time.time() - trades[sym]["start"])
                telegram(f"""🔥 *{sym[:-4]} +{target}% milestone reached*
📊 Max gain: `+{trades[sym]['max']:.2f}%`
💰 Price now: `${curr:.5g}`
🏁 Entry: `${entry:.5g}`
⏱️ Achieved in: `{dur}`""")
        
        if time.time() - trades[sym]["start"] > 86400:
            del trades[sym]

def check_flow(sym, source):
    try:
        klines = api_call(source, "klines", {"symbol": sym, "interval": "5m", "limit": 40})
        if not klines or 
