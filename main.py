# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 13.2 (FIX & TRANSPARENCY)
السر: معالجة قيود الـ API وتوضيح أسباب استبعاد العملات
المطور: MAFIO AI
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Pro Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 150000    
MIN_24H_CHANGE = -8.0      
MAX_24H_CHANGE = 18.0      
MAX_PRICE_POS = 0.50       
MIN_FLOW_RATIO = 4.0       
MIN_NET_FLOW_USD = 10000   
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "is_first_run": True}
active_trades = {}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 429: 
            time.sleep(2)
            return None
        return r.json() if r.status_code == 200 else None
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def analyze_breakout_flow(sym):
    try:
        time.sleep(0.1) # تجنب حظر الـ API
        kd_1h = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "1h", "limit": 20})
        if not kd_1h: return "API_ERR"
        
        closes_1h = [float(c[4]) for c in kd_1h]; ema20_1h = calc_ema(closes_1h, 20)
        if closes_1h[-1] < (ema20_1h * 0.99): return "TREND_DOWN" # مرونة 1%
        
        kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 20})
        if not kd_15m: return "API_ERR"
        
        closes_15m = [float(c[4]) for c in kd_15m]; opens_15m = [float(c[1]) for c in kd_15m]; vols_15m = [float(c[5]) for c in kd_15m]
        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols_15m[i] * closes_15m[i]
            if closes_15m[i] > opens_15m[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        is_dry = True if ratio > 7.0 else False
        move_1h = ((closes_15m[-1] - float(kd_15m[-5][4])) / float(kd_15m[-5][4])) * 100
        
        return {"move_1h": move_1h, "in": in_f, "out": out_f, "net": in_f - out_f, "ratio": ratio, "is_dry": is_dry, "price": closes_15m[-1]}
    except: return "SYS_ERR"

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    scanned = 0; passed_basic = 0; trend_down = 0; api_err = 0; max_r = 0.0
    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        scanned += 1
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            
            if chg_24h < MIN_24H_CHANGE or vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            
            passed_basic += 1
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue

            data = analyze_breakout_flow(sym)
            if data == "TREND_DOWN": trend_down += 1; continue
            if data in ["API_ERR", "SYS_ERR"]: api_err += 1; continue
            
            if data['ratio'] > max_r: max_r = data['ratio']
            if (data['ratio'] < MIN_FLOW_RATIO and not data['is_dry']) or data['net'] < MIN_NET_FLOW_USD: continue

            if state["is_first_run"]:
                state["sent_coins"].append(sym)
                continue

            state["count"] += 1; state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': price, 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            msg = (
                "💀 *MAFIO BOT - اختراق متفجر* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${price:.8g}`\n"
                f"📈 1h Move: `+{data['move_1h']:.2f}%` ⚡\n\n"
                f"💹 *1h Flow:*\n"
                f"  📥 In: `${data['in']/1000:.1f}K` | 📤 Out: `${data['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${data['net']/1000:.1f}K` | 📊 Ratio: `{data['ratio']:.1f}x` ✅\n\n"
                f"🕒 {datetime.now().strftime('%H:%M UTC')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - تم رصد جفاف في البيع وبداية انفجار سعري!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym} | Ratio: {data['ratio']:.1f}")
            time.sleep(1)
        except: continue

    if not state["is_first_run"]:
        logger.info(f"🔍 Scan: {scanned} coins | {passed_basic} basic | {trend_down} trend_down | {api_err} api_err | MaxR: {max_r:.1f}x")
    else:
        state["is_first_run"] = False
        logger.info("✅ Silent database built. Ready for breakouts!")

def main():
    logger.info("🚀 MAFIO BOT 13.2 (Fix & Transparency) Started")
    send_telegram("💀 *MAFIO BOT 13.2* متصل.\nتم إصلاح قيود الـ API وتحسين دقة السجلات.")
    while True:
        try:
            scan()
            time.sleep(30) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
