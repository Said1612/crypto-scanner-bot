# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 14.1 (TRANSPARENCY & FLOW)
السر: سجلات لحظية لكل خطوة + تحسين حساسية Binance
المطور: MAFIO AI
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Binance Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير Binance (تم تحسينها للحساسية)
MIN_VOLUME_24H = 800000     # 800 ألف دولار
MIN_24H_CHANGE = -12.0      
MAX_24H_CHANGE = 30.0      
MAX_PRICE_POS = 0.65       

# معايير الانفجار
MIN_FLOW_RATIO = 3.2       
MIN_NET_FLOW_USD = 30000   # 30 ألف دولار صافي سيولة
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_binance_data(endpoint, params=None):
    try:
        url = f"https://api.binance.com/api/v3/{endpoint}"
        r = requests.get(url, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def analyze_flow(sym):
    try:
        time.sleep(0.2) # تجنب الحظر
        kd = get_binance_data("klines", {"symbol": sym, "interval": "15m", "limit": 30})
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

    logger.info("🔍 Fetching market data from Binance...")
    tickers = get_binance_data("ticker/24hr")
    if not tickers: 
        logger.error("❌ Failed to fetch tickers from Binance")
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

    logger.info(f"📊 Found {len(candidates)} candidates matching basic filters.")
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    top_40 = candidates[:40]

    if not top_40:
        logger.info("😴 No elite candidates found in this cycle.")
        return

    logger.info(f"🧪 Analyzing flow for top {len(top_40)} coins...")
    max_r = 0.0
    for c in top_40:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_flow(sym)
        if not data or data == "TREND_DOWN": continue
        
        if data['ratio'] > max_r: max_r = data['ratio']
        
        if data['ratio'] >= MIN_FLOW_RATIO and data['net'] >= MIN_NET_FLOW_USD:
            state["count"] += 1; state["sent_coins"].append(sym)
            msg = (
                "🐺 *MAFIO BOT - BINANCE FLOW* 🐺\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${c['price']:.8g}`\n"
                f"📈 24h Change: `+{c['chg']:.2f}%` \n"
                f"📊 Ratio: `{data['ratio']:.1f}x` 🔥\n\n"
                f"🌊 *Net Flow:* `+${data['net']/1000:.1f}K` \n"
                f"🕒 {datetime.now().strftime('%H:%M UTC')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _سيولة مؤسساتية مرصودة على Binance!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"🎯 SIGNAL SENT: {sym} | Ratio: {data['ratio']:.1f}x")
            time.sleep(1)

    logger.info(f"✅ Cycle complete. Max Ratio found: {max_r:.1f}x")

def main():
    logger.info("🚀 MAFIO BOT 14.1 (Transparency Edition) Started")
    send_telegram("💀 *MAFIO BOT 14.1* متصل.\nنظام الشفافية والبحث اللحظي نشط الآن.")
    
    while True:
        try:
            scan()
            time.sleep(45) 
        except Exception as e:
            logger.error(f"⚠️ Loop Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
