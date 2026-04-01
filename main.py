# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 2.1 (FINAL FIXED)
اقتناص العملات بناءً على تدفق السيولة وتقاطع المتوسطات
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات - قم بوضع بياناتك هنا أو في Railway Variables
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الفلترة (MAFIO Precision)
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 300000  # الحد الأدنى للحجم بالدولار
MAX_24H_CHANGE = 20.0    # تجنب العملات التي ارتفعت كثيراً
MIN_FLOW_RATIO = 3.0     # قوة السيولة الداخلة
MIN_VDELTA = 0.65        # ضغط الشراء 65%+

# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}
last_alert_time = 0

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN:
        logger.info(f"⚠️ تنبيه: لم يتم ضبط التوكن. الرسالة: {message[:50]}...")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        res = requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
        if res.status_code != 200:
            logger.error(f"Telegram API Error: {res.text}")
        else:
            logger.info("✅ تم إرسال الرسالة إلى تلغرام.")
    except Exception as e:
        logger.error(f"Connection Error: {e}")

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json()
    except:
        return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def check_indicators(sym):
    kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 50})
    if not kd or len(kd) < 30: return False, None

    closes = [float(c[4]) for c in kd]
    opens = [float(c[1]) for c in kd]
    vols = [float(c[5]) for c in kd]

    ema5 = calc_ema(closes, 5)
    ema20 = calc_ema(closes, 20)
    
    # شرط التقاطع الإيجابي
    if ema5 <= ema20: return False, None
    
    # حساب تدفق السيولة
    in_vol = 0; out_vol = 0
    for i in range(-5, 0):
        val = vols[i] * closes[i]
        if closes[i] > opens[i]: in_vol += val
        else: out_vol += val
    
    if out_vol == 0: out_vol = 1
    ratio = in_vol / out_vol
    vdelta = in_vol / (in_vol + out_vol)

    if ratio < MIN_FLOW_RATIO or vdelta < MIN_VDELTA: return False, None

    return True, {"ratio": ratio, "vdelta": vdelta}

def scan():
    global last_alert_time
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    logger.info(f"🔍 MAFIO Scanning {len(tickers)} pairs...")

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or "DOWN" in sym or "UP" in sym: continue
        
        try:
            vol = float(t['quoteVolume'])
            chg = float(t['priceChangePercent'])
            price = float(t['lastPrice'])
        except: continue

        if vol < MIN_VOLUME_24H or chg < 0.5 or chg > MAX_24H_CHANGE: continue
        if state["count"] >= MAX_SIGNALS_PER_DAY or sym in state["sent_coins"]: continue
        if time.time() - last_alert_time < 300: continue 

        success, data = check_indicators(sym)
        if success:
            state["count"] += 1
            state["sent_coins"].append(sym)
            last_alert_time = time.time()
            
            msg = (
                "🤖 *MAFIO BOT - إشارة انفجار* 🚀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📍 العملة: *#{sym.replace('USDT','')}*\n"
                f"💰 السعر: `{price:.8g}`\n"
                f"📊 التغيير: `+{chg}%` (دخول مبكر)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌊 *تحليل السيولة (Flow):*\n"
                f"✅ صافي التدفق: `{data['ratio']:.1f}x` لصالح الشراء\n"
                f"💎 ضغط الحيتان: `{data['vdelta']*100:.0f}%` 🔥\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎯 *الحالة:* تقاطع إيجابي + دخول سيولة ضخم\n"
                "⚠️ _ادخل الآن - MAFIO رصد الانفجار!_"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym}")

def main():
    logger.info("🚀 MAFIO BOT Started Successfully!")
    send_telegram("✅ *MAFIO BOT* يعمل الآن بنجاح ويبحث عن الفرص...")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()
