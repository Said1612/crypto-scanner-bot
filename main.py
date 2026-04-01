# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 14.2 (INDESTRUCTIBLE EDITION)
السر: نظام التبديل التلقائي بين Binance و MEXC لضمان استمرار البحث
المطور: MAFIO AI
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Multi-Source Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير البحث العامة
MIN_VOLUME_24H = 500000     
MIN_24H_CHANGE = -12.0      
MAX_24H_CHANGE = 30.0      
MAX_PRICE_POS = 0.65       

# معايير الانفجار
MIN_FLOW_RATIO = 3.5       
MIN_NET_FLOW_USD = 20000   
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "current_source": "BINANCE"}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data_from_anywhere(source, endpoint, params=None):
    """محرك جلب البيانات مع دعم التبديل التلقائي"""
    if source == "BINANCE":
        urls = [
            f"https://api.binance.com/api/v3/{endpoint}",
            f"https://api1.binance.com/api/v3/{endpoint}",
            f"https://api2.binance.com/api/v3/{endpoint}",
            f"https://api3.binance.com/api/v3/{endpoint}"
        ]
    else: # MEXC
        urls = [f"https://api.mexc.com/api/v3/{endpoint}"]

    for url in urls:
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200: return r.json()
            if r.status_code == 429: time.sleep(2)
        except: continue
    return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def analyze_flow(sym, source):
    try:
        time.sleep(0.2)
        kd = get_data_from_anywhere(source, "klines", {"symbol": sym, "interval": "15m", "limit": 30})
        if not kd: return None
        
        closes = [float(c[4]) for c in kd]; opens = [float(c[1]) for c in kd]; vols = [float(c[5]) for c in kd]
        ema20 = calc_ema(closes, 20)
        if closes[-1] < ema20: return "TREND_DOWN"
        
        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        return {"in": in_f, "out": out_f, "net": in_f - out_f, "ratio": ratio, "price": closes[-1]}
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    source = state["current_source"]
    logger.info(f"🔍 Searching market using {source}...")
    
    tickers = get_data_from_anywhere(source, "ticker/24hr")
    
    # التبديل التلقائي في حال الفشل
    if not tickers:
        new_source = "MEXC" if source == "BINANCE" else "BINANCE"
        logger.warning(f"⚠️ {source} failed. Switching to {new_source}...")
        state["current_source"] = new_source
        return

    candidates = []
    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            
            if vol_24h < MIN_VOLUME_24H or chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            
            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'chg': chg_24h})
        except: continue

    logger.info(f"📊 {source}: Found {len(candidates)} potential coins.")
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    top_candidates = candidates[:35]

    max_r = 0.0
    for c in top_candidates:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_flow(sym, source)
        if not data or data == "TREND_DOWN": continue
        
        if data['ratio'] > max_r: max_r = data['ratio']
        
        if data['ratio'] >= MIN_FLOW_RATIO and data['net'] >= MIN_NET_FLOW_USD:
            state["count"] += 1; state["sent_coins"].append(sym)
            msg = (
                f"💀 *MAFIO BOT - {source} FLOW* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${c['price']:.8g}`\n"
                f"📈 24h Change: `+{c['chg']:.2f}%` \n"
                f"📊 Ratio: `{data['ratio']:.1f}x` 🔥\n\n"
                f"🌊 *Net Flow:* `+${data['net']/1000:.1f}K` \n"
                f"🕒 {datetime.now().strftime('%H:%M UTC')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ _سيولة مؤسساتية مرصودة على {source}!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"🎯 SIGNAL: {sym} | Source: {source}")
            time.sleep(1)

    logger.info(f"✅ Cycle complete ({source}). Max Ratio: {max_r:.1f}x")

def main():
    logger.info("🚀 MAFIO BOT 14.2 (Indestructible) Started")
    send_telegram("💀 *MAFIO BOT 14.2* متصل.\nنظام التبديل التلقائي (Binance/MEXC) نشط الآن لضمان استقرار البحث.")
    
    while True:
        try:
            scan()
            time.sleep(40) 
        except Exception as e:
            logger.error(f"⚠️ Loop Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
