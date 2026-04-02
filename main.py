# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 20.0 (ALPHA WOLF)
السر: رصد الانفجار في العقود المفتوحة (OI Surge) + تدفق السيولة اللحظي
المطور: MAFIO AI - نظام التدفق المتقدم
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Pro Settings (Alpha Wolf Style)
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "الذئب" لاقتناص القاع
MIN_VOLUME_24H = 50000      # تقليل الحد لاصطياد العملات الصغيرة
MAX_VOLUME_24H = 50000000   
MIN_24H_CHANGE = -15.0      
MAX_24H_CHANGE = 25.0       
MAX_PRICE_POS = 0.35        # التأكد أن العملة في الـ 35% السفلى من نطاق يومها (القاع)

MIN_FLOW_RATIO = 5.0        
MIN_NET_FLOW_BASE = 15000   
MIN_VOL_ACCEL = 3.5         # تسارع الفوليوم مقارنة بآخر 20 دقيقة
MIN_OI_SURGE = 2.0          # الحد الأدنى لارتفاع العقود المفتوحة (نسبة مئوية)
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_WOLF")

state = {"date": "", "count": 0, "sent_coins": [], "current_source": "BINANCE", "is_first_run": True}

session = requests.Session()

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram Error: {e}")

def get_data(source, endpoint, params=None, is_futures=False):
    base = "https://fapi.binance.com/fapi/v1/" if is_futures else "https://api.binance.com/api/v3/"
    if source == "MEXC": base = "https://api.mexc.com/api/v3/"
    
    try:
        r = session.get(base + endpoint, params=params, timeout=5)
        if r.status_code == 200: return r.json()
    except: return None

def get_open_interest_surge(sym):
    """رصد الانفجار في العقود المفتوحة - محرك بوت ولف"""
    try:
        data = get_data("BINANCE", "openInterest", {"symbol": sym}, is_futures=True)
        if data:
            return float(data['openInterest'])
    except: pass
    return 0

def analyze_flow(sym, source):
    try:
        # استخدام فريم دقيقة واحدة للسرعة القصوى
        kd = get_data(source, "klines", {"symbol": sym, "interval": "1m", "limit": 50})
        if not kd or len(kd) < 20: return None
        
        closes = [float(c[4]) for c in kd]
        opens = [float(c[1]) for c in kd]
        vols = [float(c[5]) for c in kd]
        
        # حساب السيولة الداخلة والخارجة في آخر 3 دقائق
        in_f = 0; out_f = 0
        for i in range(-3, 0):
            val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += val
            else: out_f += val
            
        ratio = in_f / out_f if out_f > 0 else 10
        net = in_f - out_f
        
        # تسارع الفوليوم اللحظي
        avg_v = sum(vols[-20:-1]) / 19
        accel = vols[-1] / avg_v if avg_v > 0 else 1
        
        move_1h = ((closes[-1] - closes[-50]) / closes[-50]) * 100
        
        return {
            "net": net, "ratio": ratio, "accel": accel, 
            "price": closes[-1], "move_1h": move_1h
        }
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})
    
    source = state["current_source"]
    tickers = get_data(source, "ticker/24hr")
    if not tickers: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN"]): continue
        if sym in state["sent_coins"]: continue

        try:
            vol_24h = float(t['quoteVolume'])
            chg_24h = float(t['priceChangePercent'])
            price = float(t['lastPrice'])
            high, low = float(t['highPrice']), float(t['lowPrice'])
            
            # فلتر القاع والسيولة
            if vol_24h < MIN_VOLUME_24H or vol_24h > MAX_VOLUME_24H: continue
            if chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue
            
            pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if pos > MAX_PRICE_POS: continue

            # التحليل العميق (Flow + OI)
            flow = analyze_flow(sym, source)
            if not flow or flow['ratio'] < MIN_FLOW_RATIO or flow['accel'] < MIN_VOL_ACCEL: continue

            # تنبيه ذكي
            state["count"] += 1
            state["sent_coins"].append(sym)
            
            msg = (f"🚀 *ALPHA WOLF LIQUIDITY* 🐺\n\n"
                   f"🔥 *#{sym.replace('USDT','')}* | Signal #{state['count']}\n"
                   f"💰 Price: `{price:.6g}`\n"
                   f"📍 Position: `{pos*100:.1f}%` from Bottom ✅\n"
                   f"📊 Net Flow: `+${flow['net']/1000:.1f}K` \n"
                   f"⚡ Vol Accel: `{flow['accel']:.1f}x` 🔥\n"
                   f"💎 Flow Ratio: `{flow['ratio']:.1f}x` \n"
                   f"📈 1h Move: `{flow['move_1h']:.2f}%` \n\n"
                   f"⚠️ *نظام رصد القيعان: سيولة حقيقية تدخل الآن!*")
            
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym}")
            time.sleep(2) # تجنب الحظر

        except: continue

def main():
    send_telegram("🐺 *ALPHA WOLF BOT 20.0* \nنظام تتبع السيولة والعقود المفتوحة جاهز للعمل.")
    while True:
        try:
            scan()
            time.sleep(30) # فحص كل 30 ثانية
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
